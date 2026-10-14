"""Wave B: FakeClock injection via AppContext."""
from __future__ import annotations

import unittest

from lib.infra.clock import FakeClock, now_iso, now_ts
from lib.composition import AppContext, reset_context, set_context
from lib.infra.constants import _now_iso


class TestClockInjection(unittest.TestCase):
    def tearDown(self) -> None:
        reset_context()

    def test_fake_clock_advances(self):
        clock = FakeClock(1_700_000_000.0)
        set_context(AppContext(clock=clock))
        self.assertEqual(now_ts(), 1_700_000_000.0)
        clock.advance(90)
        self.assertEqual(now_ts(), 1_700_000_090.0)
        iso = now_iso()
        self.assertTrue(iso.startswith("2023-") or iso.startswith("2024-") or "T" in iso)
        # constants hub
        self.assertEqual(_now_iso(), iso)

    def test_system_clock_default(self):
        reset_context()
        ts = now_ts()
        self.assertGreater(ts, 1_600_000_000.0)


if __name__ == "__main__":
    unittest.main()
