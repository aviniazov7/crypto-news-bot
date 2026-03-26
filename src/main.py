"""
Crypto News → Telegram Pipeline
GitHub Actions (free, 24/7)
RSS + CoinGecko + Google Translate → Telegram
Zero dependencies — Python stdlib only.
"""

import json
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from html import unescape
import re
import os
import sys

RSS_FEEDS = [
    {"name": "CoinDesk",         "url": "https://www.coindesk.com/arc/outboundfeeds/rss/"},
    {"name": "CoinTelegraph",    "url": "https://cointelegraph.com/rss"},
    {"name": "Bitcoin Magazine",  "url": "https://bitcoinmagazine.com/feed"},
    {"name": "The Block",        "url": "https://www.theblock.co/rss.xml"},
    {"name": "Decrypt",          "url": "https://decrypt.co/feed"},
]

COINS = "bitcoin,ethereum,solana,binancecoin,ripple"
COIN_SYMBOLS = [
    ("bitcoin", "BTC"), ("ethereum", "ETH"), ("solana", "SOL"),
    ("binancecoin", "BNB"), ("ripple", "XRP"),
]
HOURS_BACK = 8
MAX_PER_SOURCE = 3
ISRAEL_TZ = timezone(timedelta(hours=3))

def http_get(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": "CryptoNewsPipeline/2.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()

def clean_html(text):
    return re.sub(r"<[^>]+>", "", text).strip()

def parse_date(raw):
    if not raw: return None
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z",
                "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ",
                "%Y-%m-%dT%H:%M:%S.%f%z"):
        try:
            dt = datetime.strptime(raw.strip(), fmt)
            return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
        except ValueError: continue
    return None

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
        if not title or not link: continue
        if pub and pub < cutoff: continue
        if len(desc) > 300: desc = desc[:297] + "..."
        items.append({"title": title, "desc": desc, "source": feed["name"], "date": pub})
    if not items:
        ns = {"a": "http://www.w3.org/2005/Atom"}
        for el in root.findall(".//a:entry", ns):
            title = unescape(el.findtext("a:title", "", ns).strip())
            link_el = el.find("a:link", ns)
            link = link_el.get("href", "") if link_el is not None else ""
            summary = clean_html(unescape(el.findtext("a:summary", "", ns)))
            pub = parse_date(el.findtext("a:published", "", ns))
            if not title or not link: continue
            if pub and pub < cutoff: continue
            if len(summary) > 300: summary = summary[:297] + "..."
            items.append({"title": title, "desc": summary, "source": feed["name"], "date": pub})
    return items[:MAX_PER_SOURCE]

def fetch_prices():
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={COINS}&vs_currencies=usd&include_24hr_change=true"
    try: return json.loads(http_get(url))
    except Exception as e:
        print(f"  ⚠️  CoinGecko: {e}")
        return {}

def send_telegram(token, chat_id, text):
    payload = json.dumps({"chat_id": chat_id, "text": text, "disable_web_page_preview": True}).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            if result.get("ok"):
                print("✅ Telegram: sent!")
                return True
            print(f"❌ Telegram: {result.get('description')}")
    except Exception as e:
        print(f"❌ Telegram: {e}")
    return False

def translate_he(text):
    try:
        encoded = urllib.parse.quote(text[:300])
        url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=he&dt=t&q={encoded}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            return "".join(p[0] for p in data[0] if p[0])
    except: return text

def wrap_text(text, width=38):
    """Break long text into lines of ~width chars at word boundaries."""
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

def build_message(news, prices):
    now = datetime.now(ISRAEL_TZ)
    L = []

    L.append("┌─────────────────────┐")
    L.append(f"   📊  סקירת קריפטו יומית")
    L.append(f"   {now.strftime('%d.%m.%Y')}  |  {now.strftime('%H:%M')}")
    L.append("└─────────────────────┘")
    L.append("")

    # ── מצב שוק ──
    if prices:
        changes = []
        for cg_id, sym in COIN_SYMBOLS:
            d = prices.get(cg_id)
            if d: changes.append(d.get("usd_24h_change", 0))

        avg_change = sum(changes) / len(changes) if changes else 0
        if avg_change <= -5:
            mood = "🔴 השוק אדום — ירידות חדות"
        elif avg_change <= -2:
            mood = "🟠 השוק בירידה מתונה"
        elif avg_change <= 0:
            mood = "🟡 השוק יציב עם ירידות קלות"
        elif avg_change <= 3:
            mood = "🟢 השוק ירוק — עליות קלות"
        else:
            mood = "🟢 השוק ירוק — עליות חדות"
        L.append(mood)
        L.append("")

        for cg_id, sym in COIN_SYMBOLS:
            d = prices.get(cg_id)
            if not d: continue
            p, ch = d["usd"], d.get("usd_24h_change", 0)
            arrow = "▲" if ch >= 0 else "▼"
            ps = f"${p:,.0f}" if p >= 1000 else f"${p:,.2f}" if p >= 1 else f"${p:.4f}"
            L.append(f"  {arrow} {sym}  {ps}  ({ch:+.1f}%)")
        L.append("")

    # ── חדשות ──
    if news:
        L.append("╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌")
        L.append("📰  מה חדש היום:")
        L.append("")

        for i, item in enumerate(news[:6], 1):
            title_he = translate_he(item["title"])
            if len(title_he) > 80:
                title_he = title_he[:77] + "..."

            L.append(f"  {i}. {title_he}")

            if item.get("desc") and len(item["desc"]) > 30:
                desc_he = translate_he(item["desc"])
                desc_lines = wrap_text(desc_he, 40)
                for line in desc_lines[:4]:
                    L.append(f"     {line}")

            L.append(f"     [{item['source']}]")
            L.append("")

    L.append("╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌")
    L.append("🤖 סקירה אוטומטית • כל 4 שעות")

    return "\n".join(L)

def main():
    print("🚀 Crypto News Pipeline\n")
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        print("❌ Missing TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID")
        sys.exit(1)

    print("💰 Fetching prices...")
    prices = fetch_prices()

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

    print(f"📊 {len(unique)} unique headlines")
    msg = build_message(unique, prices)
    send_telegram(token, chat_id, msg)
    print("✅ Done!")

if __name__ == "__main__":
    main()
