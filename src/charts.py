"""
Professional candlestick chart generation.
CoinGecko OHLC data + mplfinance → dark TradingView-style charts.
"""

import io
import json
import os
from datetime import datetime, timezone

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import mplfinance as mpf
import pandas as pd

from news import http_get, COIN_SYMBOLS, _cg_headers

SYMBOL_TO_ID = {sym.lower(): cg_id for cg_id, sym in COIN_SYMBOLS}

# TradingView dark theme colors
BG_COLOR = "#131722"
GRID_COLOR = "#1e222d"
TEXT_COLOR = "#d1d4dc"
UP_COLOR = "#26a69a"
DOWN_COLOR = "#ef5350"


def _fetch_ohlc(coin_id, days=7):
    """Fetch OHLC data from CoinGecko."""
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/ohlc?vs_currency=usd&days={days}"
    try:
        data = json.loads(http_get(url, extra_headers=_cg_headers()))
        return data
    except Exception as e:
        print(f"  ⚠️  OHLC data: {e}")
        return []


def _build_candlestick_chart(symbol, ohlc_data):
    """Generate a professional candlestick chart."""
    rows = []
    for entry in ohlc_data:
        ts, o, h, l, c = entry
        dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
        rows.append({"Date": dt, "Open": o, "High": h, "Low": l, "Close": c, "Volume": 0})

    df = pd.DataFrame(rows)
    df.set_index("Date", inplace=True)

    mc = mpf.make_marketcolors(
        up=UP_COLOR, down=DOWN_COLOR,
        edge={"up": UP_COLOR, "down": DOWN_COLOR},
        wick={"up": UP_COLOR, "down": DOWN_COLOR},
        volume={"up": UP_COLOR, "down": DOWN_COLOR},
    )

    style = mpf.make_mpf_style(
        marketcolors=mc,
        facecolor=BG_COLOR,
        edgecolor=BG_COLOR,
        figcolor=BG_COLOR,
        gridcolor=GRID_COLOR,
        gridstyle="-",
        gridaxis="both",
        y_on_right=True,
        rc={
            "font.size": 9,
            "axes.labelcolor": TEXT_COLOR,
            "xtick.color": TEXT_COLOR,
            "ytick.color": TEXT_COLOR,
            "text.color": TEXT_COLOR,
        },
    )

    # price info for title
    last_close = df["Close"].iloc[-1]
    first_open = df["Open"].iloc[0]
    change = ((last_close - first_open) / first_open) * 100
    high = df["High"].max()
    low = df["Low"].min()
    arrow = "▲" if change >= 0 else "▼"
    price_fmt = f"${last_close:,.0f}" if last_close >= 1000 else f"${last_close:,.2f}" if last_close >= 1 else f"${last_close:.4f}"

    buf = io.BytesIO()
    fig, axes = mpf.plot(
        df,
        type="candle",
        style=style,
        figsize=(10, 6),
        returnfig=True,
        tight_layout=True,
        xrotation=0,
        datetime_format="%d/%m",
        warn_too_much_data=999,
    )

    # add title with price info
    title_text = f"{symbol.upper()}/USDT  •  {price_fmt}  {arrow} {change:+.1f}%"
    subtitle = f"H: ${high:,.2f}  L: ${low:,.2f}"
    fig.text(0.06, 0.95, title_text, fontsize=14, fontweight="bold",
             color="white", transform=fig.transFigure)
    fig.text(0.06, 0.91, subtitle, fontsize=10,
             color="#787b86", transform=fig.transFigure)

    fig.savefig(buf, format="png", dpi=120, bbox_inches="tight",
                facecolor=BG_COLOR, edgecolor="none", pad_inches=0.3)
    buf.seek(0)
    image_bytes = buf.read()
    plt.close(fig)
    return image_bytes


def get_chart_image(symbol="btc", days=7):
    """Get candlestick chart image. Returns (image_bytes, caption) or (None, error_msg)."""
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
        change_dir = "▲" if ohlc_data[-1][4] >= ohlc_data[0][1] else "▼"
        caption = f"📊 {symbol.upper()}/USDT | {days} ימים | {change_dir}"
        return image_bytes, caption
    except Exception as e:
        print(f"  ⚠️  Chart generation: {e}")
        return None, f"⚠️ שגיאה ביצירת גרף: {e}"


def get_available_coins():
    return [sym.upper() for _, sym in COIN_SYMBOLS]
