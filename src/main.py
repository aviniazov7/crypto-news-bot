"""
Crypto News Bot — Interactive Telegram bot.
RSS + CoinGecko + Twitter + Gemini AI + Charts → Telegram
"""

import os
import sys
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

# add src to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bot import CryptoBot


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, format, *args):
        pass  # silence logs


def start_health_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    print(f"🌐 Health server on port {port}")
    server.serve_forever()


if __name__ == "__main__":
    # start health server for Render
    threading.Thread(target=start_health_server, daemon=True).start()

    bot = CryptoBot()
    bot.run()
