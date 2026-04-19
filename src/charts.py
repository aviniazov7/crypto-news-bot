"""
Price chart generation using CoinGecko history + QuickChart.io.
Returns chart image bytes to send via Telegram sendPhoto.
"""

import json
import urllib.parse
from datetime import datetime, timezone

from news import http_get, COIN_SYMBOLS

# Map short symbols to CoinGecko IDs
SYMBOL_TO_ID = {sym.lower(): cg_id for cg_id, sym in COIN_SYMBOLS}


def _fetch_price_history(coin_id, days=7):
    """Fetch price history from CoinGecko."""
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart?vs_currency=usd&days={days}"
    try:
        data = json.loads(http_get(url))
        return data.get("prices", [])
    except Exception as e:
        print(f"  ⚠️  Chart data: {e}")
        return []


def _build_chart_url(coin_symbol, prices):
    """Build a QuickChart.io URL for a line chart."""
    # sample every Nth point to keep URL short
    step = max(1, len(prices) // 50)
    sampled = prices[::step]

    labels = []
    values = []
    for ts, price in sampled:
        dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
        labels.append(dt.strftime("%d/%m"))
        values.append(round(price, 2))

    chart_config = {
        "type": "line",
        "data": {
            "labels": labels,
            "datasets": [{
                "label": f"{coin_symbol.upper()} (USD)",
                "data": values,
                "borderColor": "#00d4aa",
                "backgroundColor": "rgba(0,212,170,0.1)",
                "fill": True,
                "tension": 0.3,
                "pointRadius": 0,
            }]
        },
        "options": {
            "plugins": {
                "legend": {"labels": {"color": "#ffffff", "font": {"size": 14}}},
            },
            "scales": {
                "x": {
                    "ticks": {"color": "#aaaaaa", "maxTicksLimit": 7},
                    "grid": {"color": "rgba(255,255,255,0.1)"},
                },
                "y": {
                    "ticks": {"color": "#aaaaaa"},
                    "grid": {"color": "rgba(255,255,255,0.1)"},
                },
            },
        },
    }

    config_str = json.dumps(chart_config)
    encoded = urllib.parse.quote(config_str)
    return f"https://quickchart.io/chart?bkg=%231a1a2e&width=600&height=400&c={encoded}"


def get_chart_image(symbol="btc", days=7):
    """Get chart image bytes for a coin. Returns (image_bytes, caption) or (None, error_msg)."""
    symbol = symbol.lower().strip()
    coin_id = SYMBOL_TO_ID.get(symbol)
    if not coin_id:
        available = ", ".join(s.upper() for s in SYMBOL_TO_ID)
        return None, f"לא מכיר את {symbol.upper()}. אפשר: {available}"

    prices = _fetch_price_history(coin_id, days)
    if not prices:
        return None, f"⚠️ לא הצלחתי לטעון נתונים עבור {symbol.upper()}"

    chart_url = _build_chart_url(symbol, prices)

    try:
        image_bytes = http_get(chart_url, timeout=20)
        caption = f"📊 {symbol.upper()} | {days} ימים אחרונים"
        return image_bytes, caption
    except Exception as e:
        return None, f"⚠️ שגיאה ביצירת גרף: {e}"


def get_available_coins():
    """Return list of available coin symbols."""
    return [sym.upper() for _, sym in COIN_SYMBOLS]
