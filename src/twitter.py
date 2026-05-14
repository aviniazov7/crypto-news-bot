"""
Twitter/X monitoring via Nitter RSS feeds.
Checks tracked accounts for new tweets and returns them for forwarding.
"""

import re
import xml.etree.ElementTree as ET
from datetime import timedelta, timezone
from html import unescape

from news import http_get, clean_html, parse_date, translate_he
import storage

ISRAEL_TZ = timezone(timedelta(hours=3))

NITTER_INSTANCES = [
    "https://nitter.privacydev.net",
    "https://nitter.poast.org",
    "https://nitter.net",
    "https://nitter.cz",
]


def extract_handle_from_url(text):
    """Extract Twitter handle from a URL like https://x.com/whale_alert or twitter.com/whale_alert."""
    m = re.search(r"(?:twitter\.com|x\.com)/(@?[\w]+)", text, re.IGNORECASE)
    if m:
        handle = m.group(1).lstrip("@")
        # skip non-profile paths
        if handle.lower() in ("home", "explore", "search", "settings", "i", "intent"):
            return None
        return handle.lower()
    return None


def extract_tweet_from_url(text):
    """If the URL points to a specific tweet, return (handle, tweet_id). Otherwise None."""
    m = re.search(r"(?:twitter\.com|x\.com)/(@?[\w]+)/status/(\d+)", text, re.IGNORECASE)
    if m:
        return m.group(1).lstrip("@").lower(), m.group(2)
    return None


def fetch_tweet_by_id(handle, tweet_id):
    """Look up a specific tweet in the handle's Nitter RSS feed."""
    xml_text = _fetch_nitter_rss(handle)
    if not xml_text:
        return None
    tweets = _parse_tweets(handle, xml_text)
    for t in tweets:
        if tweet_id in (t.get("link") or "") or tweet_id in (t.get("id") or ""):
            return t
    return None


def _fetch_nitter_rss(handle):
    """Try multiple Nitter instances to get RSS for a handle."""
    for instance in NITTER_INSTANCES:
        url = f"{instance}/{handle}/rss"
        try:
            data = http_get(url, timeout=10)
            xml_text = data.decode("utf-8", errors="replace")
            # basic check that we got valid RSS
            if "<item>" in xml_text or "<entry" in xml_text:
                return xml_text
        except Exception:
            continue
    return None


def _parse_tweets(handle, xml_text):
    """Parse Nitter RSS XML into tweet dicts."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    tweets = []
    for item in root.findall(".//item"):
        title = unescape(item.findtext("title", "").strip())
        link = item.findtext("link", "").strip()
        desc = clean_html(unescape(item.findtext("description", "")))
        pub = parse_date(item.findtext("pubDate", ""))

        if not title and not desc:
            continue

        # use link as unique ID
        tweet_id = link or title[:50]

        # convert nitter link to x.com link
        x_link = link
        for inst in NITTER_INSTANCES:
            if inst in link:
                x_link = link.replace(inst, "https://x.com")
                break

        tweets.append({
            "id": tweet_id,
            "handle": handle,
            "text": desc if desc else title,
            "link": x_link,
            "date": pub,
        })

    return tweets


def check_account(handle):
    """Check a single account for new tweets. Returns list of unseen tweets."""
    xml_text = _fetch_nitter_rss(handle)
    if not xml_text:
        return []

    tweets = _parse_tweets(handle, xml_text)
    new_tweets = []

    for tweet in tweets:
        if not storage.is_seen(handle, tweet["id"]):
            storage.mark_seen(handle, tweet["id"])
            new_tweets.append(tweet)

    return new_tweets


def check_all_accounts():
    """Check all tracked accounts for new tweets. Returns dict: handle → [tweets]."""
    accounts = storage.list_accounts()
    results = {}
    for handle in accounts:
        new_tweets = check_account(handle)
        if new_tweets:
            results[handle] = new_tweets
    return results


def format_tweet_message(tweet):
    """Format a tweet for Telegram."""
    R = "\u200F"
    raw_text = (tweet.get("text") or "").strip()
    text_he = translate_he(raw_text[:500]) if raw_text else ""

    date_str = ""
    pub = tweet.get("date")
    if pub:
        dt = pub.astimezone(ISRAEL_TZ) if pub.tzinfo else pub.replace(tzinfo=timezone.utc).astimezone(ISRAEL_TZ)
        date_str = dt.strftime("%d.%m.%Y  %H:%M")

    lines = [
        f"{R}🐦 ציוץ חדש",
        f"{R}━━━━━━━━━━━━━━━━━━━",
        f"{R}👤 @{tweet['handle']}",
    ]
    if date_str:
        lines.append(f"{R}🕐 {date_str}")
    lines.append("")
    lines.append(f"{R}{text_he or '(ללא טקסט)'}")
    lines.append("")
    lines.append(f"{R}━━━━━━━━━━━━━━━━━━━")
    lines.append(f"{R}🔗 {tweet['link']}")
    return "\n".join(lines)


def init_account(handle):
    """Initialize tracking for an account - mark existing tweets as seen so we only forward NEW ones."""
    xml_text = _fetch_nitter_rss(handle)
    if not xml_text:
        return False

    tweets = _parse_tweets(handle, xml_text)
    for tweet in tweets:
        storage.mark_seen(handle, tweet["id"])
    return True
