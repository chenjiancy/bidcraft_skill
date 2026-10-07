# -*- coding: utf-8 -*-
"""⑩ 数据一致性巡检单测：台账 ↔ 磁盘 ↔ 回收站三方对账。"""
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scripts"))

from _shared import core                          # noqa: E402
from _shared.core import ledger as _ledger        # noqa: E402
from _shared.core import trash as _trash          # noqa: E402


class ReconcileBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.lib = core.Library(self.tmp.name)
        self.ent, _ = self.lib.init_enterprise("对账测试企业")

    def tearDown(self):
        self.tmp.cleanup()

    def _write(self, rel):
        """在素材库分类目录下写一个文件并返回 rel。"""
        p = core.rel_to_path(core.lib_root(self.ent), rel)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x", encoding="utf-8")
        return rel

    def _ledger_row(self, rel, category="资质", subtype="营业执照", **kw):
        r = _ledger.new_ledger_row(category=category, subtype=subtype, rel_path=rel, **kw)
        return r


class TestConsistencyOk(ReconcileBase):
    def test_clean_library_ok(self):
        res = core.consistency_check(self.ent)
        self.assertTrue(res["ok"])
        self.assertEqual(res["summary"]["ledger_rows"], 0)
        self.assertEqual(res["issues"], [])

    def test_consistent_files_ok(self):
        rel = "资质/营业执照_20281231.jpg"
        self._write(rel)
        rows = [_ledger.new_ledger_row(category="资质", subtype="营业执照", rel_path=rel)]
        _ledger.save_ledger(self.ent, rows)
        res = core.consistency_check(self.ent)
        self.assertTrue(res["ok"], res["issues"])
        self.assertEqual(res["summary"]["disk_files"], 1)
        self.assertEqual(res["summary"]["ledger_unique_paths"], 1)


class TestConsistencyIssues(ReconcileBase):
    def test_ledger_dangling(self):
        # 台账有记录、磁盘无文件 → 悬空
        rel = "资质/资质证书_甲级_20281231.jpg"
        rows = [_ledger.new_ledger_row(category="资质", subtype="资质证书", rel_path=rel)]
        _ledger.save_ledger(self.ent, rows)
        res = core.consistency_check(self.ent)
        self.assertFalse(res["ok"])
        types = [i["type"] for i in res["issues"]]
        self.assertIn("台账悬空", types)
        self.assertNotIn("台账路径越界", types)  # 首段「资质」在分类目录内，不应触发越界

    def test_unregistered_file(self):
        # 磁盘有文件、台账无记录 → 未登记
        self._write("业绩/监理合同_P0.pdf")
        res = core.consistency_check(self.ent)
        self.assertFalse(res["ok"])
        self.assertIn("未登记文件", [i["type"] for i in res["issues"]])

    def test_duplicate_rel_path(self):
        rel = "资质/营业执照_20281231.jpg"
        self._write(rel)
        rows = [
            _ledger.new_ledger_row(category="资质", subtype="营业执照", rel_path=rel),
            _ledger.new_ledger_row(category="资质", subtype="营业执照", rel_path=rel),
        ]
        _ledger.save_ledger(self.ent, rows)
        res = core.consistency_check(self.ent)
        types = [i["type"] for i in res["issues"]]
        self.assertIn("台账重复路径", types)

    def test_rel_path_out_of_classify(self):
        # 台账路径首段不在分类目录 → 越界
        rows = [_ledger.new_ledger_row(category="资质", subtype="营业执照",
                                       rel_path="收件箱/x.jpg")]
        _ledger.save_ledger(self.ent, rows)
        res = core.consistency_check(self.ent)
        self.assertIn("台账路径越界", [i["type"] for i in res["issues"]])

    def test_trash_manifest_dangling(self):
        # 清单有记录、磁盘无 → 清单悬空
        rows = [{
            "file": "旧证书.jpg", "original_rel": "企业级/素材库/资质/旧证书.jpg",
            "reason": "测试", "deleted_at": core.now_iso(),
            "expire_at": (datetime.now() + timedelta(days=30)).isoformat(timespec="seconds"),
        }]
        _trash.save_trash_manifest(self.ent, rows)
        res = core.consistency_check(self.ent)
        self.assertIn("回收站清单悬空", [i["type"] for i in res["issues"]])

    def test_trash_orphan_file(self):
        # 磁盘有、清单无 → 孤儿文件
        tdir = _trash.trash_dir(self.ent)
        (tdir / "孤儿文件.txt").write_text("x", encoding="utf-8")
        res = core.consistency_check(self.ent)
        self.assertIn("回收站孤儿文件", [i["type"] for i in res["issues"]])

    def test_trash_expired_not_cleaned(self):
        # 已超保留期仍存在 → 过期未清理
        old = (datetime.now() - timedelta(days=31)).isoformat(timespec="seconds")
        tdir = _trash.trash_dir(self.ent)
        (tdir / "过期文件.jpg").write_text("x", encoding="utf-8")
        rows = [{
            "file": "过期文件.jpg", "original_rel": "企业级/素材库/资质/过期文件.jpg",
            "reason": "测试", "deleted_at": old,
            "expire_at": (datetime.now() + timedelta(days=30)).isoformat(timespec="seconds"),
        }]
        _trash.save_trash_manifest(self.ent, rows)
        res = core.consistency_check(self.ent)
        self.assertIn("回收站过期未清理", [i["type"] for i in res["issues"]])

    def test_multi_issue_summary_counts(self):
        # 多种问题共存时 summary 计数正确
        rel = "资质/营业执照_20281231.jpg"
        self._write(rel)                      # 未登记（台账无）
        rows = [_ledger.new_ledger_row(category="资质", subtype="营业执照", rel_path=rel)]
        _ledger.save_ledger(self.ent, rows)   # 登记后一致
        self._write("荣誉/荣誉证书_优秀_20280101.jpg")  # 未登记
        res = core.consistency_check(self.ent)
        self.assertEqual(res["summary"]["disk_files"], 2)
        self.assertEqual(res["summary"]["ledger_unique_paths"], 1)
        self.assertFalse(res["ok"])


if __name__ == "__main__":
    unittest.main()
