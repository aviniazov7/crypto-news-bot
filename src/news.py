"""
RSS news scraping, CoinGecko prices, Google Translate, message formatting.
Extracted from the original main.py pipeline.
"""

import json
import os
import urllib.request
import urllib.parse
import urllib.error
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


_JARGON_FIXES = (
    # Google translates trading jargon literally — fix the worst offenders.
    ("מכנסיים הקצרים", "שורטים"),
    ("המכנסיים הקצרים", "השורטים"),
    ("מכנסיים קצרים", "שורטים"),
    ("מכנסי קצר", "שורט"),
    ("מכנס קצר", "שורט"),
    ("לקנות את המטבל", "לקנות בירידה"),
    ("קניית המטבל", "קניית הירידה"),
    ("את המטבל", "את הירידה"),
    ("המטבל", "הירידה"),
    ("טבילה", "ירידה"),
    ("שׁוֹרי", "שורי"),
    ("קרקפת ארוכה", "סקאלפ לונג"),
    ("קרקפת קצרה", "סקאלפ שורט"),
    ("קרקופת", "סקאלפ"),
    ("קרקפת", "סקאלפ"),
    ("הרשות הפלסטינית", "פעולת המחיר"),
    ("רשות פלסטינית", "פעולת מחיר"),
    ("גבוה לב", "מינוף גבוה"),
    ("מינוף לב", "מינוף"),
    ("ריבית פתוחה", "פוזיציות פתוחות"),
    ("אסיה נמוך", "שפל אסיה"),
    ("נמוך אסיה", "שפל אסיה"),
    ("אסיה גבוה", "שיא אסיה"),
)


def _fix_he_jargon(text):
    """Replace literal mistranslations of crypto/trading slang."""
    for bad, good in _JARGON_FIXES:
        text = text.replace(bad, good)
    return text


def _has_hebrew(text):
    return any("֐" <= ch <= "׿" for ch in (text or ""))


def _google_translate_he(text):
    for attempt in range(3):
        try:
            encoded = urllib.parse.quote(text[:900])
            url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=he&dt=t&q={encoded}"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
                out = _fix_he_jargon("".join(p[0] for p in data[0] if p[0]))
                if _has_hebrew(out):
                    return out
        except Exception as e:
            print(f"  ⚠️  Google translate attempt {attempt + 1} failed: {e}")
    return None


_GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")
_GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash-lite")


def _gemini_translate_he(text):
    """Translate to Hebrew via Gemini with correct crypto/trading terminology."""
    prompt = (
        "You are a professional crypto/finance editor. Rewrite the text below "
        "in clear, fluent, professional Hebrew as a finance desk would phrase "
        "it — not a literal machine translation. Keep it concise and natural.\n"
        "Rules:\n"
        "- Translate EVERYTHING into Hebrew, including capitalized/Title-Case "
        "phrases, headlines, and trading jargon. Do NOT leave English words "
        "untranslated just because they look like a name or are capitalized. "
        "The ONLY things that stay in English are listed below.\n"
        "- Trading terms: short(s)=שורט/שורטים, long(s)=לונג/לונגים, "
        "buy the dip=קניית הירידה, pump=פאמפ, dump=מפולת, bullish=שורי, "
        "bearish=דובי, scalp/scalping=סקאלפ (NEVER קרקפת), long scalp=סקאלפ לונג.\n"
        "- Trading abbreviations: 'PA'=פעולת מחיר (price action, NEVER "
        "'הרשות הפלסטינית'), 'lev'/'leverage'=מינוף (NEVER 'לב'/heart), "
        "'high lev'=מינוף גבוה, 'liq'/'liquidation'=חיסול, "
        "'liquidation hunt(s)'=ציד חיסולים, 'MM'/'MMs'/\"MM's\"/'market maker(s)'"
        "=עושי שוק, 'OI'=פוזיציות פתוחות, 'spot'=ספוט, 'delta'=דלתא, "
        "'perp(s)'/'perpetual(s)'=פרפס (חוזים עתידיים), 'oil'=נפט, "
        "'longs'=לונגים, 'shorts'=שורטים, 'peace deal'=הסכם שלום, "
        "'7D'=7 ימים, 'docket'=על הפרק, "
        "'open interest'=פוזיציות פתוחות (NEVER 'ריבית פתוחה'), "
        "'Asia/London/NY low'=שפל מושב אסיה/לונדון/ניו-יורק (NEVER literal "
        "'אסיה נמוך'), 'Asia/London/NY high'=שיא מושב אסיה/לונדון/ניו-יורק, "
        "'LTF'=טווח זמן קצר, 'HTF'=טווח זמן ארוך, 'FVG'=פער FVG, "
        "'overextension'=מתיחת יתר, 'pivot'=נקודת היפוך, "
        "'True Retail Longs'/'TRL'=לונגים קמעונאיים אמיתיים, "
        "'1R'/'2R'=יחס סיכון (1R/2R, keep number).\n"
        "- Keep in English ONLY: ticker symbols ($BTC, ETH), prices/numbers "
        "(76k, $76,672), and the acronyms 'TWAP'/'VWAP'/'CVD'.\n"
        "- Output ONLY the Hebrew text, no quotes, notes, or preamble.\n\n"
        f"{text}"
    )
    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 1024},
    }).encode("utf-8")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{_GEMINI_MODEL}:generateContent?key={_GEMINI_KEY}"
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read().decode())
        parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
        out = (parts[0].get("text", "") if parts else "").strip()
        if not out:
            raise ValueError("empty Gemini response")
        return out


