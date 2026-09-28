"""
Persistent storage using Render environment variables.
Data survives deploys by saving to Render API as an env var.
Without RENDER_API_KEY / RENDER_SERVICE_ID (local development) state is kept
in memory only and is lost when the process stops.
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


def _word_set(text):
    """Significant words (>=4 chars) lower-cased — used for similarity matching."""
    import re
    return set(re.findall(r"\b[\w]{4,}\b", (text or "").lower()))


def has_recent_text(handle, text, threshold=0.5, min_shared=4):
    """Return True if a recent tweet from this handle covers the same story.

    Uses the overlap coefficient |A∩B| / min(|A|,|B|) so a one-line "Just in:"
    tweet matches a longer elaboration of the same news, and requires
    `min_shared` overlapping content words so short headlines that share a
    common phrase ("hits all-time high") aren't mistaken for duplicates.
    """
    handle = handle.lower().strip().lstrip("@")
    new_words = _word_set(text)
    if len(new_words) < 3:
        return False
    data = _load()
    for old_text in data.get("recent_texts", {}).get(handle, []):
        old_words = _word_set(old_text)
        if not old_words:
            continue
        shared = len(new_words & old_words)
        if shared < min_shared:
            continue
        smaller = min(len(new_words), len(old_words))
        if smaller and (shared / smaller) >= threshold:
            return True
    return False


def add_recent_text(handle, text):
    """Record a tweet text (truncated to 200 chars) as recently broadcast."""
    handle = handle.lower().strip().lstrip("@")
    if not text or len(text.strip()) < 10:
        return
    snippet = text.strip()[:200]
    with _lock:
        data = _load()
        bucket = data.setdefault("recent_texts", {}).setdefault(handle, [])
        if snippet not in bucket:
            bucket.append(snippet)
            if len(bucket) > 20:
                data["recent_texts"][handle] = bucket[-20:]
            _save(data)


def get_meta(key, default=None):
    """Read a small persistent key (e.g. last briefing slot)."""
    data = _load()
    return data.get("meta", {}).get(key, default)


def set_meta(key, value):
    """Persist a small key that must survive deploys/restarts."""
    with _lock:
        data = _load()
        data.setdefault("meta", {})[key] = value
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
