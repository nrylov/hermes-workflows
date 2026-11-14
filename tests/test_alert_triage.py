import importlib.util
import json
import os
import unittest
from datetime import datetime, timezone

base = os.path.join(os.path.dirname(__file__), "..")
spec = importlib.util.spec_from_file_location("ta", os.path.join(base, "skills", "alert-triage", "scripts", "triage_alert.py"))
ta = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ta)

RB = ta.load(os.path.join(base, "examples", "runbook.json"))
SIM = ta.load(os.path.join(base, "examples", "simulated_outputs.json"))
NOW = datetime(2026, 11, 13, tzinfo=timezone.utc)


class AlertTriageTests(unittest.TestCase):
    def test_allowlist_prefix(self):
        al = RB["allowlist"]
        self.assertTrue(ta.is_allowed(["df", "-h", "/var"], al))
        self.assertFalse(ta.is_allowed(["rm", "-rf", "/"], al))
        self.assertFalse(ta.is_allowed(["du", "-sx", "/"], al))  # prefix is ["du","-sh"]
        self.assertFalse(ta.is_allowed([], al))
        self.assertFalse(ta.is_allowed(["df", 1], al))

    def test_refused_never_runs(self):
        d = ta.run_diag(["touch", "/tmp/should_not_exist_hw"], RB["allowlist"], None)
        self.assertEqual(d["status"], "refused")
        self.assertFalse(os.path.exists("/tmp/should_not_exist_hw"))

    def test_remediation_commands_are_not_allowlisted(self):
        for e in RB["entries"]:
            for r in e["remediation"]:
                self.assertFalse(ta.is_allowed(r["argv"], RB["allowlist"]), r["argv"])

    def test_demo_report_supports_log_hypothesis(self):
        alert = ta.load(os.path.join(base, "examples", "alerts", "high_disk.json"))
        entry = ta.find_entry(RB, alert)
        diags = [ta.run_diag(c, RB["allowlist"], SIM) for c in entry["diagnostics"]]
        hyps = ta.evaluate(entry["hypotheses"], diags)
        self.assertTrue(hyps[0]["supported"])
        self.assertFalse(hyps[1]["supported"])
        report = ta.build_report(alert, entry, diags, hyps, NOW)
        self.assertIn("requires human approval", report)
        self.assertIn("SUPPORTED", report)

    def test_no_runbook(self):
        alert = {"name": "Nope"}
        self.assertIsNone(ta.find_entry(RB, alert))
        self.assertIn("NO RUNBOOK", ta.build_report(alert, None, [], [], NOW))


if __name__ == "__main__":
    unittest.main()
