"""
Crypto News Telegram Bot — Interactive polling bot with menu, commands,
Twitter monitoring, AI summaries, and price charts.
"""

import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone, timedelta

import news
import twitter
import charts
import ai_summary
import storage

# ── Config ──────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
POLL_INTERVAL = 1          # seconds between getUpdates calls
TWITTER_CHECK_INTERVAL = 300   # 5 minutes
BRIEFING_INTERVAL = 14400      # 4 hours
ISRAEL_TZ = timezone(timedelta(hours=3))

API_BASE = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

# ── Telegram API Helpers ────────────────────────────────────────────

def tg_request(method, payload=None):
    """Make a Telegram Bot API request."""
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


def send_message(chat_id, text, reply_markup=None):
    """Send a text message."""
    payload = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return tg_request("sendMessage", payload)


def send_photo(chat_id, image_bytes, caption=""):
    """Send a photo via multipart form upload."""
    boundary = "----CryptoBot"
    body = b""
    # chat_id field
    body += f"--{boundary}\r\nContent-Disposition: form-data; name=\"chat_id\"\r\n\r\n{chat_id}\r\n".encode()
    # caption field
    if caption:
        body += f"--{boundary}\r\nContent-Disposition: form-data; name=\"caption\"\r\n\r\n{caption}\r\n".encode()
    # photo file
    body += f"--{boundary}\r\nContent-Disposition: form-data; name=\"photo\"; filename=\"chart.png\"\r\nContent-Type: image/png\r\n\r\n".encode()
    body += image_bytes
    body += f"\r\n--{boundary}--\r\n".encode()

    req = urllib.request.Request(
        f"{API_BASE}/sendPhoto",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f"  ⚠️  sendPhoto: {e}")
        return {}


def answer_callback(callback_query_id, text=""):
    """Answer a callback query (dismiss loading indicator)."""
    payload = {"callback_query_id": callback_query_id}
    if text:
        payload["text"] = text
    return tg_request("answerCallbackQuery", payload)

# ── Menu ────────────────────────────────────────────────────────────

MAIN_MENU = {
    "inline_keyboard": [
        [
            {"text": "📰 חדשות", "callback_data": "cmd_news"},
            {"text": "💰 מחירים", "callback_data": "cmd_prices"},
        ],
        [
            {"text": "📊 גרף", "callback_data": "cmd_chart"},
            {"text": "🐦 טוויטר", "callback_data": "cmd_twitter"},
        ],
        [
            {"text": "🤖 סיכום AI", "callback_data": "cmd_summary"},
        ],
    ]
}

COIN_MENU = {
    "inline_keyboard": [
        [
            {"text": "BTC", "callback_data": "chart_btc"},
            {"text": "ETH", "callback_data": "chart_eth"},
            {"text": "SOL", "callback_data": "chart_sol"},
        ],
        [
            {"text": "BNB", "callback_data": "chart_bnb"},
            {"text": "XRP", "callback_data": "chart_xrp"},
        ],
        [
            {"text": "⬅️ חזרה", "callback_data": "cmd_menu"},
        ],
    ]
}


def set_bot_commands():
    """Register command menu with Telegram."""
    commands = [
        {"command": "start", "description": "התחל + תפריט ראשי"},
        {"command": "news", "description": "חדשות אחרונות"},
        {"command": "prices", "description": "מחירים עכשיו"},
        {"command": "chart", "description": "גרף מחירים"},
        {"command": "twitter", "description": "חשבונות טוויטר"},
        {"command": "summary", "description": "סיכום AI"},
        {"command": "remove", "description": "הסר מעקב טוויטר"},
        {"command": "menu", "description": "הצג תפריט"},
    ]
    tg_request("setMyCommands", {"commands": commands})

# ── Command Handlers ────────────────────────────────────────────────

