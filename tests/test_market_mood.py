"""Unit tests for the briefing mood classifier in src/news.py (pure logic)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import news  # noqa: E402


def prices(**changes):
    return {coin: {"usd_24h_change": change} for coin, change in changes.items()}


class MarketMoodTest(unittest.TestCase):
    def test_broad_rally_is_green(self):
        mood = news._market_mood(prices(bitcoin=3.0, ethereum=2.5, solana=1.5))
        self.assertEqual(mood, "🟢 השוק ירוק — עליות רחבות")

    def test_empty_and_missing_quotes_stay_stable(self):
        self.assertEqual(news._market_mood({}), "🟡 השוק יציב")
        self.assertEqual(news._market_mood(None), "🟡 השוק יציב")
        # No usd_24h_change key: the classifier treats the move as 0.
        flat = {"bitcoin": {"usd": 100000}, "ethereum": {"usd": 3000}}
        self.assertEqual(news._market_mood(flat), "🟡 השוק יציב")

    def test_crash_threshold_is_inclusive(self):
        mood = news._market_mood(prices(bitcoin=-5, ethereum=-5, solana=-5))
        self.assertEqual(mood, "🔴 יום אדום — מכירה רחבה")

    def test_alts_lead_when_btc_is_quiet(self):
        mood = news._market_mood(prices(bitcoin=0.4, ethereum=3.0, solana=4.0))
        self.assertEqual(mood, "🟢 אלטים מובילים — Risk-On")

    def test_non_numeric_change_raises(self):
        bad = prices(bitcoin="n/a", ethereum=1.0)
        with self.assertRaises(TypeError):
            news._market_mood(bad)


if __name__ == "__main__":
    unittest.main()
