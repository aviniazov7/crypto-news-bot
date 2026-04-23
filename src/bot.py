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


def send_message(chat_id, text, topic_id=None):
    payload = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True,
    }
    if topic_id:
        payload["message_thread_id"] = int(topic_id)
    return tg_request("sendMessage", payload)

def set_bot_commands():
    commands = [
        {"command": "setup", "description": "Register this chat"},
        {"command": "send", "description": "Send briefing now"},
        {"command": "list", "description": "Tracked Twitter accounts"},
        {"command": "add", "description": "Track a Twitter account"},
        {"command": "remove", "description": "Untrack a Twitter account"},
        {"command": "groups", "description": "Manage groups"},
    ]
    tg_request("setMyCommands", {"commands": commands})

# ── Admin Check ─────────────────────────────────────────────────────

def is_admin(msg):
    user_id = str(msg.get("from", {}).get("id", ""))
    return user_id == ADMIN_ID

# ── Command Handlers (admin only) ──────────────────────────────────

def handle_start(chat_id, topic_id=None, chat_name=""):
    storage.add_group(chat_id, name=chat_name, topic_id=topic_id)
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
        "/add username — Track Twitter account\n"
        "/remove username — Untrack account\n"
        "/groups — Manage groups\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "🔗 Send any x.com link to auto-track"
    )
    send_message(chat_id, text, topic_id)


def handle_add_twitter(chat_id, handle, topic_id=None):
    if storage.add_account(handle):
        twitter.init_account(handle)
        send_message(chat_id, f"✅ Now tracking @{handle}", topic_id)
    else:
        send_message(chat_id, f"ℹ️ Already tracking @{handle}", topic_id)


def handle_remove_twitter(chat_id, text, topic_id=None):
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        send_message(chat_id, "Usage: /remove @username", topic_id)
        return
    handle = parts[1].strip().lstrip("@").lower()
    if storage.remove_account(handle):
        send_message(chat_id, f"✅ Stopped tracking @{handle}", topic_id)
    else:
        send_message(chat_id, f"⚠️ @{handle} is not tracked", topic_id)


def handle_twitter_list(chat_id, topic_id=None):
    accounts = storage.list_accounts()
    if not accounts:
        send_message(chat_id, "🐦 No tracked accounts\n\nUse /add @username to start tracking", topic_id)
    else:
        lines = ["🐦 Tracked Accounts:", ""]
        for acc in accounts:
            lines.append(f"  • @{acc}")
        lines.append("")
        lines.append("Add: /add @username")
        lines.append("Remove: /remove @username")
        send_message(chat_id, "\n".join(lines), topic_id)


def handle_groups(chat_id, topic_id=None):
    groups = storage.list_groups()
    if not groups:
        send_message(chat_id, "No groups registered.\n\nUse /start in a group to add it.", topic_id)
        return
    lines = ["📡 Registered Groups:", ""]
    for gid, info in groups.items():
        status = "✅" if info.get("enabled", True) else "❌"
        name = info.get("name") or "Unknown"
        tid = info.get("topic_id", "")
        lines.append(f"  {status} {name}")
        lines.append(f"      ID: {gid}")
        if tid:
            lines.append(f"      Topic: {tid}")
    lines.append("")
    lines.append("Enable:  /enable <group_id>")
    lines.append("Disable: /disable <group_id>")
    lines.append("Remove:  /delgroup <group_id>")
    send_message(chat_id, "\n".join(lines), topic_id)


def handle_enable(chat_id, text, topic_id=None):
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        send_message(chat_id, "Usage: /enable <group_id>", topic_id)
        return
    gid = parts[1].strip()
    if storage.set_group_enabled(gid, True):
        send_message(chat_id, f"✅ Group {gid} enabled", topic_id)
    else:
        send_message(chat_id, f"⚠️ Group {gid} not found", topic_id)


