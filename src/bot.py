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
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
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
    return tg_request("sendMessage", payload)

# ── Admin Check ─────────────────────────────────────────────────────

def is_admin(msg):
    user_id = str(msg.get("from", {}).get("id", ""))
    return user_id == ADMIN_ID

# ── Command Handlers (admin only) ──────────────────────────────────

def handle_start(chat_id):
    R = "\u200F"
    accounts = storage.list_accounts()
    acc_text = ", ".join(f"@{a}" for a in accounts) if accounts else "אין"
    text = (
        f"{R}🤖 Crypto News Bot\n\n"
        f"{R}📡 סקירה אוטומטית כל 4 שעות\n"
        f"{R}🐦 מעקב טוויטר: {acc_text}\n\n"
        f"{R}פקודות אדמין:\n"
        f"{R}/list — חשבונות במעקב\n"
        f"{R}/add @handle — הוסף מעקב\n"
        f"{R}/remove @handle — הסר מעקב\n"
        f"{R}/send — שלח סקירה עכשיו"
    )
    send_message(chat_id, text)


def handle_add_twitter(chat_id, handle):
    R = "\u200F"
    if storage.add_account(handle):
        twitter.init_account(handle)
        send_message(chat_id, f"{R}✅ מעקב אחרי @{handle} הופעל!")
    else:
        send_message(chat_id, f"{R}ℹ️ כבר עוקב אחרי @{handle}")


def handle_remove_twitter(chat_id, text):
    R = "\u200F"
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        send_message(chat_id, f"{R}שימוש: /remove @username")
        return
    handle = parts[1].strip().lstrip("@").lower()
    if storage.remove_account(handle):
        send_message(chat_id, f"{R}✅ הפסקתי לעקוב אחרי @{handle}")
    else:
        send_message(chat_id, f"{R}⚠️ @{handle} לא נמצא ברשימת המעקב")


def handle_twitter_list(chat_id):
    R = "\u200F"
    accounts = storage.list_accounts()
    if not accounts:
        send_message(chat_id, f"{R}🐦 אין חשבונות במעקב\n\n{R}להוספה: /add @username")
    else:
        lines = [f"{R}🐦 חשבונות במעקב:", ""]
        for acc in accounts:
            lines.append(f"{R}  • @{acc}")
        lines.append("")
        lines.append(f"{R}להוספה: /add @username")
        lines.append(f"{R}להסרה: /remove @username")
        send_message(chat_id, "\n".join(lines))

# ── Message Processing ─────────────────────────────────────────────

def process_message(msg):
    if not is_admin(msg):
        return

    chat_id = msg["chat"]["id"]
    text = msg.get("text", "").strip()
    if not text:
        return

    cmd = text.split()[0].lower()
    if cmd in ("/start", "/start@cryptonewsbot"):
        handle_start(chat_id)
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

def check_twitter_feeds():
    new_tweets = twitter.check_all_accounts()
    if not new_tweets:
        return
    for handle, tweets in new_tweets.items():
        for tweet in tweets:
            msg = twitter.format_tweet_message(tweet)
            send_message(CHAT_ID, msg)
            time.sleep(0.5)


def send_auto_briefing():
    print("📨 Sending auto-briefing...")
    prices = news.fetch_prices()
    items = news.fetch_all_news()
    msg = news.build_briefing(items, prices)
    send_message(CHAT_ID, msg)

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
        if not CHAT_ID:
            print("❌ Missing TELEGRAM_CHAT_ID")
            sys.exit(1)
        if not ADMIN_ID:
            print("⚠️  No ADMIN_ID set — bot will ignore all commands")

        print("🚀 Crypto News Bot starting (auto-send mode)...")
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
