"""Inbox triage tests."""

import unittest

from lib.internal_llm.triage import scan_inbox_anomalies, triage_inbox_anomaly


class TestTriage(unittest.TestCase):
    def test_scan_empty_dir(self):
        anomalies = scan_inbox_anomalies("/nonexistent-mail-store")
        self.assertEqual(anomalies, [])

    def test_trigger_disabled(self):
        out = triage_inbox_anomaly("/nonexistent", {"mailbus_internal_llm": {"triggers": {}}})
        self.assertEqual(out.get("status"), "skipped")


if __name__ == "__main__":
    unittest.main()
