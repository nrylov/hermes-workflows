import importlib.util
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone

base = os.path.join(os.path.dirname(__file__), "..", "skills", "job-pipeline", "scripts")
sys.path.insert(0, base)
import jobdb  # noqa: E402
import scan  # noqa: E402


def job(i, **kw):
    d = {"id": i, "company": "acme", "title": "SRE", "location": "Remote", "url": "http://x/" + i,
         "posted": "2026-11-12T00:00:00+00:00", "description": "d"}
    d.update(kw)
    return d


class JobDbTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.con = jobdb.connect(os.path.join(self.tmp.name, "j.db"))

    def tearDown(self):
        self.con.close()
        self.tmp.cleanup()

    def test_ingest_dedupes(self):
        self.assertEqual(jobdb.ingest(self.con, [job("a"), job("b")]), 2)
        self.assertEqual(jobdb.ingest(self.con, [job("a"), job("c")]), 1)
        self.assertEqual(jobdb.known_ids(self.con), {"a", "b", "c"})

    def test_pending_newest_first_and_limit(self):
        jobdb.ingest(self.con, [job("old", posted="2026-11-01T00:00:00+00:00"), job("new", posted="2026-11-13T00:00:00+00:00")])
        self.assertEqual([p["id"] for p in jobdb.pending(self.con)], ["new", "old"])
        self.assertEqual(len(jobdb.pending(self.con, 1)), 1)

    def test_score_validation(self):
        jobdb.ingest(self.con, [job("a")])
        ok, problems = jobdb.apply_scores(self.con, [{"id": "a", "score": 5, "reason": "r"}, {"id": "zz", "score": 3},
                                                      {"id": "a", "score": 9}, {"id": "a", "score": "x"}])
        self.assertEqual(ok, 1)
        self.assertEqual(len(problems), 3)
        self.assertEqual(jobdb.pending(self.con), [])

    def test_digest_only_unnotified_and_min_score(self):
        jobdb.ingest(self.con, [job("a"), job("b"), job("c")])
        jobdb.apply_scores(self.con, [{"id": "a", "score": 5, "reason": "great"}, {"id": "b", "score": 3}, {"id": "c", "score": 4}])
        rows = jobdb.digest_rows(self.con, 4)
        self.assertEqual({r["id"] for r in rows}, {"a", "c"})
        text = jobdb.format_digest(rows, datetime(2026, 11, 13, tzinfo=timezone.utc))
        self.assertIn("[acme: SRE](http://x/a)", text)
        self.assertIn("2 new matching jobs", text)
        jobdb.mark_notified(self.con, rows)
        self.assertEqual(jobdb.digest_rows(self.con, 4), [])
        self.assertEqual(jobdb.format_digest([]), "")

    def test_ignored_not_in_digest(self):
        jobdb.ingest(self.con, [job("a")])
        jobdb.apply_scores(self.con, [{"id": "a", "score": 5}])
        self.con.execute("UPDATE jobs SET status='ignored'")
        self.assertEqual(jobdb.digest_rows(self.con), [])

    def test_ignore_company_hides_from_digest_and_report(self):
        jobdb.ingest(self.con, [job("a", company="Clera"), job("b", company="ok")])
        jobdb.apply_scores(self.con, [{"id": "a", "score": 5}, {"id": "b", "score": 5}])
        self.assertEqual(jobdb.ignore_company(self.con, "clera"), 1)
        self.assertEqual([r["id"] for r in jobdb.digest_rows(self.con)], ["b"])
        self.assertEqual([r["id"] for r in jobdb.report_rows(self.con)], ["b"])
        self.assertEqual(jobdb.ignore_company(self.con, "clera"), 0)

    def test_stats_and_report_rows(self):
        jobdb.ingest(self.con, [job("a"), job("b")])
        jobdb.apply_scores(self.con, [{"id": "a", "score": 4}])
        s = jobdb.stats(self.con)
        self.assertEqual((s["total"], s["unscored"], s["score_4_5"], s["unnotified_4_5"]), (2, 1, 1, 1))
        rows = jobdb.report_rows(self.con, 1)
        self.assertEqual([r["id"] for r in rows], ["a"])
        self.assertEqual(rows[0]["posted"], "2026-11-12")

    def test_import_csv(self):
        p = os.path.join(self.tmp.name, "t.csv")
        with open(p, "w") as f:
            f.write("id,company,title,location,url,score,reason,status\na,c,t,l,u,5,why,new\nb,c,t,l,u,,,new\n")
        self.assertEqual(jobdb.import_csv(self.con, p, mark=True), 2)
        self.assertEqual(jobdb.import_csv(self.con, p), 0)
        self.assertEqual(jobdb.digest_rows(self.con), [])  # marked notified, so not re-sent
        self.assertEqual(len(jobdb.pending(self.con)), 1)

    def test_scan_inserts_only_new_and_reports_counts(self):
        jobdb.ingest(self.con, [job("a")])
        found = [job("a"), job("b", description="x" * 5000)]

        def fake_collect(cfg, log=None):
            print("boards failed: 3", file=log)
            return found

        n, unscored, failed, enriched = scan.scan({"description_chars": 100}, self.con, collect=fake_collect)
        self.assertEqual((n, unscored, failed, enriched), (1, 2, "3", 0))
        row = self.con.execute("SELECT description FROM jobs WHERE id='b'").fetchone()
        self.assertEqual(len(row[0]), 100)

    def test_summary_stored_and_in_digest(self):
        jobdb.ingest(self.con, [job("a")])
        jobdb.apply_scores(self.con, [{"id": "a", "score": 5, "reason": "fits", "summary": "Go infra, senior"}])
        text = jobdb.format_digest(jobdb.digest_rows(self.con))
        self.assertIn("Go infra, senior", text)
        self.assertIn("Fit: fits", text)

    def test_migration_adds_summary_to_old_db(self):
        import sqlite3
        p = os.path.join(self.tmp.name, "old.db")
        c = sqlite3.connect(p)
        c.execute("CREATE TABLE jobs (id TEXT PRIMARY KEY, company TEXT, title TEXT, location TEXT, url TEXT, posted TEXT,"
                  " first_seen TEXT NOT NULL, description TEXT DEFAULT '', score INTEGER, reason TEXT, scored_at TEXT,"
                  " notified_at TEXT, status TEXT DEFAULT 'new')")
        c.commit()
        c.close()
        con = jobdb.connect(p)
        self.assertIn("summary", {r[1] for r in con.execute("PRAGMA table_info(jobs)")})
        con.close()

    def test_cli_roundtrip(self):
        db = os.path.join(self.tmp.name, "cli.db")
        import io
        from contextlib import redirect_stdout
        sys.stdin = io.StringIO(json.dumps([job("a")]))
        with redirect_stdout(io.StringIO()) as out:
            jobdb.main(["ingest", "--db", db])
        self.assertIn("inserted 1", out.getvalue())
        sys.stdin = io.StringIO(json.dumps([{"id": "a", "score": 5, "reason": "r"}]))
        with redirect_stdout(io.StringIO()):
            jobdb.main(["score", "--db", db])
        with redirect_stdout(io.StringIO()) as out:
            jobdb.main(["digest", "--db", db, "--mark"])
        self.assertIn("http://x/a", out.getvalue())
        with redirect_stdout(io.StringIO()) as out:
            jobdb.main(["digest", "--db", db])
        self.assertEqual(out.getvalue().strip(), "")


if __name__ == "__main__":
    unittest.main()