def translate_he(text):
    if not text:
        return text
    # Primary: Gemini. Accept only if it actually produced Hebrew.
    if _GEMINI_KEY:
        try:
            out = _fix_he_jargon(_gemini_translate_he(text))
            if _has_hebrew(out):
                return out
            print("  ⚠️  Gemini returned non-Hebrew output, trying Google")
        except Exception as e:
            print(f"  ⚠️  Gemini translate failed, trying Google: {e}")
    # Fallback: Google Translate (with retries).
    out = _google_translate_he(text)
    if out and _has_hebrew(out):
        return out
    # Both engines failed — return original rather than nothing.
    print("  ⚠️  All translation engines failed; sending original text")
    return text


def translation_health():
    """Probe both translation engines live. Returns a dict for /health."""
    result = {"gemini_key_set": bool(_GEMINI_KEY), "model": _GEMINI_MODEL}
    # Gemini
    if _GEMINI_KEY:
        try:
            out = _gemini_translate_he("Bitcoin is pumping hard today")
            result["gemini"] = "ok" if _has_hebrew(out) else "no-hebrew"
        except urllib.error.HTTPError as e:
            result["gemini"] = f"HTTP {e.code}" + (" (quota)" if e.code == 429 else "")
        except Exception as e:
            result["gemini"] = f"error: {type(e).__name__}"
    else:
        result["gemini"] = "no-key"
    # Google
    try:
        out = _google_translate_he("Bitcoin is pumping hard today")
        result["google"] = "ok" if (out and _has_hebrew(out)) else "failed"
    except Exception as e:
        result["google"] = f"error: {type(e).__name__}"
    return result


def is_crypto_relevant_ai(text):
    """Ask Gemini whether a tweet is crypto/finance/markets-relevant.
    Returns True/False/None (None = AI unavailable or errored — caller decides)."""
    text = (text or "").strip()
    if not text or not _GEMINI_KEY:
        return None
    prompt = (
        "You are a strict relevance AND quality filter for a crypto/finance "
        "news bot. Answer with a single word: YES or NO.\n"
        "YES if the post delivers real crypto/finance/markets substance: news, "
        "data, price levels, technical analysis, on-chain info, macro events, "
        "regulation, exchange/institution activity, or a concrete market "
        "take with actual information.\n"
        "NO if the post is: off-topic (politics, war, crime, sports, "
        "entertainment, personal life, generic tech), OR a low-value post with "
        "no real market info — a meme, joke, sarcastic/satirical 'playbook', "
        "rage-bait, vague hype, a 'gm'/'wagmi' one-liner, or pure commentary "
        "with no concrete data even if it mentions crypto.\n\n"
        f"Post:\n{text[:800]}\n\nAnswer (YES or NO):"
    )
    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.0, "maxOutputTokens": 4},
    }).encode("utf-8")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{_GEMINI_MODEL}:generateContent?key={_GEMINI_KEY}"
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
            out = (parts[0].get("text", "") if parts else "").strip().upper()
            if out.startswith("YES"):
                return True
            if out.startswith("NO"):
                return False
            return None
    except Exception as e:
        print(f"  ⚠️  Gemini relevance check failed: {e}")
        return None


