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

COINS = "bitcoin,ethereum,solana"
COIN_SYMBOLS = [
    ("bitcoin", "BTC"), ("ethereum", "ETH"), ("solana", "SOL"),
]
# Macro assets shown alongside crypto (Yahoo Finance symbols).
MACRO_SYMBOLS = [
    ("GC=F", "🥇 Gold"),
    ("CL=F", "🛢️ Oil"),
    ("QQQ", "📈 QQQ"),
]
HOURS_BACK = 8
MAX_PER_SOURCE = 3
try:
    from zoneinfo import ZoneInfo
    ISRAEL_TZ = ZoneInfo("Asia/Jerusalem")
except Exception:
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
    # 'dumping' literal-translated to garbage
    ("מזבלות", "מכירת לחץ"),
    ("המזבלה", "המכירה"),
    # trading 'session' → 'מושב מסחר' / 'סשן' (Google says 'פגישה' = meeting).
    # Order matters: longer/specific patterns must come before shorter ones,
    # otherwise the short rule matches inside the long one and leaves stray ה.
    ("סוף הפגישה בשוק באסיה", "סוף מושב המסחר באסיה"),
    ("סוף הפגישה בשוק בלונדון", "סוף מושב המסחר בלונדון"),
    ("סוף הפגישה בשוק", "סוף מושב המסחר"),
    ("הפגישה בשוק באסיה", "מושב המסחר באסיה"),
    ("הפגישה בשוק בלונדון", "מושב המסחר בלונדון"),
    ("הפגישה בשוק", "מושב המסחר"),
    ("מפגשי המסחר", "מושבי המסחר"),
    ("מפגש המסחר", "מושב המסחר"),
    ("פגישת המסחר", "מושב המסחר"),
    # 'escalations heating up' → Google mangles 'heating up' into 'arrogant'
    ("מתנשאות שוב", "מתחממות שוב"),
    ("מתנשאת שוב", "מתחממת שוב"),
    # Defensive: if 'Bitcoin' was truncated mid-word upstream → 'ביטק'.
    # Match only at word boundaries so 'ביטקוין' itself is left alone.
    ("ביטק…", "ביטקוין…"),
    ("ביטק.", "ביטקוין."),
    ("ביטק,", "ביטקוין,"),
    ("ביטק\n", "ביטקוין\n"),
    ("ביטקוי ", "ביטקוין "),
    ("ביטקוי…", "ביטקוין…"),
    ("ביטקוי.", "ביטקוין."),
    ("ביטקוי,", "ביטקוין,"),
    ("ביטקוי\n", "ביטקוין\n"),
    # 'shorts' (trading) sometimes comes out as 'שוטרים' (police). In a
    # crypto bot context this is almost always the mistranslation.
    ("שוטרים", "שורטים"),
    # 'cheap fees' → 'עמלות זילות' (scorn) instead of 'עמלות זולות' (cheap).
    ("עמלות זילות", "עמלות זולות"),
    ("עמלת זילות", "עמלת זולות"),
    ("זילות ביותר", "זולות ביותר"),
    ('ל"זילות', 'לזולות'),
    # 'mechanism' came out as 'גנגנון' (not a real Hebrew word).
    ("גנגנון", "מנגנון"),
)


def _fix_he_jargon(text):
    """Replace literal mistranslations of crypto/trading slang."""
    for bad, good in _JARGON_FIXES:
        text = text.replace(bad, good)
    return text


def _has_hebrew(text):
    return any("֐" <= ch <= "׿" for ch in (text or ""))


def _gt_endpoint_gtx(text):
    """Primary free Google endpoint (translate.googleapis.com)."""
    q = urllib.parse.quote(text)
    url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=he&dt=t&q={q}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode())
        return "".join(p[0] for p in data[0] if p[0])


def _gt_endpoint_clients5(text):
    """Alternate free Google endpoint (clients5.google.com) — different IP pool."""
    q = urllib.parse.quote(text)
    url = (
        "https://clients5.google.com/translate_a/t"
        f"?client=dict-chrome-ex&sl=en&tl=he&q={q}"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode())
        # Response is either ["text", "lang"] or [["text"], ...]
        if isinstance(data, list) and data:
            first = data[0]
            if isinstance(first, str):
                return first
            if isinstance(first, list):
                return "".join(seg if isinstance(seg, str) else seg[0] for seg in first)
        return ""


