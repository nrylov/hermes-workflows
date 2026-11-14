#!/usr/bin/env python3
"""One scan: fetch all boards, store new postings in the database, print a one-line summary.

Designed as a cron pre-run script. The summary tells the agent whether anything needs scoring:
  NEW: 3 | UNSCORED: 3 | boards failed: 39
Exit code is non-zero only when the fetch itself fails (all boards erroring).
"""
import argparse
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_jobs  # noqa: E402
import enrich  # noqa: E402
import jina  # noqa: E402
import jobdb  # noqa: E402


def scan(cfg, con, collect=fetch_jobs.collect, reader=jina.read_url):
    log = io.StringIO()
    found = collect(cfg, log=log)
    known = jobdb.known_ids(con)
    fresh = [j for j in found if j["id"] not in known]
    cap = cfg.get("description_chars", 2000)
    for j in fresh:
        j["description"] = j["description"][:cap]
    inserted = jobdb.ingest(con, fresh)
    key = jina.load_key(cfg.get("jina_key_file"))
    enriched = enrich.enrich(con, cfg, key, reader=reader)[0] if (key and inserted) else 0
    unscored = con.execute("SELECT COUNT(*) FROM jobs WHERE score IS NULL").fetchone()[0]
    failed = log.getvalue().strip().replace("boards failed: ", "")
    return inserted, unscored, failed, enriched


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("config")
    ap.add_argument("--db", default=jobdb.DEFAULT_DB)
    a = ap.parse_args(argv)
    with open(a.config) as f:
        cfg = json.load(f)
    con = jobdb.connect(a.db)
    inserted, unscored, failed, enriched = scan(cfg, con)
    print("NEW: %d | UNSCORED: %d | boards failed: %s | enriched via Jina: %d" % (inserted, unscored, failed or "0", enriched))
    return 0


if __name__ == "__main__":
    sys.exit(main())
