#!/usr/bin/env python3
"""Build a companies.json (Greenhouse/Lever/Ashby boards) from the public ats-directory dataset.

Usage: build_company_list.py OUT.json [--url URL] [--from-file companies.jsonl]
                             [--probe-slugs SLUGS.json --provider greenhouse|lever|ashby]
--probe-slugs takes a JSON array of candidate board names, tests each against the provider's
public API (in parallel) and merges the live ones. Only rows whose status is "ok" and whose provider is supported are kept. Slugs keep their case.
"""
import argparse
import gzip
import json
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

URL = "https://raw.githubusercontent.com/moonie0201/ats-directory/main/companies.jsonl.gz"
SUPPORTED = ("greenhouse", "lever", "ashby")


def parse_rows(lines):
    out, seen = [], set()
    for line in lines:
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        if r.get("status") != "ok" or r.get("provider") not in SUPPORTED:
            continue
        key = (r["provider"], r["slug"])
        if key in seen:
            continue
        seen.add(key)
        entry = {"name": r["slug"], "ats": r["provider"]}
        if r.get("region"):
            entry["region"] = r["region"]
        out.append(entry)
    return out


PROBE_URLS = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/%s/jobs",
    "lever": "https://api.lever.co/v0/postings/%s?mode=json&limit=1",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/%s",
}


def probe(provider, slug, opener=urllib.request.urlopen):
    """True if the provider's public API answers 200 with JSON for this board name."""
    try:
        req = urllib.request.Request(PROBE_URLS[provider] % slug, headers={"User-Agent": "hermes-workflows"})
        with opener(req, timeout=15) as r:
            json.load(r)
            return True
    except Exception:
        return False


def probe_many(provider, slugs, workers=24):
    with ThreadPoolExecutor(max_workers=workers) as ex:
        ok = list(ex.map(lambda s: probe(provider, s), slugs))
    return [{"name": s, "ats": provider} for s, good in zip(slugs, ok) if good]


def merge(existing, new):
    seen = {(c["ats"], c["name"].lower()) for c in existing}
    return existing + [c for c in new if (c["ats"], c["name"].lower()) not in seen]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("out")
    ap.add_argument("--url", default=URL)
    ap.add_argument("--from-file")
    ap.add_argument("--probe-slugs")
    ap.add_argument("--provider", choices=SUPPORTED)
    a = ap.parse_args(argv)
    if a.probe_slugs:
        if not a.provider:
            ap.error("--probe-slugs needs --provider")
        with open(a.out) as f:
            existing = json.load(f)
        have = {c["name"].lower() for c in existing if c["ats"] == a.provider}
        cands = [s for s in json.load(open(a.probe_slugs)) if s.lower() not in have]
        live = probe_many(a.provider, cands)
        merged = merge(existing, live)
        with open(a.out, "w") as f:
            json.dump(merged, f, indent=0)
        print("probed %d new %s slugs: %d live; total boards %d" % (len(cands), a.provider, len(live), len(merged)))
        return 0
    if a.from_file:
        lines = open(a.from_file).read().splitlines()
    else:
        req = urllib.request.Request(a.url, headers={"User-Agent": "hermes-workflows"})
        lines = gzip.decompress(urllib.request.urlopen(req, timeout=60).read()).decode().splitlines()
    rows = parse_rows(lines)
    with open(a.out, "w") as f:
        json.dump(rows, f, indent=0)
    by = {}
    for r in rows:
        by[r["ats"]] = by.get(r["ats"], 0) + 1
    print("wrote %d boards: %s" % (len(rows), by))
    return 0


if __name__ == "__main__":
    sys.exit(main())
