import importlib.util
import os
import unittest
from datetime import datetime, timedelta, timezone

p = os.path.join(os.path.dirname(__file__), "..", "skills", "feed-digest", "scripts", "fetch_feeds.py")
spec = importlib.util.spec_from_file_location("fetch_feeds", p)
ff = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ff)

RSS = b"""<rss><channel><title>Blog A</title>
<item><title>New</title><link>http://a/new</link><pubDate>Fri, 13 Nov 2026 10:00:00 GMT</pubDate><description>d</description></item>
<item><title>Old</title><link>http://a/old</link><pubDate>Mon, 01 Jun 2026 10:00:00 GMT</pubDate></item>
<item><title>Undated</title><link>http://a/u</link></item>
</channel></rss>"""

ATOM = b"""<feed xmlns="http://www.w3.org/2005/Atom"><title>Blog B</title>
<entry><title>E1</title><link rel="alternate" href="http://b/1"/><updated>2026-11-13T09:00:00Z</updated><summary>s</summary></entry>
</feed>"""

NOW = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)


class FeedDigestTests(unittest.TestCase):
    def test_parse_rss(self):
        items = ff.parse_feed(RSS)
        self.assertEqual([i["title"] for i in items], ["New", "Old", "Undated"])
        self.assertEqual(items[0]["feed"], "Blog A")
        self.assertIsNone(items[2]["published"])

    def test_parse_atom(self):
        items = ff.parse_feed(ATOM)
        self.assertEqual(items[0]["link"], "http://b/1")
        self.assertEqual(items[0]["published"], datetime(2026, 11, 13, 9, tzinfo=timezone.utc))

    def test_select_window_and_undated(self):
        out = ff.select_items(ff.parse_feed(RSS), NOW, 24, set())
        self.assertEqual([i["title"] for i in out], ["New", "Undated"])

    def test_seen_filtering(self):
        out = ff.select_items(ff.parse_feed(RSS), NOW, 24, {"http://a/new", "http://a/u"})
        self.assertEqual(out, [])

    def test_parse_date_naive_is_utc(self):
        self.assertEqual(ff.parse_date("2026-11-13T09:00:00").tzinfo, timezone.utc)
        self.assertIsNone(ff.parse_date("garbage"))


if __name__ == "__main__":
    unittest.main()