_LTR_RUN_RE = re.compile(
    r"[A-Za-z0-9$][A-Za-z0-9 $%&@#.,:/_+()'\"-]*[A-Za-z0-9%)]|[A-Za-z0-9$]"
)


def bidi_fix(text):
    """Wrap Latin/number/symbol runs in LTR isolates so mixed Hebrew+English
    keeps the right visual order in Telegram (e.g. '$BTC', '8 SLD', '82K')."""
    LRI, PDI = "⁦", "⁩"
    return _LTR_RUN_RE.sub(lambda m: f"{LRI}{m.group(0)}{PDI}", text or "")


def _clean_rss_desc(desc, title, source):
    """Strip RSS quirks from a description: source prefix, title duplication,
    "The post X appeared first on Y" feed signatures, collapse whitespace."""
    if not desc:
        return ""
    desc = desc.strip()
    if source and desc.lower().startswith(source.lower()):
        desc = desc[len(source):].strip()
    if title and desc.lower().startswith(title.lower()):
        desc = desc[len(title):].strip()
    desc = re.sub(
        r"(?:The\s+post|Post|Article)\s+.+?(?:appeared first on|first appeared on).*$",
        "",
        desc,
        flags=re.IGNORECASE | re.DOTALL,
    ).strip()
    # Also catch "Originally published by/on/at ..." footers
    desc = re.sub(
        r"\bOriginally\s+(?:published|appeared)\s+(?:by|on|at|in)\b.*$",
        "",
        desc,
        flags=re.IGNORECASE | re.DOTALL,
    ).strip()
    desc = re.sub(r"\s+", " ", desc)
    return desc


def smart_trim(text, max_len=400):
    """Trim text to max_len, ending at a sentence or word boundary if possible."""
    if len(text) <= max_len:
        return text
    snippet = text[:max_len]
    for marker in (". ", "! ", "? "):
        idx = snippet.rfind(marker)
        if idx > max_len * 0.6:
            return snippet[: idx + 1]
    idx = snippet.rfind(" ")
    if idx > max_len * 0.6:
        return snippet[:idx]
    return snippet


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

# ── Relevance filter (shared by RSS news and Twitter) ───────────────

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
    "grayscale", "blackrock", "circle", "ftx",
    # finance / macro
    "etf", "sec ", "regulat", "federal reserve", " fed ", "interest rate",
    "inflation", "recession", "nasdaq", "s&p", "treasury", "liquidat",
    "leverage", "futures", "bull market", "bear market", "bullish",
    "bearish", "market cap", "all-time high", "all time high", "rally",
    "selloff", "sell-off", "dump", "pump", "hodl", "stock market",
    "wall street", "gdp", "cpi", "fiat",
)


def is_crypto_relevant(text):
    """True if the text mentions a crypto/finance term — used to drop
    off-topic posts/news (generic AI/tech, lifestyle, politics)."""
    t = (text or "").lower()
    return any(term in t for term in _CRYPTO_TERMS)


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
        desc = smart_trim(_clean_rss_desc(desc, title, feed["name"]), 400)
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
            summary = smart_trim(_clean_rss_desc(summary, title, feed["name"]), 400)
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
        if key in seen:
            continue
        if not is_crypto_relevant(f"{item['title']} {item.get('desc', '')}"):
            continue  # drop off-topic filler (generic AI/tech, lifestyle, etc.)
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


