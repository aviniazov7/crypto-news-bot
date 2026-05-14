"""
RSS news scraping, CoinGecko prices, Google Translate, message formatting.
Extracted from the original main.py pipeline.
"""

import json
import os
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from html import unescape
import re

# ── Config ──────────────────────────────────────────────────────────
RSS_FEEDS = [
    {"name": "CoinDesk",         "url": "https://www.coindesk.com/arc/outboundfeeds/rss/"},
    {"name": "CoinTelegraph",    "url": "https://cointelegraph.com/rss"},
    {"name": "Bitcoin Magazine",  "url": "https://bitcoinmagazine.com/feed"},
    {"name": "The Block",        "url": "https://www.theblock.co/rss.xml"},
    {"name": "Decrypt",          "url": "https://decrypt.co/feed"},
]

COINS = "bitcoin,ethereum,binancecoin,solana,ripple,cardano,dogecoin,tron,avalanche-2,chainlink"
COIN_SYMBOLS = [
    ("bitcoin", "BTC"), ("ethereum", "ETH"), ("binancecoin", "BNB"),
    ("solana", "SOL"), ("ripple", "XRP"), ("cardano", "ADA"),
    ("dogecoin", "DOGE"), ("tron", "TRX"), ("avalanche-2", "AVAX"),
    ("chainlink", "LINK"),
]
HOURS_BACK = 8
MAX_PER_SOURCE = 3
ISRAEL_TZ = timezone(timedelta(hours=3))

# ── Helpers ─────────────────────────────────────────────────────────

def http_get(url, timeout=15, extra_headers=None):
    headers = {"User-Agent": "CryptoNewsPipeline/2.0"}
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def clean_html(text):
    return re.sub(r"<[^>]+>", "", text).strip()


def parse_date(raw):
    if not raw:
        return None
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z",
                "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ",
                "%Y-%m-%dT%H:%M:%S.%f%z"):
        try:
            dt = datetime.strptime(raw.strip(), fmt)
            return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
        except ValueError:
            continue
    return None


def translate_he(text):
    try:
        encoded = urllib.parse.quote(text[:300])
        url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=he&dt=t&q={encoded}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            return "".join(p[0] for p in data[0] if p[0])
    except Exception:
        return text


def wrap_text(text, width=38):
    words = text.split()
    lines, current = [], ""
    for word in words:
        if current and len(current) + len(word) + 1 > width:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}" if current else word
    if current:
        lines.append(current)
    return lines

# ── RSS Scraping ────────────────────────────────────────────────────

def scrape_feed(feed, cutoff):
    try:
        xml_text = http_get(feed["url"]).decode("utf-8", errors="replace")
    except Exception as e:
        print(f"  ⚠️  {feed['name']}: {e}")
        return []
    root = ET.fromstring(xml_text)
    items = []
    for el in root.findall(".//item"):
        title = unescape(el.findtext("title", "").strip())
        link = el.findtext("link", "").strip()
        desc = clean_html(unescape(el.findtext("description", "")))
        pub = parse_date(el.findtext("pubDate", ""))
        if not title or not link:
            continue
        if pub and pub < cutoff:
            continue
        if len(desc) > 300:
            desc = desc[:297] + "..."
        items.append({"title": title, "desc": desc, "source": feed["name"], "date": pub})
    if not items:
        ns = {"a": "http://www.w3.org/2005/Atom"}
        for el in root.findall(".//a:entry", ns):
            title = unescape(el.findtext("a:title", "", ns).strip())
            link_el = el.find("a:link", ns)
            link = link_el.get("href", "") if link_el is not None else ""
            summary = clean_html(unescape(el.findtext("a:summary", "", ns)))
            pub = parse_date(el.findtext("a:published", "", ns))
            if not title or not link:
                continue
            if pub and pub < cutoff:
                continue
            if len(summary) > 300:
                summary = summary[:297] + "..."
            items.append({"title": title, "desc": summary, "source": feed["name"], "date": pub})
    return items[:MAX_PER_SOURCE]