_MYMEMORY_EMAIL = os.environ.get("MYMEMORY_EMAIL", "")


def _gt_endpoint_mymemory(text):
    """Independent free translation API (real REST API — works from datacenter
    IPs where Google's scraping endpoints are blocked). With MYMEMORY_EMAIL set,
    the free daily limit rises from ~5k to ~50k words."""
    q = urllib.parse.quote(text[:500])  # MyMemory caps query length
    url = f"https://api.mymemory.translated.net/get?q={q}&langpair=en|he"
    if _MYMEMORY_EMAIL:
        url += f"&de={urllib.parse.quote(_MYMEMORY_EMAIL)}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode())
        return (data.get("responseData") or {}).get("translatedText", "")


def _google_translate_he(text):
    """Free translation with multiple engines. MyMemory (a real REST API) goes
    first because Google's free scraping endpoints are often blocked on
    datacenter IPs like Render's."""
    text = text[:900]
    for engine in (_gt_endpoint_mymemory, _gt_endpoint_gtx, _gt_endpoint_clients5):
        try:
            out = _fix_he_jargon(engine(text))
            if _has_hebrew(out):
                return out
        except Exception as e:
            print(f"  ⚠️  {engine.__name__} failed: {e}")
    return None


_GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")
# gemini-2.5-flash has a 20 req/day free tier; gemini-2.0-flash-lite has none.
_GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
# Free tier is ~20 requests/day. Cap our own usage a bit under that so we
# never hit 429 — within budget every translation is high-quality Gemini.
_GEMINI_DAILY_BUDGET = int(os.environ.get("GEMINI_DAILY_BUDGET", "18"))
_gemini_day = None
_gemini_count = 0


def _gemini_budget_left():
    """Remaining Gemini calls allowed today (resets at local midnight)."""
    global _gemini_day, _gemini_count
    import datetime
    today = datetime.date.today().isoformat()
    if today != _gemini_day:
        _gemini_day, _gemini_count = today, 0
    return _GEMINI_DAILY_BUDGET - _gemini_count


def _gemini_enabled():
    return bool(_GEMINI_KEY) and _gemini_budget_left() > 0


def gemini_budget_status():
    """(used, budget) for /health."""
    _gemini_budget_left()  # refresh day rollover
    return _gemini_count, _GEMINI_DAILY_BUDGET


def _consume_gemini_budget():
    """Reserve one budgeted Gemini call for code that bypasses
    _gemini_generate (e.g. ai_summary). True if a call was reserved."""
    global _gemini_count
    if not _gemini_enabled():
        return False
    _gemini_count += 1
    return True


_TRANSLATE_RULES = (
    "Rules:\n"
    "- Translate EVERYTHING into Hebrew, including capitalized/Title-Case "
    "phrases, headlines, and trading jargon. Do NOT leave English words "
    "untranslated just because they look like a name or are capitalized. "
    "The ONLY things that stay in English are listed below.\n"
    "- Trading terms: short(s)=שורט/שורטים (NEVER 'שוטרים'/police), "
    "long(s)=לונג/לונגים, buy the dip=קניית הירידה, pump=פאמפ, dump=מפולת, "
    "bullish=שורי, bearish=דובי, scalp/scalping=סקאלפ (NEVER קרקפת), "
    "long scalp=סקאלפ לונג, cheap fees=עמלות זולות (NEVER 'זילות'/scorn), "
    "mechanism=מנגנון (NEVER 'גנגנון').\n"
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
    "'1R'/'2R'=יחס סיכון (1R/2R, keep number), "
    "'session(s)' (trading)=מושב מסחר/סשן (NEVER 'פגישה'), "
    "'dumping'/'dump'=מפילה/מכירת לחץ (NEVER 'מזבלה'), "
    "'Whale Order Data'=נתוני הזמנות לוויתנים, "
    "'PWL' (Previous Week Low)=PWL (שפל השבוע הקודם), "
    "'PWH' (Previous Week High)=PWH (שיא השבוע הקודם), "
    "'dead cat bounce'=קפיצת חתול מת, "
    "'heating up' (geopolitics)=מתחמם/מתלהט (NEVER 'מתנשא').\n"
    "- Keep in English ONLY: ticker symbols ($BTC, ETH), prices/numbers "
    "(76k, $76,672), and the acronyms 'TWAP'/'VWAP'/'CVD'.\n"
    "- ABSOLUTELY NO meta-commentary: do NOT discuss translation choices, "
    "do NOT mention alternative wordings, do NOT use English connectives "
    "like 'or', 'but', 'might be', 'more formal', 'is understood', "
    "'Let's stick to'. Output the FINAL Hebrew sentence and nothing else.\n"
    "- If the source text is cut off mid-sentence, translate only the "
    "complete part and end on a complete sentence.\n"
)


