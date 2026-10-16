
# #     # "code": "4/0AXlqoi60xzeGLjiaKFDk6_cpzHpm1y7yMQSGHlgQ6k3V_kFZJA-PV5qhh5mf39ODCXEs7w",
# #     # "client_id": "523524526742-5k4e6900v367qh6bovfml4970e0ou0rq.apps.googleusercontent.com",
# #     # "client_secret": "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",

# import os
# import base64
# import datetime
# import html
# import re
# import secrets
# import threading
# import time
# import urllib.parse
# import webbrowser
# from http.server import BaseHTTPRequestHandler, HTTPServer

# import requests

# # ============================================================
# # CONFIGURATION  (use NEW secrets — old ones were exposed)
# # ============================================================

# CLIENT_ID = "523524526742-5k4e6900v367qh6bovfml4970e0ou0rq.apps.googleusercontent.com"
# CLIENT_SECRET = "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"

# TELEGRAM_BOT_TOKEN = "8976557269:AAEAZ_KUFPrk2qxrSdoqcH7MCcFufwvx42k"
# TELEGRAM_CHAT_ID = "8145643961"

# REDIRECT_URI = "http://localhost:5500/oauth-callback"
# PORT = 5500
# CHECK_EVERY_SECONDS = 30

# SCOPES = " ".join([
#     "openid",
#     "email",
#     "profile",
#     "https://www.googleapis.com/auth/gmail.readonly",
# ])

# auth_code = None
# auth_error = None
# auth_state = secrets.token_urlsafe(32)
# auth_event = threading.Event()


# class OAuthHandler(BaseHTTPRequestHandler):
#     def do_GET(self):
#         global auth_code, auth_error

#         parsed = urllib.parse.urlparse(self.path)
#         if parsed.path != "/oauth-callback":
#             self.send_response(404)
#             self.end_headers()
#             self.wfile.write(b"Not found")
#             return

#         query = urllib.parse.parse_qs(parsed.query)
#         returned_state = query.get("state", [""])[0]

#         if not secrets.compare_digest(returned_state, auth_state):
#             self.send_response(400)
#             self.end_headers()
#             self.wfile.write(b"Invalid OAuth state. Try again.")
#             return

#         if "error" in query:
#             auth_error = query["error"][0]
#             self.send_response(400)
#             self.end_headers()
#             self.wfile.write(b"Google authorization failed. Return to the terminal.")
#             auth_event.set()
#             return

#         if "code" not in query:
#             self.send_response(400)
#             self.end_headers()
#             self.wfile.write(b"No authorization code received.")
#             return

#         auth_code = query["code"][0]
#         self.send_response(200)
#         self.send_header("Content-Type", "text/html; charset=utf-8")
#         self.end_headers()
#         self.wfile.write(
#             b"<h2>Google login successful.</h2>"
#             b"<p>You can return to the terminal.</p>"
#         )
#         auth_event.set()

#     def log_message(self, format, *args):
#         return


# def response_json(response):
#     try:
#         return response.json()
#     except ValueError:
#         return {"error": response.text[:500]}


# def exchange_code_for_tokens(code):
#     response = requests.post(
#         "https://oauth2.googleapis.com/token",
#         data={
#             "code": code,
#             "client_id": CLIENT_ID,
#             "client_secret": CLIENT_SECRET,
#             "redirect_uri": REDIRECT_URI,
#             "grant_type": "authorization_code",
#         },
#         timeout=(10, 60),
#     )
#     return response.status_code, response_json(response)


# def refresh_access_token(refresh_token):
#     response = requests.post(
#         "https://oauth2.googleapis.com/token",
#         data={
#             "client_id": CLIENT_ID,
#             "client_secret": CLIENT_SECRET,
#             "refresh_token": refresh_token,
#             "grant_type": "refresh_token",
#         },
#         timeout=(10, 60),
#     )
#     return response.status_code, response_json(response)


# def get_user_email(access_token):
#     response = requests.get(
#         "https://www.googleapis.com/oauth2/v3/userinfo",
#         headers={"Authorization": f"Bearer {access_token}"},
#         timeout=(10, 60),
#     )
#     data = response_json(response)
#     if response.status_code != 200:
#         raise RuntimeError(f"Could not get Google account details: {data}")
#     return data.get("email"), data.get("name")


# def send_telegram_message(text):
#     if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
#         print("Telegram configuration is missing.")
#         return False

