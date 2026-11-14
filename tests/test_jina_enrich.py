import os
import sys
import tempfile
import unittest

base = os.path.join(os.path.dirname(__file__), "..", "skills", "job-pipeline", "scripts")
sys.path.insert(0, base)
import enrich  # noqa: E402
import jina  # noqa: E402
import jobdb  # noqa: E402
import scan  # noqa: E402

PAGE = "Title: X\n\nURL Source: http://x\n\nMarkdown Content:\n**About** [us](http://a) ![img](http://i.png)\n\n\n\n\nWe use Go. " + "word " * 100


class JinaTests(unittest.TestCase):
    def test_clean_strips_header_links_images(self):
        out = jina.clean(PAGE)
        self.assertNotIn("URL Source", out)
        self.assertNotIn("http://", out)
        self.assertIn("**About** us", out)
        self.assertNotIn("\n\n\n", out)

    def test_load_key_env_then_file_and_never_blank(self):
        self.assertEqual(jina.load_key(None, env={"JINA_API_KEY": " k1 "}), "k1")
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
            f.write("filekey\n")
        try:
            self.assertEqual(jina.load_key(f.name, env={}), "filekey")
        finally:
            os.unlink(f.name)
        self.assertIsNone(jina.load_key(None, env={}))

    def test_read_url_sends_bearer_and_target(self):
        seen = {}

        class R:
            def read(self):
                return b"ok"

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

        def opener(req, timeout):
            seen["url"], seen["auth"] = req.full_url, req.get_header("Authorization")
            return R()

        self.assertEqual(jina.read_url("http://job", "KEY", opener=opener), "ok")
        self.assertEqual(seen["url"], "https://r.jina.ai/http://job")
        self.assertEqual(seen["auth"], "Bearer KEY")


class EnrichTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.con = jobdb.connect(os.path.join(self.tmp.name, "j.db"))
        base_job = {"company": "c", "title": "t", "location": "l", "posted": "2026-11-12T00:00:00+00:00"}
        jobdb.ingest(self.con, [dict(base_job, id="thin", url="http://thin", description="short"),
                                dict(base_job, id="full", url="http://full", description="x" * 1000),
                                dict(base_job, id="bad", url="http://bad", description="")])

    def tearDown(self):
        self.con.close()
        self.tmp.cleanup()

    def test_only_thin_unscored_rows_are_fetched(self):
        calls = []

        def reader(url, key):
            calls.append(url)
            if url == "http://bad":
                raise OSError("boom")
            return PAGE

        done, failed = enrich.enrich(self.con, {"enrich_min_chars": 400}, "k", reader=reader)
        self.assertEqual((done, failed), (1, 1))
        self.assertEqual(sorted(calls), ["http://bad", "http://thin"])
        desc = self.con.execute("SELECT description FROM jobs WHERE id='thin'").fetchone()[0]
        self.assertIn("We use Go", desc)

    def test_scan_skips_enrich_without_key(self):
        n, unscored, failed, enriched = scan.scan({}, self.con, collect=lambda cfg, log=None: [])
        self.assertEqual(enriched, 0)


if __name__ == "__main__":
    unittest.main()