_META_MARKERS = (
    "might be more formal",
    "let's stick to",
    "let's use",
    "is understood",
    "more natural",
    "could be translated",
    "would be better",
    "sounds odd",
    "sounds very odd",
    "sounds strange",
    "what if",
    "is used?",
    "(shadow)",
    "(candle",
    " or \"",
    "\" or ",
)

# A run of 4+ consecutive English words inside a "Hebrew" translation is a
# leak (legit output only keeps tickers/acronyms/short names in English).
_ENGLISH_RUN_RE = re.compile(r"(?:\b[A-Za-z]{2,}\b[\s,]+){3,}\b[A-Za-z]{2,}\b")


def _looks_like_meta(text):
    """True if Gemini's output is translator-style commentary rather than a
    clean Hebrew translation (a real bug seen in production)."""
    low = (text or "").lower()
    if any(m in low for m in _META_MARKERS):
        return True
    return bool(_ENGLISH_RUN_RE.search(text or ""))


def _gemini_generate(prompt, max_tokens, temperature=0.2):
    """Single Gemini generateContent call. Returns the text or raises.
    Counts against the daily budget; raises if the budget is exhausted so
    callers fall back to Google instead of burning into a 429."""
    global _gemini_count
    if _gemini_budget_left() <= 0:
        raise RuntimeError("daily Gemini budget exhausted")
    _gemini_count += 1
    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
            # Disable gemini-2.5 'thinking' — its tokens count against
            # maxOutputTokens and can silently truncate/empty the output.
            "thinkingConfig": {"thinkingBudget": 0},
        },
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


def _gemini_translate_he(text):
    """Translate to Hebrew via Gemini with correct crypto/trading terminology."""
    prompt = (
        "You are a professional crypto/finance editor. Rewrite the text below "
        "in clear, fluent, professional Hebrew as a finance desk would phrase "
        "it — not a literal machine translation. Keep it concise and natural.\n"
        f"{_TRANSLATE_RULES}"
        "- Output ONLY the Hebrew text, no quotes, notes, or preamble.\n\n"
        f"{text}"
    )
    return _gemini_generate(prompt, 1024)


def translate_he(text):
    if not text:
        return text
    # Primary: Gemini. Accept only if it actually produced Hebrew and isn't
    # translator meta-commentary.
    if _gemini_enabled():
        try:
            out = _fix_he_jargon(_gemini_translate_he(text))
            if _looks_like_meta(out):
                print("  ⚠️  Gemini returned meta-commentary, rejecting")
                out = ""
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


_BATCH_LINE_RE = re.compile(r"^\s*\[(\d+)\]\s*(.*)$")


