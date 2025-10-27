import os
import re
import requests
from flask import Flask, request, abort

app = Flask(__name__)

# Environment variables (set in Render as ENV vars)
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
ADMIN_IDS = os.environ.get("ADMIN_IDS", "")  # comma separated numeric ids, e.g. "12345678,87654321"
CHANNEL_REPLACEMENT = os.environ.get("CHANNEL_REPLACEMENT", "@medwayteam")

if not TELEGRAM_TOKEN:
    raise RuntimeError("TELEGRAM_TOKEN environment variable is required")

# prepare admin set
def parse_admins(s: str):
    s = s.strip()
    if not s:
        return set()
    return set(int(x.strip()) for x in s.split(",") if x.strip().isdigit())

ADMINS = parse_admins(ADMIN_IDS)

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
# regex: https://t.me/..., t.me/..., @username (word chars)
TG_PATTERN = re.compile(r"(https?://t\.me/[^\s]+|t\.me/[^\s]+|@\w+)", flags=re.IGNORECASE)

def replace_telegram_links(text: str) -> str:
    if text is None:
        return text
    return TG_PATTERN.sub(CHANNEL_REPLACEMENT, text)

@app.route("/healthz")
def health():
    return "OK"

@app.route("/webhook", methods=["POST"])
def webhook():
    if request.headers.get("Content-Type", "").startswith("application/json"):
        data = request.get_json()
    else:
        abort(400)

    # only handle message updates
    if "message" not in data:
        return "no message"

    msg = data["message"]
    # get sender id (could be from 'from' for private/group messages)
    sender = msg.get("from")
    if not sender:
        return "no sender"

    sender_id = sender.get("id")
    if sender_id is None:
        return "no sender id"

    # Check admin permission
    if ADMINS and sender_id not in ADMINS:
        # Option: do not respond or send a permission-denied message.
        # Here we optionally send a short permission notice.
        try:
            send_message(msg["chat"]["id"], "شما دسترسی لازم برای استفاده از این ربات را ندارید.")
        except Exception:
            app.logger.info("Non-admin attempted usage: %s", sender_id)
        return "forbidden"

    # Accept text messages and captions
    text = msg.get("text")
    caption = msg.get("caption")
    updated = None

    if text:
        updated = replace_telegram_links(text)
    elif caption:
        updated = replace_telegram_links(caption)

    # If nothing to reply (no text/caption) do nothing
    if updated is None:
        return "no text"

    # send the modified text back to the same chat
    send_message(msg["chat"]["id"], updated)
    return "ok"

def send_message(chat_id, text):
    url = TELEGRAM_API + "/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML"
    }
    r = requests.post(url, json=payload, timeout=10)
    try:
        r.raise_for_status()
    except Exception as e:
        app.logger.error("Failed to send message: %s %s", r.status_code, r.text)

if name == "__main__":
    # local run
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
