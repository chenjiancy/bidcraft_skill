# -*- coding: utf-8 -*-
"""L2 集成测试：存储层 core（三层目录 / 台账 / 收件箱 / 回收站 / 巡检 / 检索）。
全部使用临时素材根，绝不触碰真实素材库。"""
import json
import os
import sys
import tempfile
import unittest
import shutil
from pathlib import Path

_SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scripts")
sys.path.insert(0, os.path.abspath(_SCRIPTS))
from _shared import core  # noqa: E402


class CoreBase(unittest.TestCase):
    ENT = "测试企业有限公司"

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="bid_it_")
        self.root = Path(self.tmp)
        self.lib = core.Library(self.root)
        self.ent, self.existed = self.lib.init_enterprise(self.ENT)
        self.ent_dir = Path(self.ent)
        self.libroot = core.lib_root(self.ent)  # 企业级/业绩库

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _make_file(self, name, content="dummy"):
        p = Path(self.tmp) / name
        p.write_text(content, encoding="utf-8")
        return str(p)


class TestInitStructure(CoreBase):
    def test_three_layer(self):
        self.assertTrue((self.ent_dir / "项目级").is_dir())
        self.assertTrue((self.ent_dir / "企业级" / "模板库").is_dir())
        for sub in core.ENTERPRISE_SUBDIRS:
            self.assertTrue((self.libroot / sub).is_dir(), "缺 %s" % sub)
        self.assertTrue((self.libroot / core.LEDGER_JSON).exists())
        self.assertTrue((self.libroot / core.META_JSON).exists())

    def test_lib_root_path(self):
        self.assertEqual(core.lib_root(self.ent), self.ent_dir / "企业级" / "业绩库")

    def test_enterprises_and_resolve(self):
        self.assertIn(self.ENT, self.lib.enterprises())
        self.assertEqual(self.lib.resolve(self.ENT), self.ent_dir)

    def test_init_is_idempotent(self):
        ent2, existed = self.lib.init_enterprise(self.ENT)
        self.assertTrue(existed)
        self.assertEqual(ent2, self.ent_dir)


class TestInbox(CoreBase):
    def test_upload_and_close(self):
        inbox = core.Inbox(self.ent)
        b = inbox.open(note="b1")
        self.assertIsNotNone(b["batch_id"])
        it = inbox.add(self._make_file("ISO9001_20260101.pdf"))
        self.assertEqual(it["seq"], 1)
        self.assertEqual(it["via"], "upload")
        inbox.close()
        self.assertTrue(inbox.load()["closed_at"])

    def test_upload_requires_open(self):
        inbox = core.Inbox(self.ent)
        with self.assertRaises(core.LibraryError):
            inbox.add(self._make_file("x.pdf"))

    def test_sync_folder_files(self):
        inbox = core.Inbox(self.ent)
        inbox.open()
        # 直接拷一个文件进收件箱文件夹
        f = self._make_file("身份证_人像面.jpg")
        dest = inbox.dir / "身份证_人像面.jpg"
        shutil.copy2(f, dest)
        added = inbox.sync()
        self.assertEqual(len(added), 1)
        self.assertEqual(added[0]["via"], "folder")

    def test_upload_dup_renames(self):
        inbox = core.Inbox(self.ent)
        inbox.open()
        inbox.add(self._make_file("a.pdf"))
        inbox.add(self._make_file("a.pdf"))
        files = [i["file"] for i in inbox.items()]
        self.assertNotEqual(files[0], files[1])
        self.assertTrue(any("_dup2" in f for f in files))


