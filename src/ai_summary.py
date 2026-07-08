"""
AI-powered news summary using Google Gemini API.
Summarizes crypto news into concise Hebrew bullet points.
"""

import json
import os
import re
import urllib.request


GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")


def _clean_summary(text):
    """Strip markdown artifacts and preamble lines — Telegram shows raw text,
    so '**' and '*' bullets would appear literally."""
    text = text.replace("**", "")
    lines = []
    for line in text.splitlines():
        line = re.sub(r"^\s*[\*\-•·]+\s*", "", line).rstrip()
        lines.append(line)
    # Drop a leading "הנה סיכום..." preamble line
    while lines and (not lines[0].strip() or (
        "סיכום" in lines[0] and lines[0].strip().endswith(":")
    )):
        lines.pop(0)
    return "\n".join(lines).strip()


def summarize_news(news_items):
    """
    Summarize a list of news items into Hebrew bullet points.
    Returns summary string or fallback message.
    """
    if not GEMINI_API_KEY:
        return "⚠️ סיכום AI לא זמין — חסר GEMINI_API_KEY"

    if not news_items:
        return "אין חדשות לסכם כרגע"

    # build headlines text
    headlines = []
    for i, item in enumerate(news_items[:10], 1):
        line = f"{i}. {item['title']}"
        desc = (item.get("desc") or "").strip()
        if desc:
            # Trim on a word boundary — a mid-word cut ('Bitcoi') makes the
            # model reproduce the broken word in Hebrew ('ביטקוי').
            if len(desc) > 160:
                snippet = desc[:160]
                idx = snippet.rfind(" ")
                desc = (snippet[:idx] if idx > 0 else snippet) + "…"
            line += f" — {desc}"
        headlines.append(line)
    headlines_text = "\n".join(headlines)

    prompt = (
        "You are a crypto market analyst writing for Hebrew-speaking traders.\n"
        "Rewrite the following news items in Hebrew as a clean daily digest — "
        "this IS the news section the reader sees, so cover every distinct "
        "story:\n"
        "- One short paragraph per story (1-2 sentences), starting with one "
        "fitting emoji. Blank line between paragraphs.\n"
        "- Merge duplicate/overlapping stories into one paragraph.\n"
        "- End with a final paragraph starting with 🎯 — the bottom line: "
        "the combined market picture and the one thing to watch next "
        "(1-2 sentences).\n"
        "STRICT format rules:\n"
        "- Plain text ONLY: no markdown, no asterisks, no bullets, no "
        "numbering, no bold.\n"
        "- Start DIRECTLY with the first paragraph — no preamble or intro "
        "line.\n\n"
        f"News items:\n{headlines_text}\n\n"
        "Digest:"
    )

    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.7,
            # gemini-2.5-flash "thinks" by default and thinking tokens count
            # against maxOutputTokens — with a small cap the visible answer
            # comes back empty/truncated. Disable thinking and give headroom.
            "maxOutputTokens": 1024,
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }).encode("utf-8")

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
            candidates = data.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                if parts:
                    summary = _clean_summary(parts[0].get("text", "").strip())
                    if summary:
                        R = "\u200F"
                        # RTL-mark every line so multi-paragraph text renders
                        # right-aligned in Telegram.
                        body = "\n".join(
                            f"{R}{line}" if line.strip() else line
                            for line in summary.splitlines()
                        )
                        return body  # RTL-marked digest body, no header
        return "⚠️ לא הצלחתי ליצור סיכום כרגע"
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ""
        print(f"  ⚠️  Gemini API HTTP {e.code}: {body[:300]}")
        if e.code == 429:
            return "⚠️ מכסת Gemini נגמרה — נסה שוב בעוד דקה"
        if e.code in (401, 403):
            return "⚠️ מפתח Gemini לא תקין — בדוק GEMINI_API_KEY"
        return f"⚠️ שגיאה בסיכום AI (HTTP {e.code})"
    except Exception as e:
        print(f"  ⚠️  Gemini API: {e}")
        return "⚠️ שגיאה בסיכום AI — נסה שוב מאוחר יותר"
