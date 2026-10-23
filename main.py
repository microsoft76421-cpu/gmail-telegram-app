import os
import base64
import datetime
import html
import re
import secrets
import threading
import time
import urllib.parse

import requests
from flask import Flask, redirect, request, jsonify, session, render_template_string

# ============================================================
# CONFIGURATION — ENTER YOUR ROTATED CREDENTIALS
# ============================================================
CLIENT_ID = "523524526742-5k4e6900v367qh6bovfml4970e0ou0rq.apps.googleusercontent.com"
CLIENT_SECRET = "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"

TELEGRAM_BOT_TOKEN = "8976557269:AAEAZ_KUFPrk2qxrSdoqcH7MCcFufwvx42k"
TELEGRAM_CHAT_ID = "8145643961"

# Local development URL. For deployment, change this to your
# public HTTPS URL and register it in Google Cloud Console.
BASE_URL = "https://gmail-telegram-app-9.onrender.com"
REDIRECT_URI = BASE_URL + "/oauth-callback"

SCOPES = " ".join([
    "openid",
    "email",
    "profile",
    "https://www.googleapis.com/auth/gmail.readonly",
])

CHECK_EVERY_SECONDS = 30

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)

# For local testing only: memory state is lost when the process stops.
state = {
    "access_token": None,
    "refresh_token": None,
    "email": None,
    "name": None,
    "seen_ids": set(),
    "watcher_running": False,
    "last_check": None,
    "last_error": None,
}
state_lock = threading.RLock()


def response_json(response):
    try:
        return response.json()
    except ValueError:
        return {"error": response.text[:500]}


def exchange_code_for_tokens(code):
    response = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "code": code,
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "redirect_uri": REDIRECT_URI,
            "grant_type": "authorization_code",
        },
        timeout=(10, 30),
    )
    return response.status_code, response_json(response)


def refresh_access_token(refresh_token):
    response = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=(10, 30),
    )
    return response.status_code, response_json(response)


def get_user_email(access_token):
    response = requests.get(
        "https://www.googleapis.com/oauth2/v3/userinfo",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=(10, 30),
    )
    data = response_json(response)
    if response.status_code != 200:
        raise RuntimeError(f"Google account lookup failed: {data}")
    return data.get("email"), data.get("name")