#     url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
#     chunks = [text[i:i + 3500] for i in range(0, len(text), 3500)] or [
#         "A new unread email was received."
#     ]

#     try:
#         for chunk in chunks:
#             response = requests.post(
#                 url,
#                 data={"chat_id": TELEGRAM_CHAT_ID, "text": chunk},
#                 timeout=(10, 30),
#             )
#             data = response_json(response)
#             if response.status_code != 200 or not data.get("ok"):
#                 print("Telegram delivery failed:", data)
#                 return False
#         return True
#     except requests.exceptions.RequestException as exc:
#         print("Telegram connection problem:", exc)
#         return False


# def list_unread_messages(access_token, max_results=100):
#     url = "https://gmail.googleapis.com/gmail/v1/users/me/messages"
#     messages = []
#     page_token = None

#     while True:
#         params = {
#             "maxResults": max_results,
#             "q": "in:inbox is:unread",
#         }
#         if page_token:
#             params["pageToken"] = page_token

#         response = requests.get(
#             url,
#             headers={"Authorization": f"Bearer {access_token}"},
#             params=params,
#             timeout=(10, 60),
#         )
#         data = response_json(response)

#         if response.status_code != 200:
#             return response.status_code, [], data

#         messages.extend(data.get("messages", []))
#         page_token = data.get("nextPageToken")
#         if not page_token:
#             break

#     return 200, messages, {}


# def read_message(access_token, message_id):
#     url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{message_id}"
#     response = requests.get(
#         url,
#         headers={"Authorization": f"Bearer {access_token}"},
#         params={"format": "full"},
#         timeout=(10, 60),
#     )
#     return response.status_code, response_json(response)


# def clean_email_body(body, is_html=False):
#     if is_html:
#         body = re.sub(
#             r"<(script|style)\b[^>]*>.*?</\1>",
#             " ",
#             body,
#             flags=re.I | re.S,
#         )
#         body = re.sub(r"<[^>]+>", " ", body)

#     body = html.unescape(body)
#     body = re.sub(r"\s+", " ", body).strip()
#     return body


# def decode_gmail_body(payload):
#     bodies = []

#     def walk(part):
#         mime = part.get("mimeType", "")
#         data = part.get("body", {}).get("data")
#         if data and mime in ("text/plain", "text/html"):
#             try:
#                 decoded = base64.urlsafe_b64decode(
#                     data + "=" * (-len(data) % 4)
#                 ).decode("utf-8", errors="replace")
#                 bodies.append((mime, decoded))
#             except (ValueError, UnicodeError):
#                 pass
#         for child in part.get("parts", []) or []:
#             walk(child)

#     walk(payload)

#     for mime, body in bodies:
#         if mime == "text/plain":
#             return clean_email_body(body)
#     for mime, body in bodies:
#         if mime == "text/html":
#             return clean_email_body(body, is_html=True)
#     return "[No readable message body found]"


# def get_header(message, name):
#     headers = message.get("payload", {}).get("headers", [])
#     return next(
#         (
#             item.get("value", "")
#             for item in headers
#             if item.get("name", "").lower() == name.lower()
#         ),
#         "(not provided)",
#     )


# def make_email_notification(message):
#     body = decode_gmail_body(message.get("payload", {}))
#     received = ""
#     internal_date = message.get("internalDate")
#     if internal_date:
#         received = datetime.datetime.fromtimestamp(
#             int(internal_date) / 1000
#         ).strftime("%Y-%m-%d %H:%M:%S")

#     body_preview = body[:10000]
#     if len(body) > len(body_preview):
#         body_preview += "\n\n[Message preview shortened.]"

#     return (
#         "NEW UNREAD EMAIL\n\n"
#         f"From: {get_header(message, 'From')}\n"
#         f"To: {get_header(message, 'To')}\n"
#         f"Subject: {get_header(message, 'Subject')}\n"
#         f"Date: {get_header(message, 'Date')}\n"
#         f"Received: {received or '(not provided)'}\n\n"
#         "MESSAGE:\n"
#         f"{body_preview}"
#     )


# def print_message(message):
#     print("\n" + "=" * 60)
#     print("NEW UNREAD EMAIL")
#     print("=" * 60)
#     print("From:", get_header(message, "From"))
#     print("Subject:", get_header(message, "Subject"))
#     print("Date:", get_header(message, "Date"))
#     print("-" * 60)
#     body = decode_gmail_body(message.get("payload", {}))
#     print(body[:800])
#     if len(body) > 800:
#         print("[Terminal preview shortened to 800 characters.]")
#     print("=" * 60, flush=True)


