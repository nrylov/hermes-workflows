#!/usr/bin/env python3
"""SQLite store for job postings: ingest, score, digest, report. Stdlib only.

Commands (all take --db PATH; default ~/.hermes/job-pipeline/jobs.db):
  init                       create the database
  ingest                     stdin: JSON list from fetch_jobs; inserts unseen ids
  pending [--limit N]        unscored postings as JSON, newest first
  score                      stdin: JSON [{id, score(1-5), reason, summary}]
  digest [--min-score 4] [--mark]   Markdown with links for scored, not-yet-notified postings
  report OUT.html [--min-score 3]   interactive HTML report
  status ID STATE            set a posting's status (new/applied/interested/ignored)
  stats                      counts
  import-csv FILE [--mark-notified] migrate an old tracker.csv
"""
import argparse
import csv
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone

DEFAULT_DB = os.path.expanduser("~/.hermes/job-pipeline/jobs.db")
SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY, company TEXT, title TEXT, location TEXT, url TEXT,
  posted TEXT, first_seen TEXT NOT NULL, description TEXT DEFAULT '',
  score INTEGER, reason TEXT, scored_at TEXT, notified_at TEXT, status TEXT DEFAULT 'new');
CREATE INDEX IF NOT EXISTS jobs_score ON jobs(score);
CREATE INDEX IF NOT EXISTS jobs_seen ON jobs(first_seen);
"""
STATUSES = ("new", "interested", "applied", "interview", "rejected", "ignored")


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path=DEFAULT_DB):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    if "summary" not in {r[1] for r in con.execute("PRAGMA table_info(jobs)")}:
        con.execute("ALTER TABLE jobs ADD COLUMN summary TEXT")
        con.commit()
    return con


def known_ids(con):
    return {r[0] for r in con.execute("SELECT id FROM jobs")}


def ingest(con, jobs, now=None):
    """Insert postings whose id is new. Returns the number inserted."""
    now = now or now_iso()
    n = 0
    for j in jobs:
        cur = con.execute(
            "INSERT OR IGNORE INTO jobs (id, company, title, location, url, posted, first_seen, description)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (j["id"], j.get("company"), j.get("title"), j.get("location"), j.get("url"),
             j.get("posted"), now, j.get("description", "")))
        n += cur.rowcount
    con.commit()
    return n


def pending(con, limit=60):
    rows = con.execute(
        "SELECT id, company, title, location, url, posted, description FROM jobs WHERE score IS NULL"
        " ORDER BY COALESCE(posted, first_seen) DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]


def apply_scores(con, scores, now=None):
    """Returns (updated, problems). Scores outside 1-5 or unknown ids are reported, not applied."""
    now = now or now_iso()
    updated, problems = 0, []
    for s in scores:
        try:
            val = int(s["score"])
        except (KeyError, TypeError, ValueError):
            problems.append("bad score for %s" % s.get("id"))
            continue
        if not 1 <= val <= 5:
            problems.append("score out of range for %s: %s" % (s.get("id"), val))
            continue
        cur = con.execute("UPDATE jobs SET score=?, reason=?, summary=?, scored_at=? WHERE id=?",
                          (val, s.get("reason", ""), s.get("summary", ""), now, s.get("id")))
        if cur.rowcount:
            updated += 1
        else:
            problems.append("unknown id %s" % s.get("id"))
    con.commit()
    return updated, problems


def digest_rows(con, min_score=4):
    return con.execute(
        "SELECT * FROM jobs WHERE score >= ? AND notified_at IS NULL AND status != 'ignored'"
        " ORDER BY COALESCE(posted, first_seen) DESC, score DESC", (min_score,)).fetchall()


def age_days(row, now=None):
    now = now or datetime.now(timezone.utc)
    try:
        dt = datetime.fromisoformat((row["posted"] or row["first_seen"]).replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (now - dt).days


def format_digest(rows, now=None):
    if not rows:
        return ""
    lines = ["**%d new matching job%s**" % (len(rows), "" if len(rows) == 1 else "s"), ""]
    for r in rows:
        a = age_days(r, now)
        when = "today" if a == 0 else ("%dd ago" % a if a is not None else "")
        lines.append("- [%s: %s](%s) (%s, score %d, %s)" % (
            r["company"], (r["title"] or "").strip(), r["url"], (r["location"] or "").split("|")[0].strip(),
            r["score"], when))
        if r["summary"]:
            lines.append("  %s" % r["summary"])
        if r["reason"]:
            lines.append("  Fit: %s" % r["reason"])
    return "\n".join(lines)


def mark_notified(con, rows, now=None):
    now = now or now_iso()
    con.executemany("UPDATE jobs SET notified_at=? WHERE id=?", [(now, r["id"]) for r in rows])
    con.commit()


def report_rows(con, min_score=1):
    out = []
    for r in con.execute("SELECT * FROM jobs WHERE score >= ? ORDER BY score DESC, COALESCE(posted, first_seen) DESC",
                         (min_score,)):
        d = dict(r)
        d["posted"] = (d["posted"] or d["first_seen"] or "")[:10]
        out.append(d)
    return out


def stats(con):
    one = lambda q: con.execute(q).fetchone()[0]
    return {"total": one("SELECT COUNT(*) FROM jobs"),
            "unscored": one("SELECT COUNT(*) FROM jobs WHERE score IS NULL"),
            "score_4_5": one("SELECT COUNT(*) FROM jobs WHERE score>=4"),
            "unnotified_4_5": one("SELECT COUNT(*) FROM jobs WHERE score>=4 AND notified_at IS NULL"),
            "newest_first_seen": con.execute("SELECT MAX(first_seen) FROM jobs").fetchone()[0]}


def import_csv(con, path, mark=False):
    now = now_iso()
    n = 0
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            cur = con.execute(
                "INSERT OR IGNORE INTO jobs (id, company, title, location, url, first_seen, score, reason, scored_at,"
                " notified_at, status) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (r["id"], r.get("company"), r.get("title"), r.get("location"), r.get("url"), now,
                 int(r["score"]) if (r.get("score") or "").isdigit() else None, r.get("reason"), now,
                 now if mark else None, r.get("status") or "new"))
            n += cur.rowcount
    con.commit()
    return n


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["init", "ingest", "pending", "score", "digest", "report", "status", "stats", "import-csv"])
    ap.add_argument("args", nargs="*")
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--limit", type=int, default=60)
    ap.add_argument("--min-score", type=int)
    ap.add_argument("--mark", action="store_true")
    ap.add_argument("--mark-notified", action="store_true")
    a = ap.parse_args(argv)
    con = connect(a.db)

    if a.cmd == "init":
        print("ok %s" % a.db)
    elif a.cmd == "ingest":
        print("inserted %d" % ingest(con, json.load(sys.stdin)))
    elif a.cmd == "pending":
        json.dump(pending(con, a.limit), sys.stdout, indent=1)
        print()
    elif a.cmd == "score":
        updated, problems = apply_scores(con, json.load(sys.stdin))
        print("scored %d" % updated)
        for p in problems:
            print("problem: %s" % p, file=sys.stderr)
        return 1 if problems and not updated else 0
    elif a.cmd == "digest":
        rows = digest_rows(con, a.min_score or 4)
        print(format_digest(rows))
        if a.mark:
            mark_notified(con, rows)
    elif a.cmd == "report":
        import render_report
        out = a.args[0]
        with open(out, "w") as f:
            f.write(render_report.render(report_rows(con, a.min_score or 1)))
        print("wrote %s" % out)
    elif a.cmd == "status":
        if len(a.args) != 2 or a.args[1] not in STATUSES:
            ap.error("status ID %s" % "|".join(STATUSES))
        cur = con.execute("UPDATE jobs SET status=? WHERE id=?", (a.args[1], a.args[0]))
        con.commit()
        print("updated %d" % cur.rowcount)
    elif a.cmd == "stats":
        print(json.dumps(stats(con)))
    elif a.cmd == "import-csv":
        print("imported %d" % import_csv(con, a.args[0], a.mark_notified))
    return 0


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    sys.exit(main())