def handle_start(chat_id):
    R = "\u200F"
    text = (
        f"{R}🚀 ברוכים הבאים ל-Crypto News Bot!\n\n"
        f"{R}מה אני יודע לעשות:\n"
        f"{R}📰 חדשות קריפטו אחרונות\n"
        f"{R}💰 מחירים בזמן אמת\n"
        f"{R}📊 גרפי מחירים\n"
        f"{R}🐦 מעקב טוויטר — שלח לינק של משתמש ואעקוב אחריו\n"
        f"{R}🤖 סיכום AI חכם\n\n"
        f"{R}📌 שלח לי לינק של טוויטר ואתחיל לעקוב!\n"
        f"{R}למשל: https://x.com/whale_alert"
    )
    send_message(chat_id, text, reply_markup=MAIN_MENU)


def handle_news(chat_id):
    send_message(chat_id, "⏳ טוען חדשות...")
    items = news.fetch_all_news()
    msg = news.build_news_message(items)
    send_message(chat_id, msg, reply_markup=MAIN_MENU)


def handle_prices(chat_id):
    send_message(chat_id, "⏳ טוען מחירים...")
    prices = news.fetch_prices()
    msg = news.build_prices_message(prices)
    send_message(chat_id, msg, reply_markup=MAIN_MENU)


def handle_chart_menu(chat_id):
    R = "\u200F"
    send_message(chat_id, f"{R}📊 בחר מטבע לגרף:", reply_markup=COIN_MENU)


def handle_chart(chat_id, symbol):
    send_message(chat_id, f"⏳ יוצר גרף {symbol.upper()}...")
    image_bytes, caption = charts.get_chart_image(symbol)
    if image_bytes:
        send_photo(chat_id, image_bytes, caption)
    else:
        send_message(chat_id, caption)  # error message
    send_message(chat_id, "\u200F📊 בחר מטבע נוסף או חזור:", reply_markup=COIN_MENU)


def handle_twitter_list(chat_id):
    R = "\u200F"
    accounts = storage.list_accounts()
    if not accounts:
        text = (
            f"{R}🐦 אין חשבונות במעקב\n\n"
            f"{R}שלח לי לינק של משתמש בטוויטר ואתחיל לעקוב!\n"
            f"{R}למשל: https://x.com/whale_alert"
        )
    else:
        lines = [f"{R}🐦 חשבונות במעקב:", ""]
        for acc in accounts:
            lines.append(f"{R}  • @{acc}")
        lines.append("")
        lines.append(f"{R}להוספה: שלח לינק טוויטר")
        lines.append(f"{R}להסרה: /remove @username")
        text = "\n".join(lines)
    send_message(chat_id, text, reply_markup=MAIN_MENU)


def handle_summary(chat_id):
    send_message(chat_id, "⏳ מכין סיכום AI...")
    items = news.fetch_all_news()
    summary = ai_summary.summarize_news(items)
    send_message(chat_id, summary, reply_markup=MAIN_MENU)


def handle_add_twitter(chat_id, handle):
    R = "\u200F"
    if storage.add_account(handle):
        # initialize - mark existing tweets as seen
        twitter.init_account(handle)
        send_message(chat_id, f"{R}✅ מעקב אחרי @{handle} הופעל!\n{R}אעביר לך ציוצים חדשים אוטומטית.", reply_markup=MAIN_MENU)
    else:
        send_message(chat_id, f"{R}ℹ️ כבר עוקב אחרי @{handle}", reply_markup=MAIN_MENU)


def handle_remove_twitter(chat_id, text):
    R = "\u200F"
    # extract handle from "/remove @username" or "/remove username"
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        send_message(chat_id, f"{R}שימוש: /remove @username")
        return
    handle = parts[1].strip().lstrip("@").lower()
    if storage.remove_account(handle):
        send_message(chat_id, f"{R}✅ הפסקתי לעקוב אחרי @{handle}", reply_markup=MAIN_MENU)
    else:
        send_message(chat_id, f"{R}⚠️ @{handle} לא נמצא ברשימת המעקב", reply_markup=MAIN_MENU)

