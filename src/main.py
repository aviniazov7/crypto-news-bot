"""
Crypto News Bot — Interactive Telegram bot.
RSS + CoinGecko + Twitter + Gemini AI + Charts → Telegram
"""

import os
import sys
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler


# ── Health server — must start BEFORE heavy imports ──────────────
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, format, *args):
        pass


port = int(os.environ.get("PORT", 10000))
threading.Thread(
    target=lambda: HTTPServer(("0.0.0.0", port), HealthHandler).serve_forever(),
    daemon=True,
).start()
print(f"🌐 Health server on port {port}")

# ── Now load the bot (heavy imports: matplotlib, pandas, etc.) ──
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bot import CryptoBot

if __name__ == "__main__":
    bot = CryptoBot()
    bot.run()
