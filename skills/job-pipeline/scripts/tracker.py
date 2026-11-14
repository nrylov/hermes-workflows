#!/usr/bin/env python3
"""Append scored jobs to a CSV tracker, skipping ids already present.

Usage: tracker.py TRACKER.csv < scored.json
Input JSON: [{id, company, title, location, url, score, reason}]
"""
import csv
import json
import os
import sys

COLUMNS = ["id", "company", "title", "location", "url", "score", "reason", "status"]


def existing_ids(path):
    if not os.path.exists(path):
        return set()
    with open(path, newline="") as f:
        return {r["id"] for r in csv.DictReader(f)}


def append(path, rows):
    have = existing_ids(path)
    new = [r for r in rows if r["id"] not in have]
    fresh = not os.path.exists(path)
    with open(path, "a", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        if fresh:
            wr.writeheader()
        for r in new:
            wr.writerow(dict(r, status=r.get("status", "new")))
    return len(new)


def main(argv):
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    print("added %d" % append(argv[1], json.load(sys.stdin)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