# ── Update Processing ──────────────────────────────────────────────

def process_message(msg):
    """Process an incoming message."""
    chat_id = msg["chat"]["id"]
    text = msg.get("text", "").strip()

    if not text:
        return

    # command handling
    cmd = text.split()[0].lower()
    if cmd in ("/start", "/start@cryptonewsbot"):
        handle_start(chat_id)
    elif cmd in ("/news", "/news@cryptonewsbot"):
        handle_news(chat_id)
    elif cmd in ("/prices", "/prices@cryptonewsbot"):
        handle_prices(chat_id)
    elif cmd in ("/chart", "/chart@cryptonewsbot"):
        handle_chart_menu(chat_id)
    elif cmd in ("/twitter", "/twitter@cryptonewsbot"):
        handle_twitter_list(chat_id)
    elif cmd in ("/summary", "/summary@cryptonewsbot"):
        handle_summary(chat_id)
    elif cmd in ("/remove", "/remove@cryptonewsbot"):
        handle_remove_twitter(chat_id, text)
    elif cmd in ("/menu", "/menu@cryptonewsbot"):
        handle_start(chat_id)
    # Twitter link detection
    elif "twitter.com/" in text or "x.com/" in text:
        handle_detected = twitter.extract_handle_from_url(text)
        if handle_detected:
            handle_add_twitter(chat_id, handle_detected)
        else:
            send_message(chat_id, "\u200F⚠️ לא הצלחתי לזהות משתמש מהלינק", reply_markup=MAIN_MENU)


def process_callback(callback):
    """Process an inline keyboard button press."""
    chat_id = callback["message"]["chat"]["id"]
    data = callback.get("data", "")
    answer_callback(callback["id"])

    if data == "cmd_news":
        handle_news(chat_id)
    elif data == "cmd_prices":
        handle_prices(chat_id)
    elif data == "cmd_chart":
        handle_chart_menu(chat_id)
    elif data == "cmd_twitter":
        handle_twitter_list(chat_id)
    elif data == "cmd_summary":
        handle_summary(chat_id)
    elif data == "cmd_menu":
        handle_start(chat_id)
    elif data.startswith("chart_"):
        symbol = data.replace("chart_", "")
        handle_chart(chat_id, symbol)

# ── Scheduled Tasks ────────────────────────────────────────────────

def check_twitter_feeds():
    """Check all tracked accounts for new tweets and forward them."""
    new_tweets = twitter.check_all_accounts()
    if not new_tweets:
        return
    for handle, tweets in new_tweets.items():
        for tweet in tweets:
            msg = twitter.format_tweet_message(tweet)
            send_message(CHAT_ID, msg)
            time.sleep(0.5)  # avoid rate limits


def send_auto_briefing():
    """Send the scheduled briefing (same as original bot)."""
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

        print("🚀 Crypto News Bot starting...")
        set_bot_commands()
        print("✅ Commands registered")

        # send initial briefing on startup
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
        """Fetch and process new updates."""
        result = tg_request("getUpdates", {"offset": self.offset, "timeout": 30})
        updates = result.get("result", [])

        for update in updates:
            self.offset = update["update_id"] + 1
            try:
                if "message" in update:
                    process_message(update["message"])
                elif "callback_query" in update:
                    process_callback(update["callback_query"])
            except Exception as e:
                print(f"  ⚠️  Update error: {e}")

    def _check_scheduled(self):
        """Run periodic tasks."""
        now = time.time()

        # check twitter every 5 minutes
        if now - self.last_twitter_check >= TWITTER_CHECK_INTERVAL:
            self.last_twitter_check = now
            try:
                check_twitter_feeds()
            except Exception as e:
                print(f"  ⚠️  Twitter check: {e}")

        # auto-briefing every 4 hours
        if now - self.last_briefing >= BRIEFING_INTERVAL:
            self.last_briefing = now
            try:
                send_auto_briefing()
            except Exception as e:
                print(f"  ⚠️  Briefing: {e}")