def send_telegram_message(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram configuration is missing.")
        return False

    url = (
        "https://api.telegram.org/bot"
        + TELEGRAM_BOT_TOKEN
        + "/sendMessage"
    )

    chunks = [
        message[i:i + 3500]
        for i in range(0, len(message), 3500)
    ] or ["A new unread email was received."]

    try:
        for chunk in chunks:
            response = requests.post(
                url,
                data={"chat_id": TELEGRAM_CHAT_ID, "text": chunk},
                timeout=(10, 30),
            )
            data = response_json(response)
            if response.status_code != 200 or not data.get("ok"):
                print("Telegram delivery failed:", data)
                return False
        return True
    except requests.RequestException as exc:
        print("Telegram connection problem:", exc)
        return False


def list_unread_messages(access_token, max_results=100):
    url = "https://gmail.googleapis.com/gmail/v1/users/me/messages"
    messages = []
    page_token = None

    while True:
        params = {
            "maxResults": max_results,
            "q": "in:inbox is:unread",
        }
        if page_token:
            params["pageToken"] = page_token

        response = requests.get(
            url,
            headers={"Authorization": f"Bearer {access_token}"},
            params=params,
            timeout=(10, 30),
        )
        data = response_json(response)

        if response.status_code != 200:
            return response.status_code, [], data

        messages.extend(data.get("messages", []))
        page_token = data.get("nextPageToken")
        if not page_token:
            break

    return 200, messages, {}


def read_message(access_token, message_id):
    url = (
        "https://gmail.googleapis.com/gmail/v1/users/me/messages/"
        + urllib.parse.quote(message_id, safe="")
    )
    response = requests.get(
        url,
        headers={"Authorization": f"Bearer {access_token}"},
        params={"format": "full"},
        timeout=(10, 30),
    )
    return response.status_code, response_json(response)


def clean_email_body(body, is_html=False):
    if is_html:
        body = re.sub(
            r"<(script|style)\b[^>]*>.*?</\1>",
            " ",
            body,
            flags=re.I | re.S,
        )
        body = re.sub(r"<[^>]+>", " ", body)

    body = html.unescape(body)
    return re.sub(r"\s+", " ", body).strip()


def decode_gmail_body(payload):
    bodies = []

    def walk(part):
        mime = part.get("mimeType", "")
        data = part.get("body", {}).get("data")

        if data and mime in ("text/plain", "text/html"):
            try:
                decoded = base64.urlsafe_b64decode(
                    data + "=" * (-len(data) % 4)
                ).decode("utf-8", errors="replace")
                bodies.append((mime, decoded))
            except (ValueError, UnicodeError):
                pass

        for child in part.get("parts", []) or []:
            walk(child)

    walk(payload)

    for mime, body in bodies:
        if mime == "text/plain":
            return clean_email_body(body)

    for mime, body in bodies:
        if mime == "text/html":
            return clean_email_body(body, is_html=True)

    return "[No readable message body found]"


def get_header(message, name):
    headers = message.get("payload", {}).get("headers", [])
    return next(
        (
            item.get("value", "")
            for item in headers
            if item.get("name", "").lower() == name.lower()
        ),
        "(not provided)",
    )


def make_email_notification(message):
    body = decode_gmail_body(message.get("payload", {}))
    received = ""
    internal_date = message.get("internalDate")

    if internal_date:
        received = datetime.datetime.fromtimestamp(
            int(internal_date) / 1000
        ).strftime("%Y-%m-%d %H:%M:%S")

    body_preview = body[:10000]
    if len(body) > len(body_preview):
        body_preview += "\n\n[Message preview shortened.]"

    return (
        "NEW UNREAD EMAIL\n\n"
        f"From: {get_header(message, 'From')}\n"
        f"To: {get_header(message, 'To')}\n"
        f"Subject: {get_header(message, 'Subject')}\n"
        f"Date: {get_header(message, 'Date')}\n"
        f"Received: {received or '(not provided)'}\n\n"
        "MESSAGE:\n"
        f"{body_preview}"
    )


def process_messages(access_token, messages):
    for item in reversed(messages):
        message_id = item.get("id")
        with state_lock:
            if not message_id or message_id in state["seen_ids"]:
                continue

        status, message = read_message(access_token, message_id)

        if status == 401:
            return False

        if status != 200:
            print("Could not read message:", message)
            continue

        notification = make_email_notification(message)

        if send_telegram_message(notification):
            with state_lock:
                state["seen_ids"].add(message_id)
            print("Sent email notification:", get_header(message, "Subject"))
        else:
            print("Telegram delivery failed; will retry.")

    return True


def watcher_loop():
    while True:
        with state_lock:
            if not state["watcher_running"]:
                return
            access_token = state["access_token"]
            refresh_token = state["refresh_token"]

        if not access_token:
            time.sleep(5)
            continue

        try:
            status, messages, raw = list_unread_messages(access_token)

            if status == 401 and refresh_token:
                refresh_status, refresh_data = refresh_access_token(
                    refresh_token
                )

                if refresh_status == 200 and refresh_data.get("access_token"):
                    access_token = refresh_data["access_token"]
                    with state_lock:
                        state["access_token"] = access_token
                    status, messages, raw = list_unread_messages(access_token)
                else:
                    with state_lock:
                        state["last_error"] = "Token refresh failed"
                    time.sleep(CHECK_EVERY_SECONDS)
                    continue

            with state_lock:
                state["last_check"] = datetime.datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                )

            if status != 200:
                with state_lock:
                    state["last_error"] = str(raw)
                print("Gmail API error:", raw)
            else:
                with state_lock:
                    state["last_error"] = None
                    known_ids = set(state["seen_ids"])

                new_messages = [
                    item for item in messages
                    if item.get("id") not in known_ids
                ]

                if new_messages:
                    process_messages(access_token, new_messages)
                else:
                    print("No new unread messages.")

        except Exception as exc:
            with state_lock:
                state["last_error"] = str(exc)
            print("Watcher error:", exc)

        time.sleep(CHECK_EVERY_SECONDS)


# ============================================================
# FRONTEND — SERVED DIRECTLY BY FLASK
# ============================================================
@app.route("/")
def index():
    return render_template_string("""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Private Inbox — Google Connection</title>
<style>
* { margin:0; padding:0; box-sizing:border-box; }
body {
  min-height:100vh; display:flex; justify-content:center;
  align-items:center; background:#0a0608;
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
  color:#f5e6ec; padding:20px;
}
.container {
  width:100%; max-width:520px; text-align:center;
  padding:2.5rem 2rem; border:1px solid #3a202b;
  border-radius:22px; background:#110b0e;
  box-shadow:0 18px 60px #0008;
}
h1 {
  font-size:1.9rem; margin-bottom:1rem;
  background:linear-gradient(135deg,#fff,#ff8fab);
  -webkit-background-clip:text; -webkit-text-fill-color:transparent;
}
p { color:#c5aab6; line-height:1.65; margin-bottom:1.2rem; }
.notice {
  text-align:left; padding:14px; margin:20px 0;
  background:#1b1016; border:1px solid #49303b;
  border-radius:12px; font-size:.92rem;
}
button {
  background:linear-gradient(135deg,#ff4d7a,#e63b6a);
  color:white; border:0; padding:1rem 1.5rem;
  font-size:1rem; font-weight:600; border-radius:50px;
  cursor:pointer; box-shadow:0 8px 25px #ff4d7a44;
}
button:hover { filter:brightness(1.08); }
button:disabled { opacity:.6; cursor:not-allowed; }
.status { margin-top:1.5rem; color:#ff8fab; min-height:24px; }
.small { font-size:.8rem; color:#a88b98; margin-top:18px; }
</style>
</head>
<body>
<div class="container">
  <h1>Private Inbox</h1>
  <p>Connect your Google account</p>

  <div class="notice">
    <strong>Before you continue</strong>
    <p style="margin:8px 0 0">
      Click the button below to see more.
    </p>
  </div>

  <button id="connectBtn">Continue with Google</button>
  <div class="status" id="status" role="status" aria-live="polite"></div>

</div>
<script>
const btn = document.getElementById("connectBtn");
const status = document.getElementById("status");

btn.addEventListener("click", async () => {
  btn.disabled = true;
  btn.textContent = "Connecting...";
  status.textContent = "Preparing Google authorization...";

  try {
    const res = await fetch("/api/login", {
      headers: {"Accept": "application/json"}
    });
    const data = await res.json();

    if (!res.ok || !data.auth_url) {
      throw new Error(data.error || "Could not start Google authorization.");
    }

    window.location.assign(data.auth_url);
  } catch (err) {
    status.textContent = err.message || "Cannot connect to server.";
    btn.disabled = false;
    btn.textContent = "Continue with Google";
  }
});
</script>
</body>
</html>
""")


