---
name: evidence-audit
description: Audit a codebase against a reference with graded evidence.
version: 0.1.0
author: Nikolai Rylov (nrylov), Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [audit, gap-analysis, documentation, evidence]
    related_skills: []
---

# Evidence Audit Skill

A repeatable method for "what is missing or simplified compared to the
original/spec?" questions. Generalised from a real audit workflow used on a
game-preservation project: every finding carries a confidence grade, and
checked-and-fine items are recorded so nobody re-investigates them.

## When to Use

- Gap review of a port, reimplementation, or feature set versus a spec,
  reference product, or prior version.
- Producing or refreshing an audit document in the repo's `docs/`.

Don't use for: implementing fixes. The deliverable is a report.

## Procedure

1. Read the repo's agent/contributor notes and docs index. Open only the notes
   for the feature under audit. Completion: you can name the authoritative source.
2. Build the implemented set from code (registry, index, exports), never from a
   catalogue that also lists unimplemented items.
3. Mine docs for self-reported gaps: `search_files` for the phrases in
   `references/gap-phrases.md`. Record file path + exact phrase.
4. Confirm each candidate in code. No code and a doc admission = Missing.
   Reduced implementation present = Partial.
5. Verify the reference actually had the feature, using primary evidence
   (spec text, raw API output, transcript). Boilerplate does not count.
6. Grade each finding:
   - **Confirmed**: reference evidence and code gap both shown.
   - **Reported**: the repo's own notes assert it; reference silent.
   - **Partial**: reduced implementation exists.
7. List checked-and-not-a-gap items with the negative evidence.
8. Write `docs/<topic>-audit.md` from `references/report-template.md`, link it
   from the docs index. Completion: every finding has a grade, a path, and a
   one-line current state.

## Pitfalls

- Fetched pages are often truncated or redirect stubs; prefer raw/API output.
- Absence of evidence is not evidence of absence: keep as Reported, don't delete.
- Do not commit unless asked.

## Verification

- Every row in the report cites a file path and has exactly one grade.
- Report states what was run and what was not (tests, builds).