def translate_many(texts, force_fallback=False):
    """Translate a list of strings in ONE Gemini call (saves quota on the
    briefing). If Gemini fails or is exhausted: when force_fallback=True
    (e.g. briefing news), fall back to per-item Google so the briefing
    always shows content; otherwise honour GEMINI_ONLY and return empties."""
    texts = [t or "" for t in texts]
    if not texts:
        return []
    if _gemini_enabled():
        try:
            numbered = "\n".join(f"[{i}] {t}" for i, t in enumerate(texts))
            prompt = (
                "Translate each numbered crypto/finance line below into clear, "
                "fluent, professional Hebrew.\n"
                f"{_TRANSLATE_RULES}"
                "- Return EXACTLY one line per item, in the SAME [n] format and "
                "order, e.g. '[0] <hebrew>'. No extra lines, notes, or preamble.\n\n"
                f"{numbered}"
            )
            out = _gemini_generate(prompt, 2048)
            if _looks_like_meta(out):
                raise ValueError("batch translate returned meta-commentary")
            parsed = {}
            for line in out.splitlines():
                m = _BATCH_LINE_RE.match(line)
                if m:
                    parsed[int(m.group(1))] = _fix_he_jargon(m.group(2).strip())
            if len(parsed) == len(texts) and all(
                _has_hebrew(parsed[i]) or not texts[i].strip() for i in range(len(texts))
            ):
                return [parsed[i] for i in range(len(texts))]
            print("  ⚠️  Batch translate parse mismatch")
        except Exception as e:
            print(f"  ⚠️  Batch Gemini translate failed: {e}")
    # Caller can force the Google fallback (e.g. the briefing) so news is
    # never empty; otherwise honour GEMINI_ONLY mode (default for tweets).
    if not force_fallback and os.environ.get("GEMINI_ONLY", "1") == "1":
        return ["" for _ in texts]
    return [translate_he(t) for t in texts]
    return [translate_he(t) for t in texts]


def filter_and_translate_tweet(text):
    """One Gemini call that BOTH filters and translates a tweet.
    Returns the Hebrew translation, or None if the post should be skipped
    (off-topic / low-value). Falls back to Google translate (keeping the
    post) if Gemini is unavailable — the keyword filter already ran upstream."""
    text = (text or "").strip()
    if not text:
        return ""
    if _gemini_enabled():
        try:
            prompt = (
                "You are a filter+translator for a crypto trading group's "
                "news bot. The group wants ONLY real market information.\n"
                "STEP 1 — Output exactly the single word SKIP (and nothing "
                "else) if the post is:\n"
                "(a) off-topic: politics, war, crime, sports, entertainment, "
                "generic tech, personal life;\n"
                "(b) low-value with no concrete market info: meme, joke, "
                "sarcastic 'playbook', vague hype, gm/wagmi one-liner;\n"
                "(c) promotional in ANY form: ads, sponsored/partnership "
                "content, exchange referral codes, giveaways, airdrops, "
                "presales/mints/whitelists, token or NFT shilling, "
                "'join my channel/discord/VIP' invitations, PnL brag/flex "
                "posts showing leveraged gains, or engagement bait "
                "('who else is in?', 'like & RT').\n"
                "STEP 2 — Otherwise translate it to clear, fluent, professional "
                "Hebrew as a finance desk would phrase it.\n"
                f"{_TRANSLATE_RULES}"
                "- Output ONLY the word SKIP, or ONLY the Hebrew translation. "
                "No quotes, notes, or preamble.\n\n"
                f"{text}"
            )
            out = _gemini_generate(prompt, 1024)
            if out.strip().upper().startswith("SKIP"):
                return None
            out = _fix_he_jargon(out)
            if _looks_like_meta(out):
                print("  ⚠️  Gemini filter+translate returned meta-commentary")
                out = ""
            if _has_hebrew(out):
                return out
            print("  ⚠️  Gemini filter+translate gave non-Hebrew")
        except Exception as e:
            print(f"  ⚠️  Gemini filter+translate failed: {e}")
    # Quality-first (Gemini-only) mode is the default: skip the post if we
    # can't get a high-quality Gemini translation. Set GEMINI_ONLY=0 to
    # accept Google fallback quality instead.
    if os.environ.get("GEMINI_ONLY", "1") == "1":
        print("  🚫 Skipped — Gemini unavailable and GEMINI_ONLY is on")
        return None
    out = _google_translate_he(text)
    if out and _has_hebrew(out):
        return out
    print("  🚫 No Hebrew translation available — skipping post")
    return None


def translate_he_or_none(text):
    """Quality-first translation: returns the Hebrew if Gemini can produce it,
    or None to let the caller skip. By default (GEMINI_ONLY=1) does NOT fall
    back to Google, so manual sends only deliver Gemini-quality output."""
    if not text:
        return None
    if os.environ.get("GEMINI_ONLY", "1") == "1":
        if _gemini_enabled():
            try:
                out = _fix_he_jargon(_gemini_translate_he(text))
                if _has_hebrew(out):
                    return out
            except Exception as e:
                print(f"  ⚠️  Gemini translate failed (GEMINI_ONLY): {e}")
        return None
    out = translate_he(text)
    return out if _has_hebrew(out) else None