def fetch_fear_greed():
    """Crypto Fear & Greed Index (0–100). Returns (value, color_emoji)."""
    try:
        data = json.loads(http_get("https://api.alternative.me/fng/?limit=1"))
        value = int((data.get("data") or [{}])[0].get("value", 0))
        if value <= 25:
            emoji = "🔴"
        elif value <= 45:
            emoji = "🟠"
        elif value <= 55:
            emoji = "🟡"
        else:
            emoji = "🟢"
        return value, emoji
    except Exception as e:
        print(f"  ⚠️  Fear&Greed: {e}")
        return None, None


def fetch_btc_dominance():
    """BTC market-cap dominance % from CoinGecko global. Returns float or None."""
    try:
        data = json.loads(http_get("https://api.coingecko.com/api/v3/global", extra_headers=_cg_headers()))
        return data.get("data", {}).get("market_cap_percentage", {}).get("btc")
    except Exception as e:
        print(f"  ⚠️  CG global: {e}")
        return None


def _market_mood(prices):
    """Pick a nuanced mood line based on BTC vs altcoin behaviour."""
    if not prices:
        return "🟡 השוק יציב"
    btc = prices.get("bitcoin", {}).get("usd_24h_change", 0)
    alts = [prices[c].get("usd_24h_change", 0) for c in prices if c != "bitcoin"]
    avg_alts = sum(alts) / len(alts) if alts else 0

    if btc <= -5 and avg_alts <= -5:
        return "🔴 יום אדום — מכירה רחבה"
    if btc <= -2 and avg_alts <= -2:
        return "🟠 השוק בירידה — חלשות רחבה"
    if avg_alts >= 2 and avg_alts >= btc + 1.5:
        return "🟢 אלטים מובילים — Risk-On"
    if btc >= 2 and avg_alts >= 1:
        return "🟢 השוק ירוק — עליות רחבות"
    if btc >= 1 and avg_alts <= -0.5:
        return "🟡 BTC חזק, אלטים בפיגור"
    if btc <= -0.5 and avg_alts >= 1:
        return "🟢 אלטים מתעוררים — BTC חלש"
    if abs(btc - avg_alts) >= 3:
        return "🟡 שוק מעורב — תנודתיות גבוהה"
    avg = (btc + avg_alts) / 2
    if avg >= 0.5:
        return "🟢 השוק ירוק — תנועה מתונה"
    if avg <= -0.5:
        return "🟠 השוק אדום — תנועה מתונה"
    return "🟡 השוק יציב"


# ── Message Building ───────────────────────────────────────────────

def build_briefing(news, prices):
    """Full briefing — mood + Fear&Greed + dominance + prices + categorised news."""
    from ai_summary import summarize_news, GEMINI_API_KEY

    now = datetime.now(ISRAEL_TZ)
    R = "\u200F"
    L = []

    L.append(f"{R}📊 סקירת קריפטו | {now.strftime('%d.%m.%Y')} | {now.strftime('%H:%M')}")
    L.append("")

    if prices:
        L.append(f"{R}{_market_mood(prices)}")

        fg_value, fg_label = fetch_fear_greed()
        if fg_value is not None:
            L.append(f"{R}{fg_label} Fear & Greed: {fg_value}/100")

        dom = fetch_btc_dominance()
        if dom is not None:
            L.append(f"{R}🪙 BTC Dominance: {dom:.1f}%")
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
            title_he = bidi_fix(translate_he(item["title"]))
            L.append(f"{R}{i}. {title_he}")

            desc = (item.get("desc") or "").strip()
            if desc and len(desc) > 30:
                desc_he = bidi_fix(translate_he(desc))
                L.append(f"{R}   {desc_he}")

            L.append("")

        if GEMINI_API_KEY:
            summary = summarize_news(news[:5])
            if summary and not summary.startswith("⚠️"):
                L.append("")
                L.append(summary)

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
        title_he = bidi_fix(translate_he(item["title"]))
        L.append(f"{R}{i}. {title_he}")

        desc = (item.get("desc") or "").strip()
        if desc and len(desc) > 30:
            desc_he = bidi_fix(translate_he(desc))
            L.append(f"{R}   {desc_he}")

        L.append("")

    return "\n".join(L)