@app.route("/api/login")
def api_login():
    auth_state = secrets.token_urlsafe(32)
    session["oauth_state"] = auth_state

    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPES,
        "state": auth_state,
        "prompt": "consent",
        "access_type": "offline",
    }

    auth_url = (
        "https://accounts.google.com/o/oauth2/v2/auth?"
        + urllib.parse.urlencode(params)
    )
    return jsonify({"auth_url": auth_url})


@app.route("/oauth-callback")
def oauth_callback():
    returned_state = request.args.get("state", "")
    expected_state = session.get("oauth_state", "")

    if not expected_state or not secrets.compare_digest(
        returned_state, expected_state
    ):
        return "Invalid OAuth state. Please try again.", 400

    session.pop("oauth_state", None)

    if request.args.get("error"):
        return "Google authorization was cancelled or denied.", 400

    code = request.args.get("code")
    if not code:
        return "No authorization code received.", 400

    status, token_data = exchange_code_for_tokens(code)
    if status != 200:
        print("Token exchange failed:", token_data)
        return "Google token exchange failed. Check the server configuration.", 400

    access_token = token_data.get("access_token")
    refresh_token = token_data.get("refresh_token")

    if not access_token:
        return "No access token received.", 400

    try:
        email, name = get_user_email(access_token)
    except Exception:
        return "Could not retrieve Google account details.", 400

    if not email:
        return "Google did not return an email address.", 400

    # Preserve an existing refresh token if Google does not issue another.
    with state_lock:
        if not refresh_token:
            refresh_token = state["refresh_token"]

        state["access_token"] = access_token
        state["refresh_token"] = refresh_token
        state["email"] = email
        state["name"] = name

    # Do not forward historical unread messages on initial connection.
    status, messages, _ = list_unread_messages(access_token)
    if status == 200:
        with state_lock:
            state["seen_ids"].update(
                item["id"] for item in messages if item.get("id")
            )

    with state_lock:
        should_start = not state["watcher_running"]
        if should_start:
            state["watcher_running"] = True

    if should_start:
        threading.Thread(target=watcher_loop, daemon=True).start()

    send_telegram_message(
        "Gmail watcher connected.\n"
        f"Account: {email}\n"
        "Monitoring new unread inbox messages."
    )

    return """
<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport"
content="width=device-width,initial-scale=1">
<title>Google Connected</title></head>
<body style="background:#0a0608;color:#f5e6ec;font-family:sans-serif;
display:flex;justify-content:center;align-items:center;min-height:100vh">
<div style="text-align:center;padding:24px">
<h2 style="color:#ff8fab">Google Connected</h2>
<p>Authorization succeeded. The inbox watcher has started.</p>
<p>You may close this page.</p>
</div>
</body></html>
"""


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/privacy")
def privacy():
    return """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Privacy Policy</title>
</head>
<body style="font-family:sans-serif;max-width:700px;margin:40px auto;padding:0 16px">
  <h1>Privacy Policy</h1>
  <p>Last updated: October 23, 2026</p>
  <p>This app lets you connect your own Google account to read your Gmail (readonly)
  so you can get notifications about new emails.</p>

  <h2>Data we access</h2>
  <ul>
    <li>Your Google email address</li>
    <li>Gmail messages you authorize (gmail.readonly)</li>
  </ul>

  <h2>How we use data</h2>
  <p>Only to provide the notifications you asked for. We do not sell your data.</p>

  <h2>Your control</h2>
  <p>You can revoke access at
    <a href="https://myaccount.google.com/permissions">Google Account permissions</a>.
  </p>

  <h2>Contact</h2>
  <p>Email: nbroy6969@gmail.com</p>
</body>
</html>
"""


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5500))
    print("=" * 50)
    print("Gmail → Telegram Watcher starting...")
    print(f"Running on port {port}")
    print("=" * 50)
    app.run(host="0.0.0.0", port=port, debug=False)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5500))
    print("=" * 50)
    print("Gmail → Telegram Watcher starting...")
    print(f"Running on port {port}")
    print("=" * 50)
    app.run(host="0.0.0.0", port=port, debug=False)