def translation_health():
    """Probe both translation engines live. Returns a dict for /health."""
    used, budget = gemini_budget_status()
    result = {"gemini_key_set": bool(_GEMINI_KEY), "model": _GEMINI_MODEL,
              "budget": f"{used}/{budget}",
              "gemini_only": os.environ.get("GEMINI_ONLY", "1") == "1"}
    # Gemini
    if not _GEMINI_KEY:
        result["gemini"] = "no-key"
    elif _gemini_budget_left() <= 0:
        result["gemini"] = "budget-spent"
    else:
        try:
            out = _gemini_translate_he("Bitcoin is pumping hard today")
            result["gemini"] = "ok" if _has_hebrew(out) else "no-hebrew"
        except urllib.error.HTTPError as e:
            result["gemini"] = f"HTTP {e.code}" + (" (quota)" if e.code == 429 else "")
        except Exception as e:
            result["gemini"] = f"error: {type(e).__name__}"
    # Free engines — probe each separately so we know exactly what's blocked.
    engines = {
        "mymemory": _gt_endpoint_mymemory,
        "google_gtx": _gt_endpoint_gtx,
        "google_c5": _gt_endpoint_clients5,
    }
    any_ok = False
    for name, fn in engines.items():
        try:
            out = fn("Bitcoin is pumping hard today")
            if _has_hebrew(out or ""):
                result[name] = "ok"
                any_ok = True
            else:
                result[name] = "no-hebrew"
        except urllib.error.HTTPError as e:
            result[name] = f"HTTP {e.code}"
        except Exception as e:
            result[name] = f"err: {type(e).__name__}"
    result["free_ok"] = any_ok
    return result


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


def smart_trim(text, max_len=500):
    """Trim text to max_len, NEVER ending mid-word.
    Prefers a sentence boundary in the latter half, else the last space."""
    if len(text) <= max_len:
        return text
    snippet = text[:max_len]
    for marker in (". ", "! ", "? "):
        idx = snippet.rfind(marker)
        if idx > max_len * 0.6:
            return snippet[: idx + 1]
    # Always step back to the last space — never hard-cut mid-word.
    idx = snippet.rfind(" ")
    if idx > 0:
        return snippet[:idx] + "…"
    return snippet + "…"


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
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        # e.g. an HTML error/challenge page served with HTTP 200 — skip only
        # this feed instead of aborting the whole briefing.
        print(f"  ⚠️  {feed['name']}: not valid RSS/XML ({e}), skipping")
        return []
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
        desc = smart_trim(_clean_rss_desc(desc, title, feed["name"]), 500)
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
            summary = smart_trim(_clean_rss_desc(summary, title, feed["name"]), 500)
            items.append({"title": title, "desc": summary, "source": feed["name"], "date": pub})
    return items[:MAX_PER_SOURCE]


_SPONSORED_RE = re.compile(
    r"\b(sponsored|press\s+release|partner\s+content|paid\s+post|promoted|"
    r"advertorial|brought\s+to\s+you\s+by)\b",
    re.IGNORECASE,
)


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
        blob = f"{item['title']} {item.get('desc', '')}"
        if not is_crypto_relevant(blob):
            continue  # drop off-topic filler (generic AI/tech, lifestyle, etc.)
        if _SPONSORED_RE.search(blob):
            continue  # drop sponsored/press-release items from news feeds
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


