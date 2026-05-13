"""
Persistent storage using Render environment variables.
Data survives deploys by saving to Render API as an env var.
Falls back to local file for development.
"""

import json
import os
import threading
import urllib.request

RENDER_API_KEY = os.environ.get("RENDER_API_KEY", "")
RENDER_SERVICE_ID = os.environ.get("RENDER_SERVICE_ID", "")
ENV_VAR_KEY = "TRACKING_DATA"
MAX_SEEN_PER_ACCOUNT = 100

_lock = threading.RLock()
_cache = None  # in-memory cache


def _load():
    global _cache
    with _lock:
        if _cache is None:
            raw = os.environ.get(ENV_VAR_KEY, "")
            if raw:
                try:
                    _cache = json.loads(raw)
                except json.JSONDecodeError:
                    _cache = {}
            else:
                _cache = {}
            _cache.setdefault("accounts", [])
            _cache.setdefault("seen", {})
            _cache.setdefault("groups", {})
        return _cache


def _save(data):
    global _cache
    _cache = data

    if not RENDER_API_KEY or not RENDER_SERVICE_ID:
        return  # local dev: skip API call

    # Persist to Render env var via API
    url = f"https://api.render.com/v1/services/{RENDER_SERVICE_ID}/env-vars/{ENV_VAR_KEY}"
    payload = json.dumps({"value": json.dumps(data, ensure_ascii=False)}).encode("utf-8")
    req = urllib.request.Request(url, data=payload, method="PUT", headers={
        "Authorization": f"Bearer {RENDER_API_KEY}",
        "Content-Type": "application/json",
    })
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print(f"  ⚠️  Failed to persist data: {e}")


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
            if len(seen_list) > MAX_SEEN_PER_ACCOUNT:
                data["seen"][handle] = seen_list[-MAX_SEEN_PER_ACCOUNT:]
            _save(data)


def add_group(chat_id, name="", topic_id=None):
    """Add/update a group. Returns True if newly added."""
    with _lock:
        data = _load()
        groups = data.setdefault("groups", {})
        key = str(chat_id)
        is_new = key not in groups
        groups[key] = {
            "name": name,
            "topic_id": str(topic_id) if topic_id else "",
            "enabled": True,
        }
        _save(data)
    return is_new


def remove_group(chat_id):
    """Remove a group. Returns True if existed."""
    with _lock:
        data = _load()
        groups = data.setdefault("groups", {})
        key = str(chat_id)
        if key in groups:
            del groups[key]
            _save(data)
            return True
    return False


def set_group_enabled(chat_id, enabled):
    """Enable/disable a group."""
    with _lock:
        data = _load()
        groups = data.setdefault("groups", {})
        key = str(chat_id)
        if key in groups:
            groups[key]["enabled"] = enabled
            _save(data)
            return True
    return False


def list_groups():
    """Return dict of all groups: {chat_id: {name, topic_id, enabled}}."""
    data = _load()
    return data.get("groups", {})


def get_enabled_groups():
    """Return list of enabled groups: [(chat_id, topic_id), ...]."""
    groups = list_groups()
    result = []
    for chat_id, info in groups.items():
        if info.get("enabled", True):
            result.append((chat_id, info.get("topic_id", "")))
    return result