def handle_disable(chat_id, text, topic_id=None):
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        send_message(chat_id, "Usage: /disable <group_id>", topic_id)
        return
    gid = parts[1].strip()
    if storage.set_group_enabled(gid, False):
        send_message(chat_id, f"❌ Group {gid} disabled", topic_id)
    else:
        send_message(chat_id, f"⚠️ Group {gid} not found", topic_id)


def handle_delgroup(chat_id, text, topic_id=None):
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        send_message(chat_id, "Usage: /delgroup <group_id>", topic_id)
        return
    gid = parts[1].strip()
    if storage.remove_group(gid):
        send_message(chat_id, f"✅ Group {gid} removed", topic_id)
    else:
        send_message(chat_id, f"⚠️ Group {gid} not found", topic_id)

# ── Message Processing ─────────────────────────────────────────────

def process_message(msg):
    if not is_admin(msg):
        return

    chat_id = msg["chat"]["id"]
    topic_id = msg.get("message_thread_id")
    chat_name = msg["chat"].get("title", "Private")
    text = msg.get("text", "").strip()
    if not text:
        return

    cmd = text.split()[0].lower().split("@")[0]  # strip @botname
    if cmd in ("/start", "/setup"):
        handle_start(chat_id, topic_id, chat_name)
    elif cmd in ("/list", "/twitter"):
        handle_twitter_list(chat_id, topic_id)
    elif cmd == "/add":
        parts = text.split(maxsplit=1)
        if len(parts) >= 2:
            handle = parts[1].strip().lstrip("@").lower()
            handle_add_twitter(chat_id, handle, topic_id)
    elif cmd == "/remove":
        handle_remove_twitter(chat_id, text, topic_id)
    elif cmd == "/send":
        status = send_message(chat_id, "📨 Sending briefing...", topic_id)
        try:
            send_auto_briefing()
        except Exception as e:
            send_message(chat_id, f"⚠️ Error sending briefing: {e}", topic_id)
        # delete the "Sending..." message
        msg_id = status.get("result", {}).get("message_id")
        if msg_id:
            tg_request("deleteMessage", {"chat_id": chat_id, "message_id": msg_id})
    elif cmd == "/groups":
        handle_groups(chat_id, topic_id)
    elif cmd == "/enable":
        handle_enable(chat_id, text, topic_id)
    elif cmd == "/disable":
        handle_disable(chat_id, text, topic_id)
    elif cmd == "/delgroup":
        handle_delgroup(chat_id, text, topic_id)
    # Twitter link detection
    elif "twitter.com/" in text or "x.com/" in text:
        detected = twitter.extract_handle_from_url(text)
        if detected:
            handle_add_twitter(chat_id, detected, topic_id)

# ── Scheduled Tasks ────────────────────────────────────────────────

def send_to_all_groups(text):
    """Send a message to all enabled groups."""
    groups = storage.get_enabled_groups()
    for chat_id, topic_id in groups:
        send_message(chat_id, text, topic_id or None)
        time.sleep(0.3)


def check_twitter_feeds():
    groups = storage.get_enabled_groups()
    if not groups:
        return
    new_tweets = twitter.check_all_accounts()
    if not new_tweets:
        return
    for handle, tweets in new_tweets.items():
        for tweet in tweets:
            msg = twitter.format_tweet_message(tweet)
            send_to_all_groups(msg)
            time.sleep(0.5)


def send_auto_briefing():
    groups = storage.get_enabled_groups()
    if not groups:
        print("⚠️  No groups registered — send /start in a group first")
        return
    print("📨 Sending auto-briefing...")
    prices = news.fetch_prices()
    items = news.fetch_all_news()
    msg = news.build_briefing(items, prices)
    send_to_all_groups(msg)

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
        self._clear_pending()
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

    def _clear_pending(self):
        """Skip old updates queued while bot was offline."""
        result = tg_request("getUpdates", {"offset": 0, "timeout": 0})
        updates = result.get("result", [])
        if updates:
            self.offset = updates[-1]["update_id"] + 1
            print(f"⏭️  Skipped {len(updates)} pending update(s)")

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