def fetch_all_news():
    """Fetch news from all RSS feeds, deduplicate, sort by date."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=HOURS_BACK)
    all_news = []
    for feed in RSS_FEEDS:
        print(f"📡 {feed['name']}...")
        all_news.extend(scrape_feed(feed, cutoff))
    all_news.sort(key=lambda x: x.get("date") or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    seen, unique = set(), []
    for item in all_news:
        key = item["title"].lower()[:50]
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique

# ── CoinGecko Prices ───────────────────────────────────────────────

def _cg_headers():
    """Get CoinGecko API headers."""
    cg_key = os.environ.get("COINGECKO_API_KEY", "")
    if cg_key:
        return {"x-cg-demo-api-key": cg_key}
    return {}


def fetch_prices():
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={COINS}&vs_currencies=usd&include_24hr_change=true"
    try:
        return json.loads(http_get(url, extra_headers=_cg_headers()))
    except Exception as e:
        print(f"  ⚠️  CoinGecko: {e}")
        return {}

# ── Message Building ───────────────────────────────────────────────

def build_briefing(news, prices):
    """Build the full briefing message (same format as before)."""
    now = datetime.now(ISRAEL_TZ)
    R = "\u200F"
    L = []

    L.append(f"{R}📊 סקירת קריפטו | {now.strftime('%d.%m.%Y')} | {now.strftime('%H:%M')}")
    L.append("")

    if prices:
        changes = [prices[c].get("usd_24h_change", 0) for c in prices]
        avg = sum(changes) / len(changes) if changes else 0
        if avg <= -5:
            mood = "🔴 יום אדום בשוק — ירידות חדות"
        elif avg <= -2:
            mood = "🟠 השוק בירידה מתונה"
        elif avg <= 0:
            mood = "🟡 השוק יציב — ירידות קלות"
        elif avg <= 3:
            mood = "🟢 השוק ירוק — עליות"
        else:
            mood = "🟢 עליות חדות בשוק"
        L.append(f"{R}{mood}")
        L.append("")

        for cg_id, sym in COIN_SYMBOLS:
            d = prices.get(cg_id)
            if not d:
                continue
            p, ch = d["usd"], d.get("usd_24h_change", 0)
            arrow = "▲" if ch >= 0 else "▼"
            ps = f"${p:,.0f}" if p >= 1000 else f"${p:,.2f}" if p >= 1 else f"${p:.4f}"
            L.append(f"{R}  {arrow} {sym}  {ps}  ({ch:+.1f}%)")
        L.append("")

    if news:
        L.append(f"{R}📰 מה חדש היום:")
        L.append("")

        for i, item in enumerate(news[:5], 1):
            title_he = translate_he(item["title"])
            if len(title_he) > 85:
                title_he = title_he[:82] + "..."
            L.append(f"{R}{i}. {title_he}")

            if item.get("desc") and len(item["desc"]) > 30:
                desc_he = translate_he(item["desc"])
                for line in wrap_text(desc_he, 42)[:4]:
                    L.append(f"{R}   {line}")

            L.append(f"{R}   [{item['source']}]")
            L.append("")

    return "\n".join(L)


def build_prices_message(prices):
    """Build a prices-only message."""
    R = "\u200F"
    now = datetime.now(ISRAEL_TZ)
    L = [f"{R}💰 מחירים | {now.strftime('%H:%M')}", ""]

    if not prices:
        L.append(f"{R}⚠️ לא הצלחתי לטעון מחירים כרגע")
        return "\n".join(L)

    changes = [prices[c].get("usd_24h_change", 0) for c in prices]
    avg = sum(changes) / len(changes) if changes else 0
    if avg <= -5:
        mood = "🔴 יום אדום"
    elif avg <= -2:
        mood = "🟠 ירידה מתונה"
    elif avg <= 0:
        mood = "🟡 יציב"
    elif avg <= 3:
        mood = "🟢 עליות"
    else:
        mood = "🟢 עליות חדות"
    L.append(f"{R}{mood}")
    L.append("")

    for cg_id, sym in COIN_SYMBOLS:
        d = prices.get(cg_id)
        if not d:
            continue
        p, ch = d["usd"], d.get("usd_24h_change", 0)
        arrow = "▲" if ch >= 0 else "▼"
        ps = f"${p:,.0f}" if p >= 1000 else f"${p:,.2f}" if p >= 1 else f"${p:.4f}"
        L.append(f"{R}  {arrow} {sym}  {ps}  ({ch:+.1f}%)")

    return "\n".join(L)


def build_news_message(news):
    """Build a news-only message."""
    R = "\u200F"
    now = datetime.now(ISRAEL_TZ)
    L = [f"{R}📰 חדשות אחרונות | {now.strftime('%H:%M')}", ""]

    if not news:
        L.append(f"{R}אין חדשות חדשות כרגע")
        return "\n".join(L)

    for i, item in enumerate(news[:5], 1):
        title_he = translate_he(item["title"])
        if len(title_he) > 85:
            title_he = title_he[:82] + "..."
        L.append(f"{R}{i}. {title_he}")

        if item.get("desc") and len(item["desc"]) > 30:
            desc_he = translate_he(item["desc"])
            for line in wrap_text(desc_he, 42)[:4]:
                L.append(f"{R}   {line}")

        L.append(f"{R}   [{item['source']}]")
        L.append("")

    return "\n".join(L)
