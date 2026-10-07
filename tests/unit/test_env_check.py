# -*- coding: utf-8 -*-
"""M0 env-check 单测：结构完整性（环境无关，任何机器/CI 均可通过）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scripts"))

from m0_env import run_env_checks, FONT_CHECKS          # noqa: E402


class TestEnvCheckStructure(unittest.TestCase):
    def test_result_structure(self):
        res = run_env_checks()
        self.assertIn("scanned_at", res)
        self.assertIn("checks", res)
        self.assertIn("summary", res)
        self.assertIn("ok", res)
        self.assertTrue(isinstance(res["ok"], bool))
        self.assertGreater(len(res["checks"]), 0)

    def test_each_check_shape(self):
        res = run_env_checks()
        for c in res["checks"]:
            self.assertIn("name", c)
            self.assertIn("status", c)
            self.assertIn("detail", c)
            self.assertIn(c["status"], ("ok", "warn", "fail"))

    def test_summary_counts_match_checks(self):
        res = run_env_checks()
        n_ok = sum(1 for c in res["checks"] if c["status"] == "ok")
        n_warn = sum(1 for c in res["checks"] if c["status"] == "warn")
        n_fail = sum(1 for c in res["checks"] if c["status"] == "fail")
        self.assertEqual(res["summary"]["ok"], n_ok)
        self.assertEqual(res["summary"]["warn"], n_warn)
        self.assertEqual(res["summary"]["fail"], n_fail)
        self.assertEqual(n_ok + n_warn + n_fail, len(res["checks"]))

    def test_ok_flag_consistent(self):
        res = run_env_checks()
        self.assertEqual(res["ok"], res["summary"]["fail"] == 0)

    def test_font_checks_constant(self):
        for family, label in FONT_CHECKS:
            self.assertTrue(family and label)
            # 罗马化字体名：字母数字 + 可选空格/下划线（如 FangSong_GB2312 / Microsoft YaHei）
            self.assertTrue(family.replace(" ", "").replace("_", "").isalnum(),
                            "family 应为罗马化字体名：%r" % family)


if __name__ == "__main__":
    unittest.main()
