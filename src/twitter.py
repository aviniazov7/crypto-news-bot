"""
Twitter/X monitoring via Nitter RSS feeds.
Checks tracked accounts for new tweets and returns them for forwarding.
"""

import re
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import timedelta, timezone
from html import unescape

from news import http_get, clean_html, parse_date, translate_he, bidi_fix, is_crypto_relevant_ai
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
    """Clean Nitter description noise: cut the embedded quoted/retweeted block
    (placeholder + author handle) and drop standalone Video/Image/GIF tokens."""
    text = text or ""
    # Quoted-tweet block looks like "... Video <Name> (@handle) ..." — cut it.
    text = re.split(
        r"\b(?:Video|Image|GIF)\b\s+[^\n]{0,50}?\(@[\w]{1,30}\)",
        text,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    # Drop any remaining standalone placeholder tokens.
    text = re.sub(r"\b(Video|Image|GIF)\b", " ", text, flags=re.IGNORECASE)
    return re.sub(r"\s{2,}", " ", text).strip()


_PROMO_PATTERNS = (
    r"join\s+(?:our|the|my)\s+(?:discord|telegram|server|channel|group|community|vip|premium)",
    r"join\s+(?:us\s+)?(?:on\s+)?(?:discord|telegram)",
    r"link\s+in\s+bio",
    r"\bdm\s+(?:me|us|for|to)\b",
    r"\b(?:sign\s*up|subscribe|register)\b.*\b(?:now|today|here|link|free)\b",
    r"\b(?:giveaway|airdrop|free\s+(?:crypto|nft|tokens?|mint))\b",
    r"\bclaim\s+your\b",
    r"\b(?:vip|premium)\s+(?:signals?|group|access|membership)\b",
    r"\b(?:trading|crypto)\s+signals?\b",
    r"\buse\s+(?:promo\s+|referral\s+)?code\b",
    r"\b(?:referral|affiliate)\s+(?:link|code)\b",
    r"\blimited\s+(?:time|offer|spots?)\b",
    r"\bfollow\s+(?:us|me|@)\b",
    r"\b(?:t\.me/|discord\.gg/|discord\.com/invite)\b",
    r"\bnot\s+financial\s+advice\b.*\b(?:join|subscribe|signals?)\b",
    r"#ad\b|\bsponsored\b|\bpaid\s+partnership\b",
    # YouTuber / streamer self-promo
    r"\b(?:youtu\.be/|youtube\.com/(?:watch|live|channel|c/|@))",
    r"\bwatch\s+(?:now|here|this|the\s+(?:full\s+)?video)\b",
    r"\b(?:new|latest|fresh)\s+(?:video|upload|episode|stream)\b",
    r"\b(?:check\s+out|watch)\s+my\s+(?:new\s+)?(?:video|channel|stream)\b",
    r"\bsubscribe\s+to\s+my\b",
    r"\b(?:live|streaming)\s+now\b|\bgoing\s+live\b",
    r"\bfull\s+(?:video|analysis|breakdown)\s+(?:here|below|now|on\s+youtube)\b",
    r"\blink\s+(?:below|in\s+(?:the\s+)?(?:comments|replies|thread))\b",
)
_PROMO_RE = re.compile("|".join(_PROMO_PATTERNS), re.IGNORECASE)


def is_promotional(text):
    """Heuristic: True for ads / 'join our discord' / airdrop / signals spam."""
    return bool(_PROMO_RE.search(text or ""))


_CRYPTO_TERMS = (
    # core
    "crypto", "bitcoin", "btc", "ethereum", "eth", "blockchain", "altcoin",
    "stablecoin", "defi", "memecoin", "satoshi", "halving", "on-chain",
    "onchain", "web3", "tokeniz", "wallet", "mining", "miner",
    # major coins / tickers
    "solana", "$sol", "xrp", "ripple", "$bnb", "binance", "cardano", "$ada",
    "dogecoin", "$doge", "tron", "$trx", "avalanche", "$avax", "chainlink",
    "$link", "polkadot", "polygon", "litecoin", "shiba", "pepe", "usdt",
    "usdc", "tether", "$btc", "$eth",
    # exchanges / institutions
    "coinbase", "kraken", "okx", "bybit", "bitget", "microstrategy",
    "grayscale", "blackrock", "circle",
    # finance / macro
    "etf", "sec ", "regulat", "federal reserve", " fed ", "interest rate",
    "inflation", "recession", "nasdaq", "s&p", "treasury", "liquidat",
    "leverage", "futures", "bull market", "bear market", "bullish",
    "bearish", "market cap", "all-time high", "all time high", "rally",
    "selloff", "sell-off", "dump", "pump", "hodl", "stock market",
    "wall street", "gdp", "cpi", "fiat",
)


def is_crypto_relevant(text):
    """True if the tweet mentions a crypto/finance term — used to drop
    off-topic posts (X algorithm, Grok, generic tech) from tracked accounts."""
    t = (text or "").lower()
    return any(term in t for term in _CRYPTO_TERMS)


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
        if is_promotional(text):
            continue  # skip ads / "join our discord" / airdrop spam
        if not is_crypto_relevant(text):
            continue  # fast keyword filter: skip obviously off-topic
        # AI verifier — catches false positives that pass the keyword filter
        # (e.g. political/news posts that happen to mention "rally", "fed", etc.).
        # On AI error/unavailable (None) we trust the keyword filter and let through.
        if is_crypto_relevant_ai(text) is False:
            print(f"  🚫 AI filter dropped off-topic post from @{handle}: {text[:80]}")
            continue
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
    # Telegram photo caption cap is 1024; Hebrew text is ~2x as char-dense as
    # the English source, so cap raw input around 900 and trim final output.
    text_he = translate_he(raw_text[:900]) if raw_text else ""
    if text_he and len(text_he) > 1000:
        text_he = text_he[:1000].rsplit(" ", 1)[0] + "\u2026"
    return f"{R}{bidi_fix(text_he) or '(ללא טקסט)'}"


def init_account(handle):
    """Initialize tracking for an account - mark existing tweets as seen so we only forward NEW ones."""
    xml_text = _fetch_nitter_rss(handle)
    if not xml_text:
        return False

    tweets = _parse_tweets(handle, xml_text)
    for tweet in tweets:
        storage.mark_seen(handle, tweet["id"])
    return True