# def process_messages(access_token, messages, seen_ids):
#     for item in reversed(messages):
#         message_id = item.get("id")
#         if not message_id or message_id in seen_ids:
#             continue

#         status, message = read_message(access_token, message_id)

#         if status == 401:
#             print("Access token expired while reading a message.")
#             return False

#         if status != 200:
#             print(f"Could not read message: {message}")
#             continue

#         print_message(message)
#         notification = make_email_notification(message)

#         if send_telegram_message(notification):
#             print("Successfully sent email to Telegram.")
#             seen_ids.add(message_id)
#         else:
#             print("Telegram delivery failed. This message will be retried.")

#     return True


# def main():
#     global auth_code, auth_error

#     if not CLIENT_ID or not CLIENT_SECRET or "YOUR_" in CLIENT_ID or "YOUR_" in CLIENT_SECRET:
#         print("Set CLIENT_ID and CLIENT_SECRET first.")
#         return

#     if (
#         not TELEGRAM_BOT_TOKEN
#         or not TELEGRAM_CHAT_ID
#         or "YOUR_" in TELEGRAM_BOT_TOKEN
#         or "YOUR_" in TELEGRAM_CHAT_ID
#     ):
#         print("Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID first.")
#         return

#     try:
#         server = HTTPServer(("127.0.0.1", PORT), OAuthHandler)
#     except OSError as exc:
#         print(f"Could not start OAuth server on port {PORT}: {exc}")
#         print("Close the program using port 5500 and try again.")
#         return

#     try:
#         server_thread = threading.Thread(target=server.serve_forever, daemon=True)
#         server_thread.start()

#         print("=" * 60)
#         print("GMAIL TO TELEGRAM WATCHER")
#         print("=" * 60)

#         params = {
#             "client_id": CLIENT_ID,
#             "redirect_uri": REDIRECT_URI,
#             "response_type": "code",
#             "scope": SCOPES,
#             "state": auth_state,
#             "prompt": "consent",
#             "access_type": "offline",
#         }
#         auth_url = (
#             "https://accounts.google.com/o/oauth2/v2/auth?"
#             + urllib.parse.urlencode(params)
#         )

#         print("Opening Google sign-in...")
#         webbrowser.open(auth_url)

#         while not auth_event.wait(timeout=0.5):
#             pass

#         if auth_error:
#             print("Google authorization failed:", auth_error)
#             return
#         if not auth_code:
#             print("No authorization code received.")
#             return

#         status, token_data = exchange_code_for_tokens(auth_code)
#         if status != 200:
#             print("Google token exchange failed:", token_data)
#             return

#         access_token = token_data.get("access_token")
#         refresh_token = token_data.get("refresh_token")
#         if not access_token:
#             print("Google did not return an access token.")
#             return

#         email, name = get_user_email(access_token)
#         print("Connected Gmail:", email)
#         if name:
#             print("Account name:", name)

#         if not refresh_token:
#             print("Warning: no refresh token returned.")

#         if not send_telegram_message(
#             f"Gmail watcher connected.\nAccount: {email}\n"
#             "Monitoring new unread inbox messages."
#         ):
#             print("Could not send the Telegram test notification.")
#             return

#         print("Telegram test notification sent.")
#         print(f"Checking every {CHECK_EVERY_SECONDS} seconds.")

#         status, messages, raw = list_unread_messages(access_token)
#         if status != 200:
#             print("Could not load unread messages:", raw)
#             return

#         seen_ids = {item["id"] for item in messages if item.get("id")}
#         print(f"Existing unread messages: {len(seen_ids)}")
#         print("Only newly detected unread emails will be sent.")
#         print("Watcher is running. Press Ctrl+C to stop.\n")

#         while True:
#             time.sleep(CHECK_EVERY_SECONDS)
#             try:
#                 status, messages, raw = list_unread_messages(access_token)

#                 if status == 401 and refresh_token:
#                     print("Refreshing Google access token...")
#                     refresh_status, refresh_data = refresh_access_token(refresh_token)
#                     if refresh_status == 200 and refresh_data.get("access_token"):
#                         access_token = refresh_data["access_token"]
#                         print("Access token refreshed.")
#                         status, messages, raw = list_unread_messages(access_token)
#                     else:
#                         print("Token refresh failed:", refresh_data)
#                         continue

#                 now = datetime.datetime.now().strftime("%H:%M:%S")

