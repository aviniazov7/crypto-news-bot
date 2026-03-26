"""
Crypto News → Telegram Pipeline
Runs on GitHub Actions (free, 24/7)

Sources (all free, no API keys):
  - RSS: CoinDesk, CoinTelegraph, Bitcoin Magazine, The Block, Decrypt
  - CoinGecko: prices + 24h change
  - Telegram Bot API: delivery

Zero pip dependencies — Python standard library only.
"""

import json
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from html import unescape
import re
import os
import sys

# ─── CONFIG ────────────────────────────────────────────────────

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
MAX_HEADLINES = 10
ISRAEL_TZ = timezone(timedelta(hours=3))


def http_get(url: str, timeout: int = 15) -> bytes:
    req = urllib.request.Request(url, headers={
        "User-Agent": "CryptoNewsPipeline/2.0 (GitHub Actions)"
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def clean_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).strip()


def parse_date(raw: str) -> datetime | None:
    if not raw:
        return None
    raw = raw.strip()
    for fmt in (
        "%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z",
        "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%d %H:%M:%S",
    ):
        try:
            dt = datetime.strptime(raw, fmt)
            return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
        except ValueError:
            continue
    return None


def scrape_feed(feed: dict, cutoff: datetime) -> list[dict]:
    try:
        xml_bytes = http_get(feed["url"])
        xml_text = xml_bytes.decode("utf-8", errors="replace")
    except Exception as e:
        print(f"  ⚠️  {feed['name']}: fetch failed — {e}")
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
        if len(desc) > 140:
            desc = desc[:137] + "..."
        items.append({"title": title, "url": link, "desc": desc,
                       "source": feed["name"], "date": pub})

    if not items:
        ns = {"a": "http://www.w3.org/2005/Atom"}
        for el in root.findall(".//a:entry", ns):
            title = unescape(el.findtext("a:title", "", ns).strip())
            link_el = el.find("a:link", ns)
            link = link_el.get("href", "") if link_el is not None else ""
            pub = parse_date(el.findtext("a:published", "", ns))
            summary = clean_html(unescape(el.findtext("a:summary", "", ns)))
            if not title or not link:
                continue
            if pub and pub < cutoff:
                continue
            if len(summary) > 140:
                summary = summary[:137] + "..."
            items.append({"title": title, "url": link, "desc": summary,
                           "source": feed["name"], "date": pub})

    return items[:MAX_PER_SOURCE]


def fetch_prices() -> dict:
    url = (f"https://api.coingecko.com/api/v3/simple/price"
           f"?ids={COINS}&vs_currencies=usd&include_24hr_change=true")
    try:
        return json.loads(http_get(url))
    except Exception as e:
        print(f"  ⚠️  CoinGecko error: {e}")
        return {}


def send_telegram(token: str, chat_id: str, text: str) -> bool:
    payload = json.dumps({
        "chat_id": chat_id, "text": text,
        "parse_mode": "HTML", "disable_web_page_preview": True,
    }).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload, headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            if result.get("ok"):
                print("✅ Telegram: sent!")
                return True
            print(f"❌ Telegram: {result.get('description')}")
            return False
    except Exception as e:
        print(f"❌ Telegram: {e}")
        return False


def build_message(news: list[dict], prices: dict) -> str:
    now = datetime.now(ISRAEL_TZ)
    t = now.strftime("%d/%m %H:%M")
    msg = f"⚡️ <b>Crypto Briefing</b>  |  {t}\n"
    msg += "━━━━━━━━━━━━━━━━━━━━━━\n\n"

    if prices:
        msg += "💰 <b>Prices</b>\n"
        for cg_id, sym in COIN_SYMBOLS:
            d = prices.get(cg_id)
            if not d:
                continue
            p = d.get("usd", 0)
            ch = d.get("usd_24h_change", 0)
            arrow = "🟢" if ch >= 0 else "🔴"
            if p >= 1000:
                ps = f"${p:,.0f}"
            elif p >= 1:
                ps = f"${p:,.2f}"
            else:
                ps = f"${p:.4f}"
            msg += f"  {arrow} <code>{sym:>4}</code>  {ps}  ({ch:+.1f}%)\n"
        msg += "\n"

    if news:
        msg += "📰 <b>Headlines</b>\n\n"
        for i, item in enumerate(news[:MAX_HEADLINES], 1):
            title = item["title"]
            if len(title) > 90:
                title = title[:87] + "..."
            msg += f"{i}.  <b>{title}</b>\n"
            msg += f"     📌 {item['source']}"
            if item.get("desc"):
                desc = item["desc"]
                if len(desc) > 120:
                    desc = desc[:117] + "..."
                msg += f"  •  {desc}"
            msg += "\n\n"

    msg += "━━━━━━━━━━━━━━━━━━━━━━\n"
    msg += "🤖 GitHub Actions  •  RSS + CoinGecko  •  $0/mo"
    return msg


def main():
    print("🚀 Crypto News Pipeline (GitHub Actions)\n")
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        print("❌ Missing secrets: TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID")
        sys.exit(1)

    print("💰 Fetching prices...")
    prices = fetch_prices()
    print(f"   {len(prices)} coins\n")

    cutoff = datetime.now(timezone.utc) - timedelta(hours=HOURS_BACK)
    all_news: list[dict] = []
    for feed in RSS_FEEDS:
        print(f"📡 {feed['name']}...")
        items = scrape_feed(feed, cutoff)
        all_news.extend(items)
        print(f"   {len(items)} items")

    all_news.sort(
        key=lambda x: x.get("date") or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )

    seen: set[str] = set()
    unique: list[dict] = []
    for item in all_news:
        key = item["title"].lower()[:50]
        if key not in seen:
            seen.add(key)
            unique.append(item)

    print(f"\n📊 Unique headlines: {len(unique)}")
    msg = build_message(unique, prices)
    print(f"📝 Message: {len(msg)} chars\n")
    send_telegram(token, chat_id, msg)
    print("\n✅ Done!")


if __name__ == "__main__":
    main()
