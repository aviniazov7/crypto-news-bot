"""
Crypto News Telegram Bot — Auto-send briefings + Twitter monitoring.
Admin-only commands. Designed for group deployment.
"""

import json
import os
import sys
import time
import urllib.request
from datetime import timezone, timedelta

import news
import twitter
import storage

# ── Config ──────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
ADMIN_ID = os.environ.get("ADMIN_ID", "")
POLL_INTERVAL = 1
TWITTER_CHECK_INTERVAL = 300   # 5 minutes
BRIEFING_INTERVAL = 14400      # 4 hours
ISRAEL_TZ = timezone(timedelta(hours=3))

API_BASE = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

# ── Telegram API Helpers ────────────────────────────────────────────

def tg_request(method, payload=None):
    url = f"{API_BASE}/{method}"
    if payload:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    else:
        req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f"  ⚠️  TG {method}: {e}")
        return {}


def send_message(chat_id, text):
    payload = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True,
    }
    topic_id = storage.get_topic_id()
    if topic_id:
        payload["message_thread_id"] = int(topic_id)
    return tg_request("sendMessage", payload)

def set_bot_commands():
    commands = [
        {"command": "start", "description": "Bot status & setup"},
        {"command": "send", "description": "Send briefing now"},
        {"command": "list", "description": "Tracked Twitter accounts"},
        {"command": "add", "description": "Track a Twitter account"},
        {"command": "remove", "description": "Untrack a Twitter account"},
    ]
    tg_request("setMyCommands", {"commands": commands})

# ── Admin Check ─────────────────────────────────────────────────────

def is_admin(msg):
    user_id = str(msg.get("from", {}).get("id", ""))
    return user_id == ADMIN_ID

# ── Command Handlers (admin only) ──────────────────────────────────

def handle_start(chat_id, topic_id=None):
    # save this chat (and topic) as the target for auto-sending
    storage.set_chat_id(chat_id)
    if topic_id:
        storage.set_topic_id(topic_id)
    accounts = storage.list_accounts()
    acc_text = ", ".join(f"@{a}" for a in accounts) if accounts else "None"
    text = (
        "🤖 Crypto News Bot — Ready!\n\n"
        f"📡 Auto-briefing every 4h to this chat\n"
        f"🐦 Tracking: {acc_text}\n\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "📋 Admin Commands:\n"
        "/send — Send briefing now\n"
        "/list — Tracked accounts\n"
        "/add @handle — Track account\n"
        "/remove @handle — Untrack\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "🔗 Send any x.com link to auto-track"
    )
    send_message(chat_id, text)


def handle_add_twitter(chat_id, handle):
    if storage.add_account(handle):
        twitter.init_account(handle)
        send_message(chat_id, f"✅ Now tracking @{handle}")
    else:
        send_message(chat_id, f"ℹ️ Already tracking @{handle}")


def handle_remove_twitter(chat_id, text):
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        send_message(chat_id, "Usage: /remove @username")
        return
    handle = parts[1].strip().lstrip("@").lower()
    if storage.remove_account(handle):
        send_message(chat_id, f"✅ Stopped tracking @{handle}")
    else:
        send_message(chat_id, f"⚠️ @{handle} is not tracked")


def handle_twitter_list(chat_id):
    accounts = storage.list_accounts()
    if not accounts:
        send_message(chat_id, "🐦 No tracked accounts\n\nUse /add @username to start tracking")
    else:
        lines = ["🐦 Tracked Accounts:", ""]
        for acc in accounts:
            lines.append(f"  • @{acc}")
        lines.append("")
        lines.append("Add: /add @username")
        lines.append("Remove: /remove @username")
        send_message(chat_id, "\n".join(lines))

# ── Message Processing ─────────────────────────────────────────────

