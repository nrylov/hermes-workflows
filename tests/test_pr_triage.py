import importlib.util
import os
import unittest
from datetime import datetime, timezone

p = os.path.join(os.path.dirname(__file__), "..", "skills", "pr-triage", "scripts", "triage.py")
spec = importlib.util.spec_from_file_location("triage", p)
t = importlib.util.module_from_spec(spec)
spec.loader.exec_module(t)

NOW = datetime(2026, 11, 13, tzinfo=timezone.utc)


def pr(**kw):
    base = dict(number=1, title="x", isDraft=False, createdAt="2026-11-10T00:00:00Z", additions=10, deletions=5,
                reviewDecision="APPROVED", statusCheckRollup=[{"conclusion": "SUCCESS"}])
    base.update(kw)
    return base


class TriageTests(unittest.TestCase):
    def test_ci_states(self):
        self.assertEqual(t.ci_state([]), "unknown")
        self.assertEqual(t.ci_state([{"conclusion": "FAILURE"}]), "failing")
        self.assertEqual(t.ci_state([{"state": "PENDING"}]), "pending")
        self.assertEqual(t.ci_state([{"conclusion": "SUCCESS"}]), "passing")

    def test_ready_outranks_failing_and_draft(self):
        ready = pr()
        failing = pr(statusCheckRollup=[{"conclusion": "FAILURE"}])
        draft = pr(isDraft=True)
        self.assertGreater(t.score(ready, NOW), t.score(failing, NOW))
        self.assertEqual(t.score(draft, NOW), 0)

    def test_stale_ranks_below_active(self):
        stale = pr(createdAt="2026-01-01T00:00:00Z")
        failing = pr(statusCheckRollup=[{"conclusion": "FAILURE"}])
        self.assertLess(t.score(stale, NOW), t.score(failing, NOW))

    def test_buckets(self):
        self.assertEqual(t.bucket(pr(), NOW), "ready to merge")
        self.assertEqual(t.bucket(pr(statusCheckRollup=[{"conclusion": "FAILURE"}]), NOW), "blocked on CI")
        self.assertEqual(t.bucket(pr(createdAt="2026-01-01T00:00:00Z"), NOW), "stale/draft")
        self.assertEqual(t.bucket(pr(reviewDecision="REVIEW_REQUIRED"), NOW), "needs review")


if __name__ == "__main__":
    unittest.main()
