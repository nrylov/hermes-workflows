import csv
import importlib.util
import os
import tempfile
import unittest

base = os.path.join(os.path.dirname(__file__), "..", "skills", "job-pipeline", "scripts")


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(base, name + ".py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


fj, tr, rr = load("fetch_jobs"), load("tracker"), load("render_report")

CFG = {"title_include": ["sre", "infrastructure"], "title_exclude": ["manager", "intern"],
       "locations_include": ["remote", "san francisco"]}

GH_LIST = {"jobs": [
    {"id": 1, "title": "Senior Infrastructure Engineer", "location": {"name": "San Francisco, CA"}, "absolute_url": "u1"},
    {"id": 2, "title": "Infrastructure Manager", "location": {"name": "San Francisco, CA"}, "absolute_url": "u2"},
    {"id": 3, "title": "SRE", "location": {"name": "Berlin"}, "absolute_url": "u3"},
    {"id": 4, "title": "Account Executive", "location": {"name": "Remote"}, "absolute_url": "u4"}]}


class JobTests(unittest.TestCase):
    def test_strip_html_handles_double_encoding(self):
        self.assertEqual(fj.strip_html("&lt;p&gt;Hello &amp;amp; bye&lt;/p&gt;"), "Hello & bye")

    def test_title_filters(self):
        self.assertTrue(fj.title_ok("Senior SRE", ["sre"], ["manager"]))
        self.assertFalse(fj.title_ok("SRE Manager", ["sre"], ["manager"]))
        self.assertFalse(fj.title_ok("Chef", ["sre"], []))

    def test_location_filters(self):
        self.assertTrue(fj.location_ok({"location": "Remote - US", "remote": None}, ["remote"]))
        self.assertTrue(fj.location_ok({"location": "Berlin", "remote": True}, ["remote"]))
        self.assertFalse(fj.location_ok({"location": "Berlin", "remote": False}, ["remote", "san francisco"]))
        self.assertTrue(fj.location_ok({"location": "x", "remote": False}, []))

    def test_greenhouse_fetches_detail_only_for_survivors(self):
        calls = []

        def fake(url):
            calls.append(url)
            if url.endswith("/jobs"):
                return GH_LIST
            return {"id": 1, "title": "Senior Infrastructure Engineer", "location": {"name": "San Francisco, CA"},
                    "absolute_url": "u1", "content": "&lt;p&gt;Go and k8s&lt;/p&gt;"}

        jobs = fj.fetch_company({"name": "acme", "ats": "greenhouse"}, CFG, fetcher=fake)
        self.assertEqual([j["id"] for j in jobs], ["gh:acme:1"])
        self.assertEqual(jobs[0]["description"], "Go and k8s")
        self.assertEqual(len(calls), 2)  # list + one detail

    def test_ashby_unlisted_skipped_and_remote_flag(self):
        raw = {"jobs": [
            {"id": "a", "title": "SRE", "location": "Anywhere", "isRemote": True, "isListed": True, "jobUrl": "x", "descriptionPlain": "d"},
            {"id": "b", "title": "SRE", "location": "Anywhere", "isRemote": True, "isListed": False}]}
        jobs = fj.fetch_company({"name": "co", "ats": "ashby"}, CFG, fetcher=lambda u: raw)
        self.assertEqual([j["id"] for j in jobs], ["ab:co:a"])

    def test_lever(self):
        raw = [{"id": "z", "text": "Infrastructure Engineer", "categories": {"location": "San Francisco"},
                "hostedUrl": "h", "createdAt": 1700000000000, "descriptionPlain": "plain"}]
        jobs = fj.fetch_company({"name": "co", "ats": "lever"}, CFG, fetcher=lambda u: raw)
        self.assertEqual(jobs[0]["description"], "plain")
        self.assertTrue(jobs[0]["posted"].startswith("2023-11"))

    def test_unknown_ats(self):
        with self.assertRaises(ValueError):
            fj.fetch_company({"name": "x", "ats": "nope"}, CFG)

    def test_tracker_dedupes(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "t.csv")
            row = {"id": "a", "company": "c", "title": "t", "location": "l", "url": "u", "score": 4, "reason": "r"}
            self.assertEqual(tr.append(p, [row]), 1)
            self.assertEqual(tr.append(p, [row, dict(row, id="b")]), 1)
            with open(p, newline="") as f:
                rows = list(csv.DictReader(f))
            self.assertEqual([r["id"] for r in rows], ["a", "b"])
            self.assertEqual(rows[0]["status"], "new")

    def test_render_filters_and_escapes_script_end(self):
        rows = [{"id": "a", "company": "C", "title": "</script><b>x", "location": "l", "url": "u", "score": 5, "reason": "r"},
                {"id": "b", "company": "C", "title": "low", "location": "l", "url": "u", "score": 2, "reason": "r"}]
        out = rr.render(rows, min_score=4)
        self.assertIn('"id": "a"', out)
        self.assertNotIn('"id": "b"', out)
        data_line = [l for l in out.splitlines() if l.startswith("const D=")][0]
        self.assertNotIn("</script>", data_line)

    def test_load_rows_bad_score(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "t.csv")
            with open(p, "w") as f:
                f.write("id,company,title,location,url,score,reason,status\na,c,t,l,u,x,r,new\n")
            self.assertEqual(rr.load_rows(p)[0]["score"], 0)


if __name__ == "__main__":
    unittest.main()
