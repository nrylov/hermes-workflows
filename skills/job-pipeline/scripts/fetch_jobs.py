#!/usr/bin/env python3
"""Fetch postings from public ATS APIs (Greenhouse, Lever, Ashby) at scale, newest first.

Stdlib only. Only public job-board endpoints are used; nothing is applied to or posted.
Dedupes against the tracker CSV (jobs are "seen" once scored, so a crashed run loses nothing).
"""
import argparse
import csv
import html
import json
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

UA = "hermes-workflows-job-pipeline/0.2"


def http_json(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


class PacedFetcher:
    """Shared rate limiter plus 429 retry for ATS APIs.

    Greenhouse answers bursts (~24 parallel workers) with HTTP 429 on thousands of boards.
    One shared slot schedule keeps all workers under `requests_per_second`; 429s are retried
    after Retry-After (or exponential backoff) and only then counted as failures.
    """

    def __init__(self, requests_per_second=20.0, max_retries=3, timeout=25):
        self.interval = 1.0 / float(requests_per_second)
        self.max_retries = int(max_retries)
        self.timeout = timeout
        self._lock = threading.Lock()
        self._next = 0.0
        self.stats = {"requests": 0, "retries_429": 0, "gave_up": 0}

    def _slot(self):
        with self._lock:
            at = max(time.time(), self._next)
            self._next = at + self.interval
        delay = at - time.time()
        if delay > 0:
            time.sleep(delay)

    def __call__(self, url):
        for attempt in range(self.max_retries + 1):
            self._slot()
            with self._lock:
                self.stats["requests"] += 1
            try:
                return http_json(url, timeout=self.timeout)
            except urllib.error.HTTPError as e:
                if e.code != 429 or attempt >= self.max_retries:
                    if e.code == 429:
                        with self._lock:
                            self.stats["gave_up"] += 1
                    raise
                with self._lock:
                    self.stats["retries_429"] += 1
                try:
                    wait = float(e.headers.get("Retry-After") or 5.0 * (2 ** attempt))
                except ValueError:
                    wait = 5.0 * (2 ** attempt)
                time.sleep(min(wait, 60))


def strip_html(text):
    text = html.unescape(text or "")  # Greenhouse double-encodes its HTML
    text = re.sub(r"<[^>]+>", " ", html.unescape(text))
    return re.sub(r"\s+", " ", text).strip()


def parse_dt(s):
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


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

def title_class(title, cfg):
    """'match' (title clearly fits), 'generic' (plausible, needs description evidence), or None."""
    t = title.lower()
    if any(re.search(p, t) for p in cfg.get("title_exclude", [])):
        return None
    inc = cfg.get("title_include", [])
    if not inc or any(re.search(p, t) for p in inc):
        return "match"
    if any(re.search(p, t) for p in cfg.get("title_generic", [])):
        return "generic"
    return None


def title_ok(title, include, exclude):  # kept for simple callers/tests
    return title_class(title, {"title_include": include, "title_exclude": exclude}) == "match"


REMOTE_HINTS = ("united states", "usa", "u.s.", "(us)", " us", "us-", "anywhere", "north america", "americas",
                "no preference")
# a bare country-wide label means "anywhere in the US", which is how boards list remote roles
US_WIDE = ("united states", "us", "usa", "u.s.", "united states of america", "remote - no preference")


def location_ok(job, keywords, exclude=(), remote_hints=REMOTE_HINTS):
    """Accept by location. Remote counts only when the location text is empty/plain "Remote"
    or looks US/anywhere, so "Sweden (Remote)" or isRemote=true + "Ho Chi Minh" are rejected."""
    loc = (job.get("location") or "").lower()
    # an excluded region only rejects the posting when it does not also list a US location
    if any(x.lower() in loc for x in exclude) and not any(h in (" " + loc) for h in remote_hints):
        return False
    if not keywords:
        return True
    kws = [k.lower() for k in keywords]
    if any(k != "remote" and k in loc for k in kws):
        return True
    if "remote" in kws and (job.get("remote") or "remote" in loc or loc.strip() in US_WIDE):
        return loc.strip() in ("", "remote", "remote only") or loc.strip() in US_WIDE \
            or any(h in (" " + loc) for h in remote_hints)
    return False


def age_ok(job, cfg, now):
    days = cfg.get("max_age_days")
    dt = parse_dt(job.get("posted"))
    if not days or dt is None:  # undated postings are kept; scoring can judge
        return True
    return dt >= now - timedelta(days=days)


def keyword_hits(text, cfg):
    t = text.lower()
    return sum(1 for k in cfg.get("description_keywords", []) if k.lower() in t)


def cheap_ok(job, cfg, now):
    """Filters that need only list-view fields. Returns the title class or None."""
    if not age_ok(job, cfg, now) or not location_ok(job, cfg.get("locations_include", []), cfg.get("locations_exclude", [])):
        return None
    return title_class(job["title"], cfg)


def accept(job, cls, cfg):
    if cls == "match":
        return True
    return cls == "generic" and keyword_hits(job["description"], cfg) >= cfg.get("min_keyword_hits", 3)


# ---- fetching ---------------------------------------------------------------------------

def fetch_company(c, cfg, fetcher=http_json, now=None):
    """Return filtered, normalised jobs for one company entry {name, ats[, region]}."""
    now = now or datetime.now(timezone.utc)
    name, ats = c["name"], c["ats"]
    out = []
    if ats == "greenhouse":
        base = "https://boards-api.greenhouse.io/v1/boards/%s/jobs" % name
        for j in fetcher(base)["jobs"]:
            cls = cheap_ok(norm_greenhouse(name, j), cfg, now)
            if cls:  # the list view has no description: fetch detail only for survivors
                full = norm_greenhouse(name, fetcher("%s/%s" % (base, j["id"])))
                if accept(full, cls, cfg):
                    out.append(full)
        return out
    if ats == "lever":
        host = "api.eu.lever.co" if c.get("region") == "eu" else "api.lever.co"
        norm = norm_lever
        raw = fetcher("https://%s/v0/postings/%s?mode=json" % (host, name))
    elif ats == "ashby":
        norm = norm_ashby
        raw = [j for j in fetcher("https://api.ashbyhq.com/posting-api/job-board/%s" % name)["jobs"]
               if j.get("isListed", True)]
    else:
        raise ValueError("unknown ats %r for %s" % (ats, name))
    for j in raw:
        n = norm(name, j)
        cls = cheap_ok(n, cfg, now)
        if cls and accept(n, cls, cfg):
            out.append(n)
    return out


def load_companies(cfg):
    """Merge inline `companies` with the JSON list at `companies_file`, de-duplicated."""
    items = list(cfg.get("companies", []))
    if cfg.get("companies_file"):
        with open(cfg["companies_file"]) as f:
            items += json.load(f)
    blocked = {c.lower() for c in cfg.get("companies_exclude", [])}
    seen, out = set(), []
    for c in items:
        key = (c["ats"], c["name"].lower())
        if key not in seen and c["name"].lower() not in blocked:
            seen.add(key)
            out.append(c)
    return out


def tracked_ids(path):
    try:
        with open(path, newline="") as f:
            return {r["id"] for r in csv.DictReader(f)}
    except FileNotFoundError:
        return set()


def collect(cfg, workers=8, fetcher=None, now=None, log=sys.stderr):
    if fetcher is None:
        fetcher = PacedFetcher(
            requests_per_second=cfg.get("requests_per_second", 20),
            max_retries=cfg.get("max_retries", 3),
        )

    def one(c):
        try:
            return fetch_company(c, cfg, fetcher=fetcher, now=now), None
        except Exception as exc:  # one broken board must not sink the run
            return [], "%s/%s: %s" % (c.get("ats"), c.get("name"), exc)

    found, errors = [], 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for jobs, err in ex.map(one, load_companies(cfg)):
            found.extend(jobs)
            errors += bool(err)
    print("boards failed: %d" % errors, file=log)
    return found


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("config")
    ap.add_argument("--tracker", help="tracker.csv; jobs already in it are skipped")
    ap.add_argument("--max", type=int, help="override config max_per_run")
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args(argv)

    with open(args.config) as f:
        cfg = json.load(f)
    done = tracked_ids(args.tracker) if args.tracker else set()
    found = [j for j in collect(cfg, args.workers) if j["id"] not in done]
    found.sort(key=lambda j: parse_dt(j["posted"]) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    total = len(found)
    found = found[: args.max or cfg.get("max_per_run", 40)]
    now = datetime.now(timezone.utc)
    for j in found:
        dt = parse_dt(j["posted"])
        j["age_days"] = (now - dt).days if dt else None
        j["description"] = j["description"][: cfg.get("description_chars", 3000)]
    print("unscored matches: %d, returning %d (newest first)" % (total, len(found)), file=sys.stderr)
    json.dump(found, sys.stdout, indent=1)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
