"""Regression tests for RSS scraping in src/news.py (stdlib only, no network)."""

import contextlib
import email.utils
import io
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import news  # noqa: E402

NOW_RFC822 = email.utils.format_datetime(datetime.now(timezone.utc))
CUTOFF = datetime.now(timezone.utc) - timedelta(hours=news.HOURS_BACK)

# An HTML challenge/error page served with HTTP 200 instead of RSS.
HTML_PAGE = (
    b"<!DOCTYPE html><html><head><meta charset=utf-8><title>Just a moment...</title>"
    b"</head><body>Checking your browser<br></body></html>"
)


def rss(title):
    return (
        '<?xml version="1.0"?><rss><channel><item>'
        f"<title>{title}</title><link>https://example.com/{abs(hash(title))}</link>"
        "<description>Spot bitcoin ETFs recorded strong inflows today.</description>"
        f"<pubDate>{NOW_RFC822}</pubDate>"
        "</item></channel></rss>"
    ).encode()


class ScrapeFeedTest(unittest.TestCase):
    def test_malformed_feed_is_skipped(self):
        feed = {"name": "Broken", "url": "https://broken.example/rss"}
        out = io.StringIO()
        with mock.patch.object(news, "http_get", return_value=HTML_PAGE), \
                contextlib.redirect_stdout(out):
            self.assertEqual(news.scrape_feed(feed, CUTOFF), [])
        self.assertIn("Broken", out.getvalue())

    def test_valid_feed_is_parsed(self):
        feed = {"name": "Good", "url": "https://good.example/rss"}
        with mock.patch.object(news, "http_get", return_value=rss("Bitcoin ETF inflows jump")):
            items = news.scrape_feed(feed, CUTOFF)
        self.assertEqual([i["title"] for i in items], ["Bitcoin ETF inflows jump"])

    def test_one_malformed_feed_does_not_drop_the_others(self):
        feeds = [
            {"name": "Good A", "url": "https://a.example/rss"},
            {"name": "Broken", "url": "https://broken.example/rss"},
            {"name": "Good B", "url": "https://b.example/rss"},
        ]
        responses = {
            "https://a.example/rss": rss("Bitcoin rallies as ETF demand grows"),
            "https://broken.example/rss": HTML_PAGE,
            "https://b.example/rss": rss("Ethereum staking inflows hit record"),
        }
        with mock.patch.object(news, "RSS_FEEDS", feeds), \
                mock.patch.object(news, "http_get", side_effect=lambda url, **kw: responses[url]), \
                contextlib.redirect_stdout(io.StringIO()):
            items = news.fetch_all_news()
        self.assertEqual({i["source"] for i in items}, {"Good A", "Good B"})


if __name__ == "__main__":
    unittest.main()