#                 if status != 200:
#                     print(f"[{now}] Gmail API error: {raw}")
#                     continue

#                 new_messages = [
#                     item for item in messages if item.get("id") not in seen_ids
#                 ]

#                 if new_messages:
#                     print(f"[{now}] Found {len(new_messages)} new unread email(s).")
#                     success = process_messages(access_token, new_messages, seen_ids)
#                     if not success and refresh_token:
#                         refresh_status, refresh_data = refresh_access_token(refresh_token)
#                         if refresh_status == 200 and refresh_data.get("access_token"):
#                             access_token = refresh_data["access_token"]
#                             process_messages(access_token, new_messages, seen_ids)
#                         else:
#                             print("Token refresh failed:", refresh_data)
#                 else:
#                     print(f"[{now}] No new unread messages.")

#             except requests.exceptions.RequestException as exc:
#                 print("[Network problem]", exc)
#             except (ValueError, KeyError) as exc:
#                 print("[Response processing problem]", exc)

#     except KeyboardInterrupt:
#         print("\nWatcher stopped.")
#     except requests.exceptions.RequestException as exc:
#         print("Network request failed:", exc)
#     finally:
#         server.shutdown()
#         server.server_close()


# if __name__ == "__main__":
#     main()



import base64
import datetime
import html
import os
import re
import secrets
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests

# ============================================================
# CONFIG from environment (set these in Render Dashboard)
# ============================================================

CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "523524526742-5k4e6900v367qh6bovfml4970e0ou0rq.apps.googleusercontent.com").strip()
CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "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").strip()
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8976557269:AAEAZ_KUFPrk2qxrSdoqcH7MCcFufwvx42k").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "8145643961").strip()

# Example: https://gmail-telegram-app.onrender.com/oauth-callback
REDIRECT_URI = os.environ.get(
    "REDIRECT_URI",
    "https://YOUR-SERVICE.onrender.com/oauth-callback",
).strip()

PORT = int(os.environ.get("PORT", "10000"))  # Render sets PORT
CHECK_EVERY_SECONDS = int(os.environ.get("CHECK_EVERY_SECONDS", "30"))

SCOPES = " ".join([
    "openid",
    "email",
    "profile",
    "https://www.googleapis.com/auth/gmail.readonly",
])

auth_code = None
auth_error = None
auth_state = secrets.token_urlsafe(32)
auth_event = threading.Event()


class OAuthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global auth_code, auth_error

        parsed = urllib.parse.urlparse(self.path)

        # Health check for Render
        if parsed.path in ("/", "/health"):
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"ok")
            return

        if parsed.path != "/oauth-callback":
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not found")
            return

        query = urllib.parse.parse_qs(parsed.query)
        returned_state = query.get("state", [""])[0]

        if not secrets.compare_digest(returned_state, auth_state):
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Invalid OAuth state.")
            return

        if "error" in query:
            auth_error = query["error"][0]
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Google authorization failed.")
            auth_event.set()
            return

        if "code" not in query:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"No authorization code.")
            return

        auth_code = query["code"][0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(
            b"<h2>Google login successful.</h2>"
            b"<p>You can close this tab. Check Render logs.</p>"
        )
        auth_event.set()

    def log_message(self, format, *args):
        print("HTTP:", format % args)


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
        timeout=(10, 60),
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
        timeout=(10, 60),
    )
    return response.status_code, response_json(response)


def get_user_email(access_token):
    response = requests.get(
        "https://www.googleapis.com/oauth2/v3/userinfo",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=(10, 60),
    )
    data = response_json(response)
    if response.status_code != 200:
        raise RuntimeError(f"Could not get account details: {data}")
    return data.get("email"), data.get("name")


