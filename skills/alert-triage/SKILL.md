---
name: alert-triage
description: Triage an alert with read-only diagnostics and a runbook.
version: 0.1.0
author: Nikolai Rylov (nrylov), Hermes Agent
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [oncall, alerts, sre, triage, runbook]
    related_skills: []
---

# Alert Triage Skill

Turns an alert into a diagnosis: match it to a runbook, run only allowlisted
read-only diagnostic commands, and produce a report with proposed fixes. Fixes
are never executed by the script; each is labelled as needing human approval.

## When to Use

- An alert (JSON) arrives and the user wants likely cause and next steps.
- Building an oncall assistant that must stay safe by construction.

Don't use for: executing remediation. Ask the user, then run the step yourself
with `terminal` after approval.

## Prerequisites

- Python 3.8+, stdlib only.
- A runbook JSON (see `examples/runbook.json`): per-alert-name diagnostics
  (argv lists), hypotheses, and proposed remediation.

## How to Run

Demo, no infrastructure needed:

`terminal(command="python3 skills/alert-triage/scripts/triage_alert.py examples/alerts/high_disk.json --runbook examples/runbook.json --simulate examples/simulated_outputs.json")`

Real run: drop `--simulate`. Diagnostics run for real, but only if the command
matches the runbook's `allowlist` prefixes.

## Procedure

1. Run the script on the alert. Completion: exit 0 and a Markdown report.
2. If the report says `NO RUNBOOK`, say so, run only read-only commands you can
   justify, and recommend adding a runbook entry. Do not improvise fixes.
3. Read the diagnostics and state which hypothesis the evidence supports, and
   which it contradicts. Quote the output lines you relied on.
4. Present remediation steps as proposals. Wait for explicit approval before
   running any of them.
5. Close with what was checked, what was not, and confidence (high/medium/low).

## Pitfalls

- A command outside the allowlist is refused and reported, never run.
- No shell is used (argv lists only), so pipes and redirects in a runbook do not work by design.
- Evidence can be stale; always include the diagnostic timestamp from the report.

## Verification

- `python3 -m unittest discover tests` passes, including the allowlist-refusal tests.
- The demo output lists diagnostics, a supported hypothesis and approval-gated fixes.
