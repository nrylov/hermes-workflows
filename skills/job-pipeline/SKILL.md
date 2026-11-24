---
name: job-pipeline
description: Scan job boards into a database and report new matches.
version: 0.2.0
author: Nikolai Rylov (nrylov), Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [jobs, career, ats, sqlite, scoring, cron]
    related_skills: []
---

# Job Pipeline Skill

Code scans public ATS boards (Greenhouse, Lever, Ashby; thousands of companies),
keeps recent postings that fit, and stores them in SQLite. The agent only scores
fit against the user's profile and reports new matches. Nothing is ever submitted:
no applications, no messages.

## When to Use

- A recurring scan that alerts the user when new matching jobs appear.
- A one-off search, or reviewing the stored jobs.

Don't use for: auto-applying, scraping logged-in sites, or contacting recruiters.

## Prerequisites

Private working dir (default `~/.hermes/job-pipeline/`, never committed):
- `config.json`: filters, `max_age_days`, `companies_file` (see `examples/job_config.json`)
- `companies.json`: boards to search (`scripts/build_company_list.py`)
- `profile.md`: background, target roles, deal-breakers
- `companies_exclude` (in `config.json`): board names never fetched (agencies, aggregators,
  recruiters); also run `jobdb.py ignore-company NAME` to hide ones already stored
- `jobs.db`: created by `scripts/jobdb.py`

Python 3.8+, stdlib only. Optional: a Jina Reader API key (`$JINA_API_KEY` or
`jina_key_file` in `config.json`) for fetching full posting pages.

## How to Run

Setup once: `build_company_list.py ~/.hermes/job-pipeline/companies.json`
(optionally `--probe-slugs LIST.json --provider greenhouse` to add boards).

Scan: `terminal(command="python3 skills/job-pipeline/scripts/scan.py ~/.hermes/job-pipeline/config.json")`
prints `NEW: n | UNSCORED: m | boards failed: k`. As a cron `script` this makes quiet
scans cheap: when UNSCORED is 0, reply exactly `[SILENT]` and stop.

Read any posting page as Markdown: `terminal(command="python3 skills/job-pipeline/scripts/jina.py URL --key-file <path>")`.
The scan also does this automatically for new postings whose API description is shorter
than `enrich_min_chars`. The key is never printed; do not paste it into prompts or commits.

All database commands: `python3 skills/job-pipeline/scripts/jobdb.py <cmd> [--db PATH]`.

## Procedure

1. Scan (or read the injected scan summary). If UNSCORED is 0, reply `[SILENT]`.
2. `jobdb.py pending --limit 60` returns unscored postings newest first.
3. Read `profile.md`. For each posting write `score` (1-5), a one-line `reason` grounded
   in the posting text, and a `summary` of at most 2 sentences (role scope, stack,
   seniority/years, pay if stated, remote policy). Apply deal-breakers first (location,
   level, stack); violations score 1. Remote counts only if US-eligible. Thin description:
   score conservatively and say so. This is reading-and-summarising work, so a small
   model (e.g. a Haiku-class model) is enough; pin it on the cron job.
4. Save: pipe `[{"id","score","reason","summary"}]` into `jobdb.py score`. Completion: it prints
   `scored N` with N equal to the batch size. Do this before the next batch.
5. Repeat 2-4 until pending is empty (max 4 batches per run).
6. `jobdb.py report ~/.hermes/job-pipeline/report.html --min-score 3`.
7. `jobdb.py digest --min-score 4 --mark` prints the Markdown list with links and marks
   those jobs notified. Reply with that text verbatim, then `::preview{file="<abs path
   to report.html>"}` on its own line (desktop app). If the digest is empty, reply `[SILENT]`.
8. For a posting the user picks, draft talking points from `profile.md` only.
   `jobdb.py status ID applied|interested|ignored` records their decisions.

## Pitfalls

- Greenhouse list view has no description: the fetcher filters on age/title/location
  first and fetches detail only for survivors.
- Greenhouse rate-limits bursts: HTTP 429 on thousands of boards when a sweep sends ~9k requests in ~100 s (24 workers). Dead boards return 404 (~100 per sweep). Classify errors by status before concluding anything; the summary line only counts failures. Probe the full set, not a sample: a 600-board sample showed almost no 429s and missed the burst.
- Fix: `fetch_jobs.PacedFetcher` shares one slot schedule across workers (`requests_per_second`, default 20; `max_retries`, default 3, honoring `Retry-After`). Measured on the Greenhouse API: 10/s and 20/s gave zero 429s over 1,000 requests; 25/s hit 429 after ~500 requests. Keep 20/s or lower; do not raise the worker count to compensate. A full sweep at 20/s takes ~10 min.
- A full scan reports `boards failed` near the dead-board count (~100), not thousands. A count in the thousands means the pacing config was lost or the rate was raised.
- Generic titles pass only with `min_keyword_hits` of `description_keywords` in the text.
- Remote counts only for plain "Remote" or US-looking locations; extend `locations_exclude`.
- A posting is stored at first sight, so it is never re-fetched; unscored ones stay in
  `pending` until scored, so a crashed run loses nothing.
- Cron runs must not use `write_file` for staging: it refuses to overwrite a file the task
  has not read, and Hermes then appends a "file edit FAILED" warning to the delivered message.
  Stage with terminal redirects into unique names, or avoid files (stdout/stdin).
- Keep `config.json`, `companies.json`, `profile.md`, `jobs.db` out of public repos.

- The gateway may run on a different machine from the desktop app. Never `open` a URL from
  the agent to show the user a page: it opens on the gateway host. Give Markdown links in the
  reply instead (they open on the user's machine), plus the Copy link button in the report.

## Verification

- `python3 -m unittest discover tests` passes (offline).
- A second scan right after the first reports `NEW: 0`.
- `jobdb.py stats` shows `unscored: 0` after a completed run.
