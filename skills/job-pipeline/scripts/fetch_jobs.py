#!/usr/bin/env python3
"""Fetch postings from public ATS APIs (Greenhouse, Lever, Ashby), filter, de-dupe, print JSON.

Stdlib only. Only public job-board endpoints are used; nothing is applied to or posted.
"""
import argparse
import html
import json
import re
import sys
import urllib.request
from datetime import datetime, timezone

UA = "hermes-workflows-job-pipeline/0.1"


def http_json(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def strip_html(text):
    text = html.unescape(text or "")  # Greenhouse double-encodes its HTML
    text = re.sub(r"<[^>]+>", " ", html.unescape(text))
    return re.sub(r"\s+", " ", text).strip()


# ---- normalisers: each returns dicts with the same keys ---------------------------------

def norm_greenhouse(company, j):
    return {"id": "gh:%s:%s" % (company, j["id"]), "company": company, "title": j.get("title", ""),
            "location": (j.get("location") or {}).get("name", ""), "remote": None,
            "url": j.get("absolute_url", ""), "posted": j.get("first_published") or j.get("updated_at"),
            "description": strip_html(j.get("content", ""))}


def norm_lever(company, j):
    cat = j.get("categories") or {}
    ts = j.get("createdAt")
    posted = datetime.fromtimestamp(ts / 1000, timezone.utc).isoformat() if ts else None
    return {"id": "lv:%s:%s" % (company, j["id"]), "company": company, "title": j.get("text", ""),
            "location": cat.get("location", "") or "", "remote": (j.get("workplaceType") == "remote") or None,
            "url": j.get("hostedUrl", ""), "posted": posted,
            "description": (j.get("descriptionPlain") or strip_html(j.get("description", "")))}


def norm_ashby(company, j):
    return {"id": "ab:%s:%s" % (company, j["id"]), "company": company, "title": j.get("title", ""),
            "location": j.get("location", "") or "", "remote": j.get("isRemote"),
            "url": j.get("jobUrl", ""), "posted": j.get("publishedAt"),
            "description": j.get("descriptionPlain") or strip_html(j.get("descriptionHtml", ""))}


# ---- filtering --------------------------------------------------------------------------

def title_ok(title, include, exclude):
    t = title.lower()
    if any(re.search(p, t) for p in exclude):
        return False
    return not include or any(re.search(p, t) for p in include)


def location_ok(job, keywords):
    if not keywords:
        return True
    if job.get("remote"):
        return "remote" in [k.lower() for k in keywords]
    loc = (job.get("location") or "").lower()
    return any(k.lower() in loc for k in keywords)


def keep(job, cfg):
    return title_ok(job["title"], cfg.get("title_include", []), cfg.get("title_exclude", [])) \
        and location_ok(job, cfg.get("locations_include", []))


# ---- fetching ---------------------------------------------------------------------------

def fetch_company(c, cfg, fetcher=http_json):
    """Return filtered, normalised jobs for one company entry {name, ats}."""
    name, ats = c["name"], c["ats"]
    if ats == "greenhouse":
        base = "https://boards-api.greenhouse.io/v1/boards/%s/jobs" % name
        out = []
        for j in fetcher(base)["jobs"]:
            # the list view has no description: filter on title/location first, then fetch detail
            stub = norm_greenhouse(name, j)
            if keep(stub, cfg):
                detail = fetcher("%s/%s" % (base, j["id"]))
                out.append(norm_greenhouse(name, detail))
        return out
    if ats == "lever":
        raw = fetcher("https://api.lever.co/v0/postings/%s?mode=json" % name)
        return [n for n in (norm_lever(name, j) for j in raw) if keep(n, cfg)]
    if ats == "ashby":
        raw = fetcher("https://api.ashbyhq.com/posting-api/job-board/%s" % name)["jobs"]
        return [n for n in (norm_ashby(name, j) for j in raw if j.get("isListed", True)) if keep(n, cfg)]
    raise ValueError("unknown ats %r for %s" % (ats, name))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("config")
    ap.add_argument("--seen-file", help="JSON list of job ids already surfaced; updated in place")
    ap.add_argument("--max", type=int, help="override config max_per_run")
    args = ap.parse_args(argv)

    with open(args.config) as f:
        cfg = json.load(f)
    seen = set()
    if args.seen_file:
        try:
            with open(args.seen_file) as f:
                seen = set(json.load(f))
        except FileNotFoundError:
            pass

    found = []
    for c in cfg["companies"]:
        try:
            found.extend(j for j in fetch_company(c, cfg) if j["id"] not in seen)
        except Exception as exc:  # one broken board must not sink the run
            print("skip %s/%s: %s" % (c.get("ats"), c.get("name"), exc), file=sys.stderr)

    found.sort(key=lambda j: j["posted"] or "", reverse=True)
    limit = args.max or cfg.get("max_per_run", 25)
    found = found[:limit]
    for j in found:
        j["description"] = j["description"][: cfg.get("description_chars", 3000)]
    if args.seen_file:
        seen.update(j["id"] for j in found)
        with open(args.seen_file, "w") as f:
            json.dump(sorted(seen), f, indent=1)
    json.dump(found, sys.stdout, indent=1)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
