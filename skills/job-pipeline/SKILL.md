---
name: job-pipeline
description: Find, score and track job postings against your profile.
version: 0.1.0
author: Nikolai Rylov (nrylov), Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [jobs, career, ats, scoring, cron]
    related_skills: []
---

# Job Pipeline Skill

Deterministic code finds and filters postings from public ATS APIs
(Greenhouse, Lever, Ashby); the agent scores fit against the user's profile and
writes a short digest. Nothing is ever submitted: no applications, no messages.

## When to Use

- The user wants a recurring shortlist of relevant roles, or a one-off search.

Don't use for: auto-applying, scraping logged-in sites, or contacting recruiters.

## Prerequisites

- A private working dir (default `~/.hermes/job-pipeline/`, never committed) with:
  - `config.json`: companies, title/location filters (see `examples/job_config.json`)
  - `profile.md`: the user's background, target roles, deal-breakers
  - `seen.json` and `tracker.csv`: created by the scripts
- Python 3.8+, stdlib only.

## How to Run

`terminal(command="python3 skills/job-pipeline/scripts/fetch_jobs.py ~/.hermes/job-pipeline/config.json --seen-file ~/.hermes/job-pipeline/seen.json")`

## Procedure

1. Run the fetcher. Completion: exit 0 and a JSON list (possibly empty).
   Stderr `skip` lines are boards that failed; mention them, don't retry in a loop.
2. Optional breadth: for boards without a public API, `web_search` queries like
   `"site:jobs.lever.co OR site:boards.greenhouse.io <role> remote"`. Treat results as
   unverified until the posting URL is opened with `web_extract`.
3. Read `profile.md`. Score each job 1-5 for fit. Every score needs a one-line
   reason that quotes or paraphrases the posting (stack, level, location). If the
   description is thin, say so and score conservatively.
4. Apply deal-breakers from the profile first (location, level, clearance, stack).
   Violations score 1 regardless of title.
5. Pipe the scored list into `scripts/tracker.py ~/.hermes/job-pipeline/tracker.csv`.
   Completion: it prints `added N` where N equals the number of new jobs.
6. Render the viewable report: `terminal(command="python3 skills/job-pipeline/scripts/render_report.py ~/.hermes/job-pipeline/tracker.csv ~/.hermes/job-pipeline/report.html --min-score 3")`.
   In the Hermes desktop app, end the reply with `::preview{file="<absolute path to report.html>"}` on its own line.
7. Deliver a digest: top picks (score 4-5) with company, title, location, link, and
   the reason; then a one-line count of the rest. If nothing new, say "No new matches".
8. For a pick the user wants, draft tailored talking points mapped to the posting's
   requirements, using only facts in `profile.md`. Never invent experience.

## Pitfalls

- Greenhouse list view has no description; the fetcher filters on title/location
  first, then fetches detail only for survivors, to avoid hundreds of requests.
- A 404 for a company means a wrong board token or a different ATS; fix the config.
- Posting dates are the board's own; `seen.json` is what prevents repeats.
- Keep `config.json`, `profile.md`, and `tracker.csv` out of any public repo.

## Verification

- `python3 -m unittest discover tests` passes (filters and de-dupe tested offline).
- A second run with the same seen file returns `[]` unless new postings appeared.
