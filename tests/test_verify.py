"""Verify step result tests."""

import unittest

from lib.verify.step_verify import verify_dev_done, verify_step_result, verify_test_done
from lib.verify.runner import run_step_verify


class TestVerify(unittest.TestCase):
    def test_dev_self_test_fail(self):
        ok, err = verify_dev_done({"self_test": "fail"})
        self.assertFalse(ok)

    def test_test_missing_results_strict(self):
        ok, err = verify_test_done({}, strict=True)
        self.assertFalse(ok)

    def test_test_pass_with_results(self):
        ok, _ = verify_test_done({"results": [{"name": "a", "status": "pass"}]})
        self.assertTrue(ok)

    def test_role_type_6_pass(self):
        ok, _ = verify_step_result(6, "pass", {"details": {"results": [{"status": "pass"}]}})
        self.assertTrue(ok)


    def test_runner_skips_without_repo(self):
        ok, err, meta = run_step_verify(8, "done", {"details": {}}, config={}, data_dir="")
        self.assertTrue(ok)

    def test_git_check_no_repo(self):
        from lib.verify.git_check import git_diff_stat
        has, err, stat = git_diff_stat("/nonexistent")
        self.assertTrue(has)


if __name__ == "__main__":
    unittest.main()
