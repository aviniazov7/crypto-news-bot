"""
AI-powered news summary using Google Gemini API.
Summarizes crypto news into concise Hebrew bullet points.
"""

import json
import os
import urllib.request


GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")


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
        if item.get("desc"):
            line += f" — {item['desc'][:100]}"
        headlines.append(line)
    headlines_text = "\n".join(headlines)

    prompt = (
        "You are a crypto market analyst writing for Hebrew-speaking traders.\n"
        "Summarize the following crypto news headlines into 3-5 concise bullet points in Hebrew.\n"
        "Focus on: market impact, key events, and actionable insights.\n"
        "Use emojis for visual clarity. Keep each bullet to 1-2 sentences.\n\n"
        f"Headlines:\n{headlines_text}\n\n"
        "Write the summary in Hebrew:"
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
                    summary = parts[0].get("text", "").strip()
                    if summary:
                        R = "\u200F"
                        return f"{R}🤖 סיכום AI:\n\n{R}{summary}"
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
