"""
Twitter/X monitoring via Nitter RSS feeds.
Checks tracked accounts for new tweets and returns them for forwarding.
"""

import re
import urllib.parse
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


def _to_direct_twimg_url(url):
    """Map a Nitter /pic/ proxy URL to the original pbs.twimg.com URL at high quality."""
    m = re.match(r"https?://[^/]+/pic/(?:orig/)?(.+)$", url)
    if not m:
        return url
    path = urllib.parse.unquote(m.group(1))
    direct = f"https://pbs.twimg.com/{path}"
    if "?" not in direct:
        direct += "?name=large"
    return direct


def _strip_news_prefix(text):
    """Drop English news-flash prefixes that Google Translate leaves untranslated."""
    return re.sub(
        r"^\s*(JUST\s+IN:?|BREAKING:?|UPDATE:?|NEW:?|DEVELOPING:?|EXCLUSIVE:?|ALERT:?)\s*",
        "",
        (text or "").strip(),
        flags=re.IGNORECASE,
    )


def _extract_media(html_desc):
    """Extract media (videos/photos) from a Nitter RSS description HTML blob.

    Scans for any URL pointing at MP4 (video) or at Twitter/Nitter image hosts
    (Twitter CDN paths or nitter /pic/ proxies) — more forgiving than parsing
    specific tags, since Nitter's HTML varies. Maps everything back to direct
    pbs.twimg.com URLs at high quality.
    """
    media = []
    skip = ("emoji", "profile_image", "profile_banner")

    for m in re.finditer(r'https?://[^\s"\'<>]+\.mp4[^\s"\'<>]*', html_desc, re.IGNORECASE):
        media.append({"type": "video", "url": m.group(0)})

    if not media:
        seen_urls = set()
        for m in re.finditer(r'https?://[^\s"\'<>]+', html_desc):
            url = m.group(0)
            if not ("/pic/" in url or "pbs.twimg.com" in url):
                continue
            if any(s in url for s in skip):
                continue
            direct = _to_direct_twimg_url(url)
            if direct in seen_urls:
                continue
            seen_urls.add(direct)
            media.append({"type": "photo", "url": direct})

    return media


def _strip_media_placeholder(text):
    """Drop the trailing "Video"/"Image"/"GIF" word Nitter appends in descriptions."""
    return re.sub(r"\s*\b(Video|Image|GIF)\s*$", "", text, flags=re.IGNORECASE).strip()


_MEDIA_NS = {"media": "http://search.yahoo.com/mrss/"}


def _media_from_xml_item(item):
    """Pull media URLs from <media:content> and <enclosure> elements as a fallback."""
    media = []
    for mc in item.findall("media:content", _MEDIA_NS):
        url = mc.get("url", "")
        if not url:
            continue
        kind = "video" if mc.get("medium") == "video" or url.lower().endswith(".mp4") else "photo"
        media.append({"type": kind, "url": _to_direct_twimg_url(url)})
    for enc in item.findall("enclosure"):
        url = enc.get("url", "")
        if not url:
            continue
        t = enc.get("type", "")
        kind = "video" if t.startswith("video") or url.lower().endswith(".mp4") else "photo"
        media.append({"type": kind, "url": _to_direct_twimg_url(url)})
    return media


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
        raw_desc = unescape(item.findtext("description", ""))
        desc = _strip_media_placeholder(clean_html(raw_desc))
        media = _extract_media(raw_desc) or _media_from_xml_item(item)
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
            "media": media,
        })

    return tweets


def check_account(handle):
    """Check a single account for new tweets, skipping near-duplicates by text."""
    xml_text = _fetch_nitter_rss(handle)
    if not xml_text:
        return []

    tweets = _parse_tweets(handle, xml_text)
    new_tweets = []

    for tweet in tweets:
        if storage.is_seen(handle, tweet["id"]):
            continue
        storage.mark_seen(handle, tweet["id"])
        text = tweet.get("text", "")
        if storage.has_recent_text(handle, text):
            continue  # same story re-tweeted in a thread — silently skip
        storage.add_recent_text(handle, text)
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
    raw_text = _strip_news_prefix(tweet.get("text") or "")
    text_he = translate_he(raw_text[:500]) if raw_text else ""
    return f"{R}{text_he or '(ללא טקסט)'}"


def init_account(handle):
    """Initialize tracking for an account - mark existing tweets as seen so we only forward NEW ones."""
    xml_text = _fetch_nitter_rss(handle)
    if not xml_text:
        return False

    tweets = _parse_tweets(handle, xml_text)
    for tweet in tweets:
        storage.mark_seen(handle, tweet["id"])
    return True
