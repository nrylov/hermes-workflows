#!/usr/bin/env python3
"""Replace thin descriptions of unscored postings with full page text from Jina Reader.

Some boards return only a stub (or nothing) in the API. For those, fetch the posting page.
"""
import os
import sys
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jina  # noqa: E402


def thin_rows(con, min_chars, limit):
    return con.execute(
        "SELECT id, url FROM jobs WHERE score IS NULL AND url != '' AND LENGTH(COALESCE(description,'')) < ?"
        " ORDER BY COALESCE(posted, first_seen) DESC LIMIT ?", (min_chars, limit)).fetchall()


def enrich(con, cfg, key, reader=jina.read_url, workers=6):
    """Returns (enriched, failed). Only overwrites when the fetched text is longer than what we had."""
    rows = thin_rows(con, cfg.get("enrich_min_chars", 400), cfg.get("enrich_max_per_run", 40))
    cap = cfg.get("description_chars", 2000)

    def one(r):
        try:
            return r["id"], jina.clean(reader(r["url"], key), cap)
        except Exception:
            return r["id"], None

    done = failed = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for jid, text in ex.map(one, rows):
            if text and len(text) > 200:
                con.execute("UPDATE jobs SET description=? WHERE id=? AND LENGTH(COALESCE(description,'')) < ?",
                            (text, jid, len(text)))
                done += 1
            else:
                failed += 1
    con.commit()
    return done, failed
