"""
Simple JSON file persistence for Twitter account tracking.
Stores tracked accounts and seen tweet IDs to avoid duplicates.
"""

import json
import os
import threading

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
TRACKING_FILE = os.path.join(DATA_DIR, "tracking.json")
MAX_SEEN_PER_ACCOUNT = 100  # keep last N tweet IDs per account

_lock = threading.Lock()


def _ensure_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


def _load():
    _ensure_dir()
    if not os.path.exists(TRACKING_FILE):
        return {"accounts": [], "seen": {}}
    try:
        with open(TRACKING_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {"accounts": [], "seen": {}}


def _save(data):
    _ensure_dir()
    with open(TRACKING_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def add_account(handle):
    """Add a Twitter handle to track. Returns True if newly added."""
    handle = handle.lower().strip().lstrip("@")
    with _lock:
        data = _load()
        if handle in data["accounts"]:
            return False
        data["accounts"].append(handle)
        data["seen"].setdefault(handle, [])
        _save(data)
    return True


def remove_account(handle):
    """Remove a Twitter handle. Returns True if it existed."""
    handle = handle.lower().strip().lstrip("@")
    with _lock:
        data = _load()
        if handle not in data["accounts"]:
            return False
        data["accounts"].remove(handle)
        data["seen"].pop(handle, None)
        _save(data)
    return True


def list_accounts():
    """Return list of tracked handles."""
    data = _load()
    return list(data["accounts"])


def is_seen(handle, tweet_id):
    """Check if a tweet ID was already seen."""
    handle = handle.lower().strip().lstrip("@")
    data = _load()
    return tweet_id in data["seen"].get(handle, [])


def mark_seen(handle, tweet_id):
    """Mark a tweet ID as seen."""
    handle = handle.lower().strip().lstrip("@")
    with _lock:
        data = _load()
        seen_list = data["seen"].setdefault(handle, [])
        if tweet_id not in seen_list:
            seen_list.append(tweet_id)
            # trim old entries
            if len(seen_list) > MAX_SEEN_PER_ACCOUNT:
                data["seen"][handle] = seen_list[-MAX_SEEN_PER_ACCOUNT:]
            _save(data)


def get_chat_id():
    """Get the saved target chat ID."""
    data = _load()
    return data.get("chat_id", "")


def set_chat_id(chat_id):
    """Save the target chat ID."""
    with _lock:
        data = _load()
        data["chat_id"] = str(chat_id)
        _save(data)