def fetch_macro():
    """Gold / oil / QQQ via Yahoo Finance (free, no key).
    Returns [(label, price, pct_change)], skipping symbols that fail."""
    results = []
    for symbol, label in MACRO_SYMBOLS:
        try:
            url = (
                "https://query1.finance.yahoo.com/v8/finance/chart/"
                f"{urllib.parse.quote(symbol)}?interval=1d&range=2d"
            )
            data = json.loads(http_get(url, extra_headers={"User-Agent": "Mozilla/5.0"}))
            meta = data["chart"]["result"][0]["meta"]
            price = meta.get("regularMarketPrice")
            prev = meta.get("chartPreviousClose") or meta.get("previousClose")
            if price is None or not prev:
                continue
            change = (price / prev - 1) * 100
            results.append((label, price, change))
        except Exception as e:
            print(f"  ⚠️  Yahoo {symbol}: {e}")
    return results


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
        return "🟠 השוק בירידה — חולשה רחבה"
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

        macro = fetch_macro()
        if macro:
            L.append("")
            for label, p, ch in macro:
                arrow = "▲" if ch >= 0 else "▼"
                ps = f"${p:,.0f}" if p >= 1000 else f"${p:,.2f}"
                L.append(f"{R}  {arrow} {label}  {ps}  ({ch:+.1f}%)")
        L.append("")

    if news:
        top = news[:5]

        # Primary: ONE AI call turns the day's items into a clean digest —
        # emoji-led paragraphs (no numbering) ending with a 🎯 bottom line.
        # Counts against the daily Gemini budget. Disable: BRIEFING_AI_SUMMARY=0.
        digest = None
        if (
            GEMINI_API_KEY
            and os.environ.get("BRIEFING_AI_SUMMARY", "1") == "1"
            and _consume_gemini_budget()
        ):
            digest = summarize_news(top)
            if not digest or digest.startswith("⚠️") or not _has_hebrew(digest):
                digest = None
            else:
                digest = _fix_he_jargon(digest)

        if digest:
            L.append(f"{R}📰 מה חדש היום:")
            L.append("")
            L.append(digest)
        else:
            # Fallback: translated numbered list (Google fallback allowed)
            # so the briefing still carries news when the digest fails.
            to_translate = []
            for item in top:
                to_translate.append(item["title"])
                desc = (item.get("desc") or "").strip()
                to_translate.append(desc if len(desc) > 30 else "")
            translated = translate_many(to_translate, force_fallback=True)

            news_lines = []
            n = 0
            for i in range(len(top)):
                title_he = translated[i * 2]
                if not _has_hebrew(title_he):
                    continue  # skip untranslated item (never show English)
                n += 1
                news_lines.append(f"{R}{n}. {bidi_fix(title_he)}")
                desc_he = translated[i * 2 + 1]
                if desc_he and _has_hebrew(desc_he):
                    news_lines.append(f"{R}   {bidi_fix(desc_he)}")
                news_lines.append("")

            if news_lines:
                L.append(f"{R}📰 מה חדש היום:")
                L.append("")
                L.extend(news_lines)

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

    macro = fetch_macro()
    if macro:
        L.append("")
        for label, p, ch in macro:
            arrow = "▲" if ch >= 0 else "▼"
            ps = f"${p:,.0f}" if p >= 1000 else f"${p:,.2f}"
            L.append(f"{R}  {arrow} {label}  {ps}  ({ch:+.1f}%)")

    return "\n".join(L)


def build_news_message(news):
    """Build a news-only message."""
    R = "\u200F"
    now = datetime.now(ISRAEL_TZ)
    L = [f"{R}📰 חדשות אחרונות | {now.strftime('%H:%M')}", ""]

    if not news:
        L.append(f"{R}אין חדשות חדשות כרגע")
        return "\n".join(L)

    top = news[:5]
    to_translate = []
    for item in top:
        to_translate.append(item["title"])
        desc = (item.get("desc") or "").strip()
        to_translate.append(desc if len(desc) > 30 else "")
    translated = translate_many(to_translate, force_fallback=True)

    n = 0
    for i in range(len(top)):
        title_he = translated[i * 2]
        if not _has_hebrew(title_he):
            continue  # Hebrew-only: skip untranslated items
        n += 1
        L.append(f"{R}{n}. {bidi_fix(title_he)}")
        desc_he = translated[i * 2 + 1]
        if desc_he and _has_hebrew(desc_he):
            L.append(f"{R}   {bidi_fix(desc_he)}")
        L.append("")

    if n == 0:
        L.append(f"{R}⚠️ אין תרגום זמין כרגע — נסה שוב מאוחר יותר")

    return "\n".join(L)
