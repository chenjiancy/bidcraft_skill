# -*- coding: utf-8 -*-
"""C2 写盘安全四件套：原子写+退避+.bak+回读 / 坏 JSON 隔离 / 跨进程锁（链企引入第 2 项）。"""
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS = os.path.abspath(os.path.join(_HERE, "..", "..", "scripts"))
sys.path.insert(0, _SCRIPTS)

from _shared import core  # noqa: E402
from _shared.core import lock  # noqa: E402


class TestAtomicWrite(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="bid_atomic_")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_write_json_creates_and_reads_back(self):
        p = os.path.join(self.tmp, "台账.json")
        core.write_json(p, {"a": 1, "中文": "值"})
        self.assertTrue(os.path.exists(p))
        self.assertEqual(core.read_json(p), {"a": 1, "中文": "值"})

    def test_bak_created_on_overwrite(self):
        p = os.path.join(self.tmp, "data.json")
        core.write_json(p, {"v": 1})
        core.write_json(p, {"v": 2})
        bak = p + ".bak"
        self.assertTrue(os.path.exists(bak), ".bak 应保留上一版")
        self.assertEqual(core.read_json(bak), {"v": 1})

    def test_tmp_cleaned_after_write(self):
        p = os.path.join(self.tmp, "data.json")
        core.write_json(p, {"v": 1})
        self.assertFalse(os.path.exists(p + ".tmp"), "原子写后 .tmp 应清理")

    def test_atomic_write_text_roundtrip(self):
        p = os.path.join(self.tmp, "body.md")
        core.atomic_write_text(p, "第一行\n第二行")
        self.assertEqual(open(p, encoding="utf-8").read(), "第一行\n第二行")


class TestCorruptJson(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="bid_corrupt_")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write_bad(self, name="bad.json"):
        p = os.path.join(self.tmp, name)
        open(p, "w", encoding="utf-8").write('{"broken": ')
        return p

    def test_read_json_quarantines_corrupt(self):
        p = self._write_bad()
        self.assertEqual(core.read_json(p, default="DEFAULT"), "DEFAULT")
        # 现场保留：.corrupt-* 备份存在，原文件未被空内容覆盖
        corrupts = [f for f in os.listdir(self.tmp) if f.startswith("bad.json.corrupt-")]
        self.assertEqual(len(corrupts), 1)
        self.assertEqual(open(p, encoding="utf-8").read(), '{"broken": ')

    def test_read_json_strict_raises(self):
        p = self._write_bad()
        with self.assertRaises(core.LibraryError) as cm:
            core.read_json_strict(p, label="共享资源")
        self.assertIn("SIDECAR_CORRUPT", str(cm.exception))
        corrupts = [f for f in os.listdir(self.tmp) if "corrupt-" in f]
        self.assertEqual(len(corrupts), 1)

    def test_read_json_strict_missing_with_default(self):
        p = os.path.join(self.tmp, "nope.json")
        self.assertEqual(core.read_json_strict(p, default={"x": 1}), {"x": 1})


class TestFileLock(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="bid_lock_")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_lock_release_cycle(self):
        p = os.path.join(self.tmp, "data.json")
        with lock.file_lock(p, timeout=1.0):
            self.assertTrue(os.path.exists(p + ".lock"))
        self.assertFalse(os.path.exists(p + ".lock"), "释放后 lockfile 应删除")

    def test_second_lock_times_out(self):
        p = os.path.join(self.tmp, "data.json")
        with lock.file_lock(p, timeout=0.3):
            with self.assertRaises(core.LibraryError) as cm:
                with lock.file_lock(p, timeout=0.3):
                    pass
            self.assertIn("LOCK_BUSY", str(cm.exception))

    def test_cross_process_lock(self):
        """子进程持锁时本进程拿不到；子进程退出后 stale 抢占可拿到。"""
        p = os.path.join(self.tmp, "data.json")
        code = (
            "import os, sys, time\n"
            "sys.path.insert(0, os.environ['BIDCRAFT_SCRIPTS'])\n"
            "from _shared.core import lock\n"
            "with lock.file_lock(r'%s', timeout=5.0):\n"
            "    time.sleep(2.0)\n" % p
        )
        env = dict(os.environ)
        env["BIDCRAFT_SCRIPTS"] = _SCRIPTS
        proc = subprocess.Popen([sys.executable, "-c", code], env=env)
        time.sleep(0.8)  # 子进程已持锁
        self.assertTrue(os.path.exists(p + ".lock"))
        try:
            with lock.file_lock(p, timeout=0.5):
                self.fail("子进程持锁时不应拿到")
        except core.LibraryError as e:
            self.assertIn("LOCK_BUSY", str(e))
        proc.wait(timeout=10)  # 子进程释放并退出
        # 进程已死 → stale 抢占可立即拿到
        with lock.file_lock(p, timeout=2.0):
            self.assertTrue(os.path.exists(p + ".lock"))


if __name__ == "__main__":
    unittest.main()
