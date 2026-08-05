"""
Crypto News Bot — Interactive Telegram bot.
RSS + CoinGecko + Twitter + Gemini AI + Charts → Telegram
"""

import os
import sys
import threading
import time
import traceback
import urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler

# Belt & suspenders with the Dockerfile's PYTHONUNBUFFERED: make prints
# line-buffered so Render's log tail shows activity in real time.
try:
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)
except Exception:
    pass


# ── Health server — must start BEFORE heavy imports ──────────────
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

    def log_message(self, format, *args):
        pass


port = int(os.environ.get("PORT", 10000))
threading.Thread(
    target=lambda: HTTPServer(("0.0.0.0", port), HealthHandler).serve_forever(),
    daemon=True,
).start()
print(f"🌐 Health server on port {port}")


# ── Keep-alive: Render free web services spin down without INBOUND
# traffic. Ping our own public URL every 10 minutes so the instance
# stays awake (Render injects RENDER_EXTERNAL_URL automatically).
def _keep_alive():
    url = os.environ.get("RENDER_EXTERNAL_URL", "")
    if not url:
        return
    while True:
        time.sleep(600)
        try:
            urllib.request.urlopen(url, timeout=20).read()
        except Exception as e:
            print(f"  ⚠️  keep-alive ping failed: {e}")


threading.Thread(target=_keep_alive, daemon=True).start()

# ── Now load the bot (heavy imports: matplotlib, pandas, etc.) ──
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bot import CryptoBot

if __name__ == "__main__":
    try:
        bot = CryptoBot()
        bot.run()
    except Exception:
        # Never die silently: log the traceback and exit non-zero so
        # Render restarts the service (visible in Events, not a ghost).
        print("💥 Bot loop crashed:")
        traceback.print_exc()
        sys.exit(1)