class TestArchiveFlow(CoreBase):
    def _upload_and_propose(self, files):
        inbox = core.Inbox(self.ent)
        inbox.open(note="b")
        for f in files:
            inbox.add(self._make_file(f))
        inbox.close()
        return core.propose(self.ent, require_closed=True)

    def test_propose_apply_lands_in_lib(self):
        prop = self._upload_and_propose(["ISO9001_20260101.pdf"])
        prop["items"][0]["category"] = "资质"
        prop["items"][0]["subtype"] = "体系认证"
        res = core.apply(self.ent, prop)
        self.assertEqual(res["summary"]["archived"], 1)
        self.assertTrue((self.libroot / "资质" / "ISO9001_20260101.pdf").exists())
        rows = core.load_ledger(self.ent)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["category"], "资质")

    def _archive(self, fname, cat="资质", sub="体系认证"):
        """上传并归档单份文件。"""
        inbox = core.Inbox(self.ent)
        inbox.open()
        inbox.add(self._make_file(fname))
        inbox.close()
        prop = core.propose(self.ent, require_closed=True)
        it = prop["items"][0]
        it["category"], it["subtype"] = cat, sub
        core.apply(self.ent, prop)

    def _upload_propose(self, fname):
        """仅上传不归档，返回 propose。"""
        inbox = core.Inbox(self.ent)
        inbox.open()
        inbox.add(self._make_file(fname))
        inbox.close()
        return core.propose(self.ent, require_closed=True)

    def test_name_conflict_and_confirm(self):
        self._archive("ISO9001_20260101.pdf")
        # 第二份同关键字（不同日期）→ 判定同名冲突
        prop2 = self._upload_propose("ISO9001_20270101.pdf")
        it2 = prop2["items"][0]
        self.assertTrue(it2["is_name_conflict"])
        self.assertEqual(it2["on_conflict"], "")
        # 未确认 → apply 失败
        res = core.apply(self.ent, prop2)
        self.assertEqual(res["summary"]["failed"], 1)
        # 确认 keep_both → 成功
        it2["category"], it2["subtype"] = "资质", "体系认证"
        it2["on_conflict"] = "keep_both"
        res = core.apply(self.ent, prop2)
        self.assertEqual(res["summary"]["archived"], 1)
        self.assertEqual(len(core.load_ledger(self.ent)), 2)

    def test_different_keyword_no_conflict(self):
        self._archive("ISO9001_20260101.pdf")
        prop2 = self._upload_propose("营业执照_20260101.jpg")
        for it in prop2["items"]:
            self.assertFalse(it["is_name_conflict"])


class TestQueryInspectOverview(CoreBase):
    def test_query_and_overview(self):
        self._seed_one()
        rows = core.query(self.ent, category="资质", keyword="ISO9001")
        self.assertEqual(len(rows), 1)
        ov = core.enterprise_overview(self.ent)
        self.assertEqual(ov["ledger_total"], 1)
        self.assertEqual(ov["path"], str(self.libroot))

    def test_inspect_catches_untracked(self):
        (self.libroot / "资质").mkdir(exist_ok=True)
        (self.libroot / "资质" / "裸文件_20260101.jpg").write_text("x", encoding="utf-8")
        res = core.inspect(self.ent)
        types = [i["type"] for i in res["issues"]]
        self.assertIn("非常规上传", types)

    def _seed_one(self):
        inbox = core.Inbox(self.ent)
        inbox.open()
        inbox.add(self._make_file("ISO9001_20260101.pdf"))
        inbox.close()
        prop = core.propose(self.ent, require_closed=True)
        prop["items"][0]["category"] = "资质"
        prop["items"][0]["subtype"] = "体系认证"
        core.apply(self.ent, prop)


class TestOwnershipAndTrash(CoreBase):
    def test_ownership_match(self):
        r = core.ownership_check(self.ent, "ISO9001_20260101.pdf")
        self.assertIn(r["status"], ("match", "unknown"))

    def test_trash_and_cleanup(self):
        self._seed_one()
        src = self.libroot / "资质" / "ISO9001_20260101.pdf"
        self.assertTrue(src.exists())
        dest = core.move_to_trash(self.ent, "资质/ISO9001_20260101.pdf", reason="测试")
        self.assertFalse(src.exists())
        self.assertTrue(dest.exists())
        self.assertEqual(len(core.trash_manifest(self.ent)), 1)
        core.cleanup_trash(self.ent, days=0)
        self.assertEqual(len(core.trash_manifest(self.ent)), 0)

    def _seed_one(self):
        inbox = core.Inbox(self.ent)
        inbox.open()
        inbox.add(self._make_file("ISO9001_20260101.pdf"))
        inbox.close()
        prop = core.propose(self.ent, require_closed=True)
        prop["items"][0]["category"] = "资质"
        prop["items"][0]["subtype"] = "体系认证"
        core.apply(self.ent, prop)


if __name__ == "__main__":
    unittest.main()
