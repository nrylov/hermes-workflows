#!/usr/bin/env python3
"""Match an alert to a runbook, gather allowlisted read-only diagnostics, print a report.

Never executes remediation. Diagnostics are argv lists run without a shell.
"""
import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone


def load(path):
    with open(path) as f:
        return json.load(f)


def find_entry(runbook, alert):
    for entry in runbook.get("entries", []):
        if entry["alert"] == alert.get("name"):
            return entry
    return None


def is_allowed(argv, allowlist):
    """True if argv starts with one of the allowlisted argv prefixes."""
    if not argv or not all(isinstance(a, str) for a in argv):
        return False
    return any(argv[: len(p)] == p for p in allowlist)


def run_diag(argv, allowlist, simulated, timeout=15):
    key = " ".join(argv)
    if not is_allowed(argv, allowlist):
        return {"command": key, "status": "refused", "output": "not on allowlist"}
    if simulated is not None:
        if key in simulated:
            return {"command": key, "status": "simulated", "output": simulated[key]}
        return {"command": key, "status": "error", "output": "no simulated output"}
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
        return {"command": key, "status": "ok" if p.returncode == 0 else "error",
                "output": (p.stdout or p.stderr).strip()[:2000]}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"command": key, "status": "error", "output": str(exc)}


def evaluate(hypotheses, diags):
    """A hypothesis is supported if any of its `evidence` substrings appear in diagnostic output."""
    blob = "\n".join(d["output"] for d in diags if d["status"] in ("ok", "simulated"))
    out = []
    for h in hypotheses:
        hits = [e for e in h.get("evidence", []) if e in blob]
        out.append({"cause": h["cause"], "supported": bool(hits), "matched": hits})
    return out


def build_report(alert, entry, diags, hyps, now):
    L = ["# Alert triage: %s" % alert.get("name", "?"),
         "", "- Host: %s" % alert.get("host", "?"),
         "- Severity: %s" % alert.get("severity", "?"),
         "- Generated: %s" % now.isoformat(timespec="seconds"), ""]
    if entry is None:
        L += ["**NO RUNBOOK** for this alert. No diagnostics were run.", ""]
        return "\n".join(L)
    L.append("## Diagnostics")
    for d in diags:
        L += ["", "`%s` [%s]" % (d["command"], d["status"]), "```", d["output"], "```"]
    L += ["", "## Hypotheses"]
    for h in hyps:
        mark = "SUPPORTED" if h["supported"] else "not supported"
        extra = " (matched: %s)" % ", ".join(h["matched"]) if h["matched"] else ""
        L.append("- %s: %s%s" % (h["cause"], mark, extra))
    L += ["", "## Proposed remediation (requires human approval, NOT executed)"]
    for r in entry.get("remediation", []):
        L.append("- %s: `%s`" % (r["description"], " ".join(r["argv"])))
    L.append("")
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("alert")
    ap.add_argument("--runbook", required=True)
    ap.add_argument("--simulate", help="JSON mapping command string -> canned output")
    args = ap.parse_args(argv)

    alert, runbook = load(args.alert), load(args.runbook)
    simulated = load(args.simulate) if args.simulate else None
    entry = find_entry(runbook, alert)
    diags, hyps = [], []
    if entry:
        allow = runbook.get("allowlist", [])
        diags = [run_diag(c, allow, simulated) for c in entry.get("diagnostics", [])]
        hyps = evaluate(entry.get("hypotheses", []), diags)
    print(build_report(alert, entry, diags, hyps, datetime.now(timezone.utc)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
