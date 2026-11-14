#!/usr/bin/env python3
"""Rank open PRs via `gh pr list --json`. Read-only."""
import json
import subprocess
import sys
from datetime import datetime, timezone

FIELDS = "number,title,isDraft,createdAt,additions,deletions,reviewDecision,statusCheckRollup,author"


def ci_state(rollup):
    if not rollup:
        return "unknown"
    states = [(c.get("conclusion") or c.get("state") or "").upper() for c in rollup]
    if any(s in ("FAILURE", "ERROR", "TIMED_OUT", "CANCELLED") for s in states):
        return "failing"
    if any(s in ("", "PENDING", "IN_PROGRESS", "QUEUED") for s in states):
        return "pending"
    return "passing"


def score(pr, now):
    """Higher = needs a human sooner."""
    if pr["isDraft"]:
        return 0
    s = 50
    ci = ci_state(pr.get("statusCheckRollup"))
    s += {"passing": 20, "pending": 0, "unknown": 0, "failing": -15}[ci]
    s += {"APPROVED": 25, "REVIEW_REQUIRED": 10, "CHANGES_REQUESTED": -10}.get(pr.get("reviewDecision") or "", 5)
    size = pr["additions"] + pr["deletions"]
    s += 10 if size < 100 else (0 if size < 500 else -10)
    age = (now - datetime.fromisoformat(pr["createdAt"].replace("Z", "+00:00"))).days
    if age > 30:
        return min(s, 10)  # stale PRs rank below anything active
    return s


def bucket(pr, now):
    age = (now - datetime.fromisoformat(pr["createdAt"].replace("Z", "+00:00"))).days
    ci = ci_state(pr.get("statusCheckRollup"))
    if pr["isDraft"] or age > 30:
        return "stale/draft"
    if ci == "failing":
        return "blocked on CI"
    if pr.get("reviewDecision") == "APPROVED" and ci == "passing":
        return "ready to merge"
    return "needs review"


def main(argv):
    if len(argv) != 2:
        print("usage: triage.py OWNER/REPO", file=sys.stderr)
        return 2
    out = subprocess.run(["gh", "pr", "list", "-R", argv[1], "--state", "open", "--limit", "100", "--json", FIELDS],
                         capture_output=True, text=True)
    if out.returncode:
        print(out.stderr, file=sys.stderr)
        return out.returncode
    now = datetime.now(timezone.utc)
    prs = sorted(json.loads(out.stdout), key=lambda p: -score(p, now))
    for p in prs:
        print("%3d  #%-5d %-14s ci=%-8s %+d/-%d  %s" % (score(p, now), p["number"], bucket(p, now),
              ci_state(p.get("statusCheckRollup")), p["additions"], p["deletions"], p["title"][:60]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
