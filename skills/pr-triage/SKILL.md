---
name: pr-triage
description: Rank open pull requests by CI, review state and size.
version: 0.1.0
author: Nikolai Rylov (nrylov), Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [github, pull-requests, triage, review]
    related_skills: []
---

# PR Triage Skill

Ranks open PRs by what needs a human first, using CI state, review state and
size. Read-only: it never comments, approves or merges.

## When to Use

- "What PRs need my attention?" for one repo or an org.

## Prerequisites

- `gh auth status` succeeds.

## How to Run

`terminal(command="python3 skills/pr-triage/scripts/triage.py OWNER/REPO")`

## Procedure

1. Run the script; it prints a ranked table (score, PR, CI, reviews, size, age).
2. For the top 3, open the diff with `terminal(command="gh pr diff N")` and add a
   one-line risk note.
3. Report: ready to merge / blocked on CI / needs review / stale (>30 days).
   Completion: every open PR appears in exactly one bucket.

## Pitfalls

- Drafts are ranked last. Forks may hide CI status; shown as `unknown`.
- Pure Python plus `gh`; no shell pipelines, so it runs on any OS where `gh` is installed.

## Verification

- `python3 -m unittest discover tests` passes (scoring is unit-tested offline).
