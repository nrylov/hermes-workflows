---
name: feed-digest
description: Build a daily digest from RSS/Atom feeds on a schedule.
version: 0.1.0
author: Nikolai Rylov (nrylov), Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [rss, atom, digest, cron, automation]
    related_skills: []
---

# Feed Digest Skill

Fetches RSS/Atom feeds with a stdlib-only script, filters to recent items, and
has the agent write a short, cited briefing. Fetching is deterministic code;
the model only does the summarising.

## When to Use

- The user wants a recurring briefing from blogs, newsletters or release feeds.
- A cron job needs a compact, de-duplicated list of new items as input.

Don't use for: paywalled or login-only sources (the script reads public feeds).

## Prerequisites

- Python 3.8+. No third-party packages.
- A feeds file: one feed URL per line, `#` comments allowed (see `examples/feeds.txt`).

## How to Run

`terminal(command="python3 skills/feed-digest/scripts/fetch_feeds.py examples/feeds.txt --hours 24 --seen-file .seen.json")`

Output is JSON: `[{feed, title, link, published, summary}]`, newest first.

## Procedure

1. Run the script. Completion: exit code 0 and valid JSON on stdout.
2. If the list is empty, reply "Nothing new" and stop. Do not pad.
3. Group items by feed. Write 1-2 sentences per item, then the link.
4. Rank by relevance to the user's stated interests; put at most 5 under "Top picks".
5. Every claim must come from the item's `title`/`summary`. If more detail is
   needed, `web_extract` the link; never guess article contents.

## Pitfalls

- `--seen-file` records links already delivered; delete it to resend.
- A feed that errors is reported on stderr and skipped; other feeds still run.
- Some feeds omit dates. Those items are treated as new once, then tracked in the seen file.

## Verification

- `python3 -m unittest discover tests` passes.
- Running twice with the same `--seen-file` returns `[]` the second time.
