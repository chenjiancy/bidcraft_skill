# -*- coding: utf-8 -*-
"""⑬ require_data 前置清单化单测：helper 自身行为（不依赖真实数据）。"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from _data_guard import require_data, skip_unless_data, env_ent_root, env_proj_root  # noqa: E402


class DataGuardBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        (self.base / "a.txt").write_text("x", encoding="utf-8")
        (self.base / "sub").mkdir()
        (self.base / "sub" / "b.json").write_text("{}", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()


class TestRequireData(DataGuardBase):
    def test_empty_list_ok(self):
        ok, missing = require_data([], base=self.base)
        self.assertTrue(ok)
        self.assertEqual(missing, [])

    def test_all_exist_ok(self):
        ok, missing = require_data(["a.txt", "sub/b.json"], base=self.base)
        self.assertTrue(ok)
        self.assertEqual(missing, [])

    def test_directory_exist_ok(self):
        ok, _ = require_data(["sub"], base=self.base)
        self.assertTrue(ok)

    def test_missing_reports_list(self):
        ok, missing = require_data(["a.txt", "不存在.json"], base=self.base)
        self.assertFalse(ok)
        self.assertEqual(missing, ["不存在.json"])

    def test_backslash_normalized(self):
        ok, missing = require_data([r"sub\b.json"], base=self.base)
        self.assertTrue(ok)
        self.assertEqual(missing, [])


class TestSkipUnlessData(DataGuardBase):
    def test_skip_when_missing(self):
        deco = skip_unless_data(["不存在.json"], base=self.base)

        @deco
        def f():
            raise AssertionError("不应执行")

        # 缺失数据时调用装饰结果应抛 SkipTest（reason 含缺失清单）
        try:
            f()
        except unittest.SkipTest as e:
            self.assertIn("不存在.json", str(e))
        else:
            self.fail("缺失数据时应抛出 SkipTest")

    def test_run_when_all_exist(self):
        deco = skip_unless_data(["a.txt"], base=self.base)

        @deco
        def f():
            return 42

        self.assertEqual(f(), 42)


class TestEnvPaths(unittest.TestCase):
    def test_defaults(self):
        self.assertTrue(str(env_ent_root()).endswith("示例建设工程监理有限公司"))
        self.assertTrue(str(env_proj_root()).startswith(str(env_ent_root())))
        self.assertTrue(str(env_proj_root()).endswith("示例化工园尾水水质提升工程（EPC总承包）监理"))


if __name__ == "__main__":
    unittest.main()
