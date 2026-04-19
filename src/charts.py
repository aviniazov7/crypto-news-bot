"""
Candlestick chart generation using CoinGecko OHLC + mplfinance.
Generates professional dark-themed candlestick charts.
"""

import io
import json
import os
from datetime import datetime, timezone

import matplotlib
matplotlib.use("Agg")
import mplfinance as mpf
import pandas as pd

from news import http_get, COIN_SYMBOLS

# Map short symbols to CoinGecko IDs
SYMBOL_TO_ID = {sym.lower(): cg_id for cg_id, sym in COIN_SYMBOLS}


def _fetch_ohlc(coin_id, days=7):
    """Fetch OHLC data from CoinGecko."""
    cg_key = os.environ.get("COINGECKO_API_KEY", "")
    key_param = f"&x_cg_demo_api_key={cg_key}" if cg_key else ""
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/ohlc?vs_currency=usd&days={days}{key_param}"
    try:
        data = json.loads(http_get(url))
        return data  # [[timestamp, open, high, low, close], ...]
    except Exception as e:
        print(f"  ⚠️  OHLC data: {e}")
        return []


def _build_candlestick_chart(symbol, ohlc_data):
    """Generate a candlestick chart image using mplfinance."""
    # Convert to DataFrame
    rows = []
    for entry in ohlc_data:
        ts, o, h, l, c = entry
        dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
        rows.append({"Date": dt, "Open": o, "High": h, "Low": l, "Close": c})

    df = pd.DataFrame(rows)
    df.set_index("Date", inplace=True)

    # Dark style matching TradingView
    mc = mpf.make_marketcolors(
        up="#26a69a", down="#ef5350",
        edge={"up": "#26a69a", "down": "#ef5350"},
        wick={"up": "#26a69a", "down": "#ef5350"},
    )
    style = mpf.make_mpf_style(
        base_mpf_style="nightclouds",
        marketcolors=mc,
        facecolor="#131722",
        edgecolor="#131722",
        gridcolor="#1e222d",
        gridstyle="-",
        y_on_right=True,
        rc={"font.size": 10},
    )

    # Generate chart
    buf = io.BytesIO()
    fig, axes = mpf.plot(
        df,
        type="candle",
        style=style,
        title=f"\n{symbol.upper()}/USDT",
        ylabel="",
        figsize=(10, 6),
        returnfig=True,
    )
    fig.savefig(buf, format="png", dpi=100, bbox_inches="tight",
                facecolor="#131722", edgecolor="none")
    buf.seek(0)
    image_bytes = buf.read()
    matplotlib.pyplot.close(fig)
    return image_bytes


def get_chart_image(symbol="btc", days=7):
    """Get candlestick chart image bytes. Returns (image_bytes, caption) or (None, error_msg)."""
    symbol = symbol.lower().strip()
    coin_id = SYMBOL_TO_ID.get(symbol)
    if not coin_id:
        available = ", ".join(s.upper() for s in SYMBOL_TO_ID)
        return None, f"לא מכיר את {symbol.upper()}. אפשר: {available}"

    ohlc_data = _fetch_ohlc(coin_id, days)
    if not ohlc_data:
        return None, f"⚠️ לא הצלחתי לטעון נתונים עבור {symbol.upper()}"

    try:
        image_bytes = _build_candlestick_chart(symbol, ohlc_data)
        caption = f"📊 {symbol.upper()}/USDT | {days} ימים אחרונים"
        return image_bytes, caption
    except Exception as e:
        print(f"  ⚠️  Chart generation: {e}")
        return None, f"⚠️ שגיאה ביצירת גרף: {e}"


def get_available_coins():
    """Return list of available coin symbols."""
    return [sym.upper() for _, sym in COIN_SYMBOLS]
