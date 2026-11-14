# hermes-workflows

Reusable [Hermes Agent](https://github.com/NousResearch/hermes-agent) skills for
everyday AI workflow automation. Each skill pairs a short procedure for the agent
with a deterministic, tested helper script, so the model does judgement work and
code does the mechanical work.

| Skill | What it does | Helper |
|---|---|---|
| [`feed-digest`](skills/feed-digest) | Scheduled, de-duplicated RSS/Atom briefing with cited summaries | `fetch_feeds.py` (stdlib) |
| [`evidence-audit`](skills/evidence-audit) | Gap analysis of a codebase vs. a reference, with graded confidence | report template |
| [`pr-triage`](skills/pr-triage) | Ranks open PRs by CI, review state, size and age (read-only) | `triage.py` (via `gh`) |

## Design principles

- **Deterministic where possible.** Fetching, parsing and scoring are plain code with unit tests; the LLM summarises and judges.
- **Evidence over assertion.** Audits grade every claim (Confirmed / Reported / Partial) and record negative results.
- **Read-only by default.** Nothing here posts, merges or commits unless you ask.
- **No dependencies.** Python standard library only.

## Install

Copy a skill folder into your Hermes skills directory:

```bash
cp -r skills/feed-digest ~/.hermes/skills/productivity/
```

Start a new session; the skill appears in the index.

## Try it

```bash
python3 skills/feed-digest/scripts/fetch_feeds.py examples/feeds.txt --hours 48
python3 skills/pr-triage/scripts/triage.py NousResearch/hermes-agent
python3 -m unittest discover tests -v
python3 scripts/validate_skills.py
```

## Background

`evidence-audit` is generalised from a workflow I use on a historical-preservation
project, where claims about "what the original did" must be backed by primary
sources. `feed-digest` comes from a daily briefing cron I run with Hermes.

MIT licensed.