def process_message(msg):
    if not is_admin(msg):
        return

    chat_id = msg["chat"]["id"]
    topic_id = msg.get("message_thread_id")
    text = msg.get("text", "").strip()
    if not text:
        return

    cmd = text.split()[0].lower()
    if cmd in ("/start", "/start@cryptonewsbot"):
        handle_start(chat_id, topic_id)
    elif cmd in ("/list", "/list@cryptonewsbot", "/twitter", "/twitter@cryptonewsbot"):
        handle_twitter_list(chat_id)
    elif cmd in ("/add", "/add@cryptonewsbot"):
        parts = text.split(maxsplit=1)
        if len(parts) >= 2:
            handle = parts[1].strip().lstrip("@").lower()
            handle_add_twitter(chat_id, handle)
    elif cmd in ("/remove", "/remove@cryptonewsbot"):
        handle_remove_twitter(chat_id, text)
    elif cmd in ("/send", "/send@cryptonewsbot"):
        send_auto_briefing()
    # Twitter link detection
    elif "twitter.com/" in text or "x.com/" in text:
        detected = twitter.extract_handle_from_url(text)
        if detected:
            handle_add_twitter(chat_id, detected)

# ── Scheduled Tasks ────────────────────────────────────────────────

def get_target_chat():
    """Get the target chat ID from storage."""
    return storage.get_chat_id()


def check_twitter_feeds():
    chat_id = get_target_chat()
    if not chat_id:
        return
    new_tweets = twitter.check_all_accounts()
    if not new_tweets:
        return
    for handle, tweets in new_tweets.items():
        for tweet in tweets:
            msg = twitter.format_tweet_message(tweet)
            send_message(chat_id, msg)
            time.sleep(0.5)


def send_auto_briefing():
    chat_id = get_target_chat()
    if not chat_id:
        print("⚠️  No target chat set — send /start in a group first")
        return
    print("📨 Sending auto-briefing...")
    prices = news.fetch_prices()
    items = news.fetch_all_news()
    msg = news.build_briefing(items, prices)
    send_message(chat_id, msg)

# ── Main Bot Loop ──────────────────────────────────────────────────

class CryptoBot:
    def __init__(self):
        self.offset = 0
        self.last_twitter_check = 0
        self.last_briefing = 0

    def run(self):
        if not TELEGRAM_TOKEN:
            print("❌ Missing TELEGRAM_BOT_TOKEN")
            sys.exit(1)
        if not ADMIN_ID:
            print("⚠️  No ADMIN_ID set — bot will ignore all commands")

        print("🚀 Crypto News Bot starting (auto-send mode)...")
        set_bot_commands()
        print(f"📡 Briefing every {BRIEFING_INTERVAL // 3600}h | Twitter check every {TWITTER_CHECK_INTERVAL // 60}min")

        self.last_briefing = time.time()
        self.last_twitter_check = time.time()

        print("🔄 Polling for updates...")

        while True:
            try:
                self._poll()
                self._check_scheduled()
            except KeyboardInterrupt:
                print("\n👋 Bot stopped.")
                break
            except Exception as e:
                print(f"⚠️  Main loop error: {e}")
                time.sleep(5)

    def _poll(self):
        result = tg_request("getUpdates", {"offset": self.offset, "timeout": 30})
        updates = result.get("result", [])

        for update in updates:
            self.offset = update["update_id"] + 1
            try:
                if "message" in update:
                    process_message(update["message"])
            except Exception as e:
                print(f"  ⚠️  Update error: {e}")

    def _check_scheduled(self):
        now = time.time()

        if now - self.last_twitter_check >= TWITTER_CHECK_INTERVAL:
            self.last_twitter_check = now
            try:
                check_twitter_feeds()
            except Exception as e:
                print(f"  ⚠️  Twitter check: {e}")

        if now - self.last_briefing >= BRIEFING_INTERVAL:
            self.last_briefing = now
            try:
                send_auto_briefing()
            except Exception as e:
                print(f"  ⚠️  Briefing: {e}")
