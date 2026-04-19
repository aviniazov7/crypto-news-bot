"""
Crypto News Bot — Interactive Telegram bot.
RSS + CoinGecko + Twitter + Gemini AI + Charts → Telegram
Zero dependencies — Python stdlib only.
"""

import os
import sys

# add src to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bot import CryptoBot

if __name__ == "__main__":
    bot = CryptoBot()
    bot.run()