def send_telegram_message(text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram not configured; printing only.")
        print(text)
        return True

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    chunks = [text[i:i + 3500] for i in range(0, len(text), 3500)] or ["(empty)"]

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
    except requests.exceptions.RequestException as exc:
        print("Telegram connection problem:", exc)
        return False


def list_unread_messages(access_token, max_results=50):
    url = "https://gmail.googleapis.com/gmail/v1/users/me/messages"
    messages = []
    page_token = None

    while True:
        params = {"maxResults": max_results, "q": "in:inbox is:unread"}
        if page_token:
            params["pageToken"] = page_token

        response = requests.get(
            url,
            headers={"Authorization": f"Bearer {access_token}"},
            params=params,
            timeout=(10, 60),
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
    url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{message_id}"
    response = requests.get(
        url,
        headers={"Authorization": f"Bearer {access_token}"},
        params={"format": "full"},
        timeout=(10, 60),
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


def print_message(message):
    print("\n" + "=" * 60)
    print("NEW UNREAD EMAIL")
    print("=" * 60)
    print("From:", get_header(message, "From"))
    print("Subject:", get_header(message, "Subject"))
    print("Date:", get_header(message, "Date"))
    print("-" * 60)
    body = decode_gmail_body(message.get("payload", {}))
    print(body[:800])
    print("=" * 60, flush=True)


def process_messages(access_token, messages, seen_ids):
    for item in reversed(messages):
        message_id = item.get("id")
        if not message_id or message_id in seen_ids:
            continue

        status, message = read_message(access_token, message_id)
        if status == 401:
            print("Access token expired while reading a message.")
            return False
        if status != 200:
            print(f"Could not read message: {message}")
            continue

        print_message(message)
        notification = make_email_notification(message)

        if send_telegram_message(notification):
            print("Notification sent.")
            seen_ids.add(message_id)
        else:
            print("Telegram failed; will retry this message.")

    return True


def main():
    global auth_code, auth_error

    if not CLIENT_ID or not CLIENT_SECRET:
        print("Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in Render env.")
        return

    if "YOUR-SERVICE" in REDIRECT_URI:
        print("Set REDIRECT_URI to your real Render URL + /oauth-callback")
        return

    try:
        # Required for Render: bind 0.0.0.0 and use PORT
        server = HTTPServer(("0.0.0.0", PORT), OAuthHandler)
    except OSError as exc:
        print(f"Could not start server on port {PORT}: {exc}")
        return

    try:
        threading.Thread(target=server.serve_forever, daemon=True).start()
        print("=" * 60)
        print("GMAIL WATCHER (Render)")
        print("=" * 60)
        print(f"Listening on 0.0.0.0:{PORT}")
        print(f"Redirect URI: {REDIRECT_URI}")

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

        # No browser on Render — open this URL on your PC
        print("\nOpen this URL in YOUR browser (your Gmail only):\n")
        print(auth_url)
        print("\nWaiting for OAuth callback...")

        while not auth_event.wait(timeout=0.5):
            pass

        if auth_error:
            print("Google authorization failed:", auth_error)
            return
        if not auth_code:
            print("No authorization code received.")
            return

        status, token_data = exchange_code_for_tokens(auth_code)
        if status != 200:
            print("Token exchange failed:", token_data)
            return

        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")
        if not access_token:
            print("No access token returned.")
            return

        email, name = get_user_email(access_token)
        print("Connected Gmail:", email)
        if name:
            print("Account name:", name)

        send_telegram_message(
            f"Gmail watcher connected.\nAccount: {email}\n"
            f"Checking every {CHECK_EVERY_SECONDS}s."
        )

        status, messages, raw = list_unread_messages(access_token)
        if status != 200:
            print("Could not load unread messages:", raw)
            return

        seen_ids = {item["id"] for item in messages if item.get("id")}
        print(f"Existing unread: {len(seen_ids)}")
        print("Watching for NEW unread mail only.\n")

        while True:
            time.sleep(CHECK_EVERY_SECONDS)
            try:
                status, messages, raw = list_unread_messages(access_token)

                if status == 401 and refresh_token:
                    print("Refreshing access token...")
                    rs, rd = refresh_access_token(refresh_token)
                    if rs == 200 and rd.get("access_token"):
                        access_token = rd["access_token"]
                        status, messages, raw = list_unread_messages(access_token)
                    else:
                        print("Refresh failed:", rd)
                        continue

                now = datetime.datetime.now().strftime("%H:%M:%S")
                if status != 200:
                    print(f"[{now}] Gmail API error: {raw}")
                    continue

                new_messages = [
                    m for m in messages if m.get("id") not in seen_ids
                ]

                if new_messages:
                    print(f"[{now}] {len(new_messages)} new unread message(s).")
                    ok = process_messages(access_token, new_messages, seen_ids)
                    if not ok and refresh_token:
                        rs, rd = refresh_access_token(refresh_token)
                        if rs == 200 and rd.get("access_token"):
                            access_token = rd["access_token"]
                            process_messages(access_token, new_messages, seen_ids)
                else:
                    print(f"[{now}] No new unread messages.")

            except requests.exceptions.RequestException as exc:
                print("[Network problem]", exc)
            except (ValueError, KeyError) as exc:
                print("[Response problem]", exc)

    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()