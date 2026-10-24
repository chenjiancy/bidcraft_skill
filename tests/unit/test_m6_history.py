# -*- coding: utf-8 -*-
"""C1 章节版本历史：snapshot 防抖四道 / 上限 / restore 双向撤销 / diff（链企引入第 1 项）。"""
import os
import shutil
import tempfile
import time
import unittest

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))

from m6_tech import history, store  # noqa: E402


def _mkimg(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x", encoding="utf-8")


class TestSnapshot(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="bid_hist_")
        self.tech = os.path.join(self.tmp, "技术标")
        os.makedirs(self.tech, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_empty_text_skipped(self):
        self.assertIsNone(history.snapshot(self.tech, "ch-01", ""))
        self.assertIsNone(history.snapshot(self.tech, "ch-01", "   \n "))
        self.assertEqual(history.versions(self.tech, "ch-01"), [])

    def test_dedup_same_text(self):
        e1 = history.snapshot(self.tech, "ch-01", "第一版正文内容", reason="write")
        e2 = history.snapshot(self.tech, "ch-01", "第一版正文内容", reason="write")
        self.assertIsNotNone(e1)
        self.assertIsNone(e2)  # 同文去重：不新增
        self.assertEqual(len(history.versions(self.tech, "ch-01")), 1)

    def test_merge_window_same_reason(self):
        history.snapshot(self.tech, "ch-01", "版本A", reason="rewrite")
        time.sleep(0.05)
        e = history.snapshot(self.tech, "ch-01", "版本B", reason="rewrite")
        vs = history.versions(self.tech, "ch-01")
        self.assertEqual(len(vs), 1)  # 2min 同 reason 合并 → 仍 1 版
        self.assertEqual(vs[0]["md5"], e["md5"])
        self.assertEqual(vs[0]["seq"], 1)

    def test_different_reason_new_version(self):
        history.snapshot(self.tech, "ch-01", "版本A", reason="draft")
        history.snapshot(self.tech, "ch-01", "版本B", reason="write")
        vs = history.versions(self.tech, "ch-01")
        self.assertEqual(len(vs), 2)
        self.assertEqual([v["seq"] for v in vs], [1, 2])

    def test_max_versions_evict_oldest(self):
        for i in range(history.MAX_VERSIONS + 5):
            history.snapshot(self.tech, "ch-01", "内容第%d版" % i, reason="r%d" % i)  # 不同 reason 避开合并窗口
        vs = history.versions(self.tech, "ch-01")
        self.assertEqual(len(vs), history.MAX_VERSIONS)
        # seq 递增不重排：25 次写入删最旧 5 版 → 剩余 seq 6..25
        self.assertEqual(vs[-1]["seq"], history.MAX_VERSIONS + 5)
        self.assertEqual(vs[0]["seq"], 6)  # 25 版删最旧 5 → 最旧 seq=6
        # 最旧 5 版文件已删，保留的最旧文件存在
        d = os.path.join(self.tech, ".history", "ch-01")
        for i in range(1, 6):
            self.assertFalse(os.path.exists(os.path.join(d, "v%03d.md" % i)))
        self.assertTrue(os.path.exists(os.path.join(d, "v%03d.md" % 6)))

    def test_read_version_and_restore(self):
        # 正文先落盘（首写无旧稿 → 不快照）
        from m4_tender import rules as _t
        from m6_tech.rules_base import GATES  # noqa: F401

        chapter = {"id": "ch-01", "files": {"body": "章节/ch-01.md"}}
        os.makedirs(os.path.join(self.tech, "章节"), exist_ok=True)
        store.write_chapter_body(self.tech, chapter, "旧正文A", reason="parse")
        # 第二次写 → 写前快照"旧正文A"（reason=rewrite）
        store.write_chapter_body(self.tech, chapter, "新正文B", reason="rewrite")
        vs = history.versions(self.tech, "ch-01")
        self.assertEqual(len(vs), 1)
        self.assertEqual(vs[0]["reason"], "rewrite")
        # 撤销到快照版本 → 写回"旧正文A"（写前快照"新正文B" reason=restore，可再撤销）
        store.write_chapter_body(self.tech, chapter,
                                 history.read_version(self.tech, "ch-01", vs[0]["seq"]),
                                 reason="restore")
        vs2 = history.versions(self.tech, "ch-01")
        self.assertEqual(len(vs2), 2)
        self.assertEqual(vs2[-1]["reason"], "restore")
        body = store.read_chapter_body(self.tech, chapter)
        self.assertEqual(body, "旧正文A")

    def test_diff_versions(self):
        history.snapshot(self.tech, "ch-01", "第一行\n第二行\n第三行", reason="a")
        history.snapshot(self.tech, "ch-01", "第一行\n第二行改\n第三行\n第四行", reason="b")
        d = history.diff_versions(self.tech, "ch-01", 1, 2)
        self.assertEqual(d["from"], 1)
        self.assertEqual(d["to"], 2)
        self.assertGreaterEqual(d["summary"]["modified"], 1)
        self.assertGreaterEqual(d["summary"]["added"], 1)

    def test_history_summary(self):
        history.snapshot(self.tech, "ch-01", "甲内容", reason="write")
        history.snapshot(self.tech, "ch-02", "乙内容", reason="write")
        s = history.history_summary(self.tech)
        self.assertEqual(set(s.keys()), {"ch-01", "ch-02"})
        self.assertEqual(s["ch-01"]["count"], 1)


class TestStoreHook(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="bid_hook_")
        self.tech = os.path.join(self.tmp, "技术标")
        os.makedirs(os.path.join(self.tech, "章节"), exist_ok=True)
        self.chapter = {"id": "ch-01", "files": {"body": "章节/ch-01.md"}}

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_write_chapter_body_snapshots_old(self):
        store.write_chapter_body(self.tech, self.chapter, "第一稿", reason="parse")   # 首写无旧稿 → 不快照
        store.write_chapter_body(self.tech, self.chapter, "第二稿", reason="rewrite") # 写前快照"第一稿"
        vs = history.versions(self.tech, "ch-01")
        self.assertEqual(len(vs), 1)
        self.assertEqual(vs[0]["reason"], "rewrite")
        # 回收站也有旧稿
        trash = os.path.join(self.tech, ".rewrite-trash")
        self.assertTrue(os.path.isdir(trash))

    def test_restore_roundtrip(self):
        store.write_chapter_body(self.tech, self.chapter, "第一稿", reason="parse")
        store.write_chapter_body(self.tech, self.chapter, "第二稿", reason="rewrite")
        vs = history.versions(self.tech, "ch-01")
        seq_first = vs[0]["seq"]  # =1（快照的是"第一稿"）
        store.write_chapter_body(self.tech, self.chapter,
                                 history.read_version(self.tech, "ch-01", seq_first),
                                 reason="restore")
        body = store.read_chapter_body(self.tech, self.chapter)
        self.assertEqual(body, "第一稿")


if __name__ == "__main__":
    unittest.main()
