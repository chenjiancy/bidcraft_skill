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
        self.libroot = core.lib_root(self.ent)  # 企业级/素材库

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
        self.assertEqual(core.lib_root(self.ent), self.ent_dir / "企业级" / "素材库")

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

    def test_single_page_removes_p0(self):
        # 荣誉单页：即使 page=0，批次内唯一 → apply 自动去 _P0
        prop = self._upload_propose("优秀监理企业_20260101.png")
        it = prop["items"][0]
        it["category"], it["subtype"] = "荣誉", "荣誉证书"
        it["keywords"], it["dates"] = ["优秀监理企业"], ["20260101"]
        it["page"] = 0
        res = core.apply(self.ent, prop)
        self.assertEqual(res["summary"]["archived"], 1)
        self.assertTrue((self.libroot / "荣誉" / "优秀监理企业_20260101.png").exists())
        self.assertFalse((self.libroot / "荣誉" / "优秀监理企业_20260101_P0.png").exists())
        row = core.load_ledger(self.ent)[0]
        self.assertEqual(row["page_index"], "")

    def test_multi_page_keeps_pages(self):
        # 同一 base 两页 → 保留 _P0/_P1
        prop = self._upload_and_propose(["身份证_20260101_P0.png", "身份证_20260101_P1.png"])
        for it, p in zip(prop["items"], [0, 1]):
            it["category"], it["subtype"] = "人员", "身份证"
            it["dates"], it["date_type"], it["person"] = ["20260101"], "到期日", "张三"
            it["page"] = p
        res = core.apply(self.ent, prop)
        self.assertEqual(res["summary"]["archived"], 2)
        self.assertTrue((self.libroot / "人员" / "张三" / "身份证" / "身份证_20260101_P0.png").exists())
        self.assertTrue((self.libroot / "人员" / "张三" / "身份证" / "身份证_20260101_P1.png").exists())

    def _archive_person_resume(self, fname, person, upload_date):
        """上传并归档一份人员简历（固定词子类：关键字为空，person 必填）。"""
        inbox = core.Inbox(self.ent)
        inbox.open()
        inbox.add(self._make_file(fname))
        inbox.close()
        prop = core.propose(self.ent, require_closed=True)
        it = prop["items"][0]
        it["category"], it["subtype"] = "人员", "简历"
        it["person"] = person
        it["keywords"] = []
        it["dates"], it["date_type"] = [upload_date], "上传日期"
        core.apply(self.ent, prop)

    def _upload_resume_propose(self, fname):
        """仅上传不归档，返回 propose（person 由调用方补齐）。"""
        inbox = core.Inbox(self.ent)
        inbox.open()
        inbox.add(self._make_file(fname))
        inbox.close()
        return core.propose(self.ent, require_closed=True)

    def test_fixed_word_conflict_same_person(self):
        """固定词子类（简历，关键字为空）：同人 → 判定同名（删除/更新语义）。"""
        self._archive_person_resume("简历_20261001.png", "陈阳", "20261001")
        prop2 = self._upload_resume_propose("简历_20261002.png")
        it2 = prop2["items"][0]
        it2["category"], it2["subtype"] = "人员", "简历"
        it2["person"] = "陈阳"
        it2["keywords"] = []
        it2["dates"], it2["date_type"] = ["20261002"], "上传日期"
        # propose 时 person 为空 → 不判；apply 前以最终字段重算 → 判同名
        res = core.apply(self.ent, prop2)
        self.assertEqual(res["summary"]["failed"], 1, "同名未确认处理方式应被 apply 拒绝")
        self.assertIn("同名", res["failed"][0]["error"])
        # 旧文件仍在（未被误删）
        self.assertTrue((self.libroot / "人员" / "陈阳" / "简历" / "简历_20261001.png").exists())

    def test_trash_old_removes_old_file_and_row(self):
        """同名确认 trash_old：旧文件入回收站、旧台账行清理、新文件归档（删除更新）。"""
        self._archive_person_resume("简历_20261001.png", "陈阳", "20261001")
        prop2 = self._upload_resume_propose("简历_20261002.png")
        it2 = prop2["items"][0]
        it2["category"], it2["subtype"] = "人员", "简历"
        it2["person"] = "陈阳"
        it2["keywords"] = []
        it2["dates"], it2["date_type"] = ["20261002"], "上传日期"
        it2["on_conflict"] = "trash_old"
        res = core.apply(self.ent, prop2)
        self.assertEqual(res["summary"]["archived"], 1, res["failed"])
        # 旧文件入回收站、原位置消失
        self.assertFalse((self.libroot / "人员" / "陈阳" / "简历" / "简历_20261001.png").exists())
        self.assertTrue((self.libroot / "回收站" / "简历_20261001.png").exists())
        # 台账：旧行清理，仅 1 条新行（无同 rel_path 重复）
        rows = core.load_ledger(self.ent)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["rel_path"], "人员/陈阳/简历/简历_20261002.png")

    def test_empty_keyword_different_person_no_conflict(self):
        """固定词子类：不同人 → 不判定同名。"""
        self._archive_person_resume("简历_20261001.png", "陈阳", "20261001")
        prop2 = self._upload_resume_propose("简历_20261002.png")
        it2 = prop2["items"][0]
        it2["category"], it2["subtype"] = "人员", "简历"
        it2["person"] = "张三"
        it2["keywords"] = []
        it2["dates"], it2["date_type"] = ["20261002"], "上传日期"
        core.apply(self.ent, prop2)
        rows = core.load_ledger(self.ent)
        self.assertEqual(len(rows), 2, "不同人不应判同名，两份并存")
        self.assertEqual({r["rel_path"] for r in rows},
                         {"人员/陈阳/简历/简历_20261001.png", "人员/张三/简历/简历_20261002.png"})

    def test_final_name_without_ext_auto_appends(self):
        """final_name 不带扩展名 → 自动补源文件扩展名（防归档后丢后缀）。"""
        inbox = core.Inbox(self.ent)
        inbox.open()
        inbox.add(self._make_file("PixPin_2026-10-02_09-10-26.png"))
        inbox.close()
        prop = core.propose(self.ent, require_closed=True)
        it = prop["items"][0]
        it["category"], it["subtype"] = "人员", "简历"
        it["person"] = "陈阳"
        it["keywords"] = []
        it["dates"], it["date_type"] = ["20261002"], "上传日期"
        it["final_name"] = "简历_20261002"   # 无后缀
        res = core.apply(self.ent, prop)
        self.assertEqual(res["summary"]["archived"], 1, res["failed"])
        self.assertTrue((self.libroot / "人员" / "陈阳" / "简历" / "简历_20261002.png").exists(),
                        "final_name 无后缀时应自动补 .png")
        self.assertFalse((self.libroot / "人员" / "陈阳" / "简历" / "简历_20261002").exists())
        row = core.load_ledger(self.ent)[0]
        self.assertEqual(row["rel_path"], "人员/陈阳/简历/简历_20261002.png")
        self.assertEqual(row["ext"], ".png")

    def test_final_name_with_ext_keeps_as_is(self):
        """final_name 已带扩展名 → 原样使用，不重复追加。"""
        inbox = core.Inbox(self.ent)
        inbox.open()
        inbox.add(self._make_file("PixPin_2026-10-02_09-10-26.png"))
        inbox.close()
        prop = core.propose(self.ent, require_closed=True)
        it = prop["items"][0]
        it["category"], it["subtype"] = "人员", "简历"
        it["person"] = "陈阳"
        it["keywords"] = []
        it["dates"], it["date_type"] = ["20261002"], "上传日期"
        it["final_name"] = "简历_20261002.png"
        res = core.apply(self.ent, prop)
        self.assertEqual(res["summary"]["archived"], 1, res["failed"])
        self.assertTrue((self.libroot / "人员" / "陈阳" / "简历" / "简历_20261002.png").exists())
        row = core.load_ledger(self.ent)[0]
        self.assertEqual(row["ext"], ".png")

    # ---- 同名判定语义：人员类同人 + 排除等级/类型固定词 ----

    def _archive_credential(self, person, sub, keywords, dates, fname):
        inbox = core.Inbox(self.ent)
        inbox.open()
        inbox.add(self._make_file("PixPin_2026-10-02_09-10-26.png"))
        inbox.close()
        prop = core.propose(self.ent, require_closed=True)
        it = prop["items"][0]
        it["category"], it["subtype"] = "人员", sub
        it["person"] = person
        it["keywords"] = keywords
        it["dates"] = dates
        it["date_type"] = "到期日"
        it["final_name"] = fname
        res = core.apply(self.ent, prop)
        self.assertEqual(res["summary"]["archived"], 1, res["failed"])

    def test_title_same_person_different_specialty_no_conflict(self):
        """职称证书：同人不同专业（工程师_市政工程 vs 工程师_建筑工程）→ 不判同名，并存。"""
        self._archive_credential("陈友龙", "职称证书", ["工程师", "建筑工程"], [], "工程师_建筑工程.png")
        inbox = core.Inbox(self.ent)
        inbox.open()
        inbox.add(self._make_file("PixPin_2026-10-02_09-20-30.png"))
        inbox.close()
        prop = core.propose(self.ent, require_closed=True)
        it = prop["items"][0]
        it["category"], it["subtype"] = "人员", "职称证书"
        it["person"] = "陈友龙"
        it["keywords"] = ["工程师", "市政工程"]
        it["dates"] = []
        res = core.apply(self.ent, prop)
        self.assertEqual(res["summary"]["archived"], 1, res["failed"])
        self.assertTrue((self.libroot / "人员" / "陈友龙" / "职称证书" / "工程师_市政工程.png").exists())

    def test_title_same_person_same_specialty_conflicts(self):
        """职称证书：同人同专业再传 → 判同名（更新语义）。"""
        self._archive_credential("陈友龙", "职称证书", ["工程师", "市政工程"], [], "工程师_市政工程.png")
        inbox = core.Inbox(self.ent)
        inbox.open()
        inbox.add(self._make_file("PixPin_2026-10-02_09-20-30.png"))
        inbox.close()
        prop = core.propose(self.ent, require_closed=True)
        it = prop["items"][0]
        it["category"], it["subtype"] = "人员", "职称证书"
        it["person"] = "陈友龙"
        it["keywords"] = ["工程师", "市政工程"]
        it["dates"] = []
        res = core.apply(self.ent, prop)
        self.assertEqual(res["failed"], [{"seq": 1,
                                          "file": "PixPin_2026-10-02_09-20-30.png",
                                          "error": "关键字同名素材：请先确认处理方式（keep_both / skip / trash_old）后再 apply"}],
                         "同人同专业应判同名并拒绝未确认的 apply")

    def test_registration_diff_person_no_conflict(self):
        """注册证书：类型词固定，不同人 → 不判同名。"""
        self._archive_credential("李林", "注册证书", ["监理工程师"], ["20290322", "20291102"],
                                 "监理工程师_20290322_20291102.png")
        inbox = core.Inbox(self.ent)
        inbox.open()
        inbox.add(self._make_file("PixPin_2026-10-02_09-20-30.png"))
        inbox.close()
        prop = core.propose(self.ent, require_closed=True)
        it = prop["items"][0]
        it["category"], it["subtype"] = "人员", "注册证书"
        it["person"] = "张三"
        it["keywords"] = ["监理工程师"]
        it["dates"] = ["20280123", "20270220"]
        res = core.apply(self.ent, prop)
        self.assertEqual(res["summary"]["archived"], 1, res["failed"])
        self.assertTrue((self.libroot / "人员" / "张三" / "注册证书" / "监理工程师_20280123_20270220.png").exists())

    def test_registration_same_person_new_cert_conflicts(self):
        """注册证书：同人再传新证书（新使用有效期）→ 判同名（更新语义）。"""
        self._archive_credential("张三", "注册证书", ["监理工程师"], ["20280123", "20270220"],
                                 "监理工程师_20280123_20270220.png")
        inbox = core.Inbox(self.ent)
        inbox.open()
        inbox.add(self._make_file("PixPin_2026-10-02_09-20-30.png"))
        inbox.close()
        prop = core.propose(self.ent, require_closed=True)
        it = prop["items"][0]
        it["category"], it["subtype"] = "人员", "注册证书"
        it["person"] = "张三"
        it["keywords"] = ["监理工程师"]
        it["dates"] = ["20280123", "20280220"]
        res = core.apply(self.ent, prop)
        self.assertEqual(len(res["failed"]), 1, "同人新注册证书应判同名并拒绝未确认的 apply")

    def test_title_same_person_diff_grade_no_conflict(self):
        """职称证书：同人同专业不同等级（工程师 vs 高级工程师）→ 不判同名，并存。"""
        self._archive_credential("方业华", "职称证书", ["工程师", "建筑电气"], [], "工程师_建筑电气.png")
        inbox = core.Inbox(self.ent)
        inbox.open()
        inbox.add(self._make_file("PixPin_2026-10-02_09-35-47.png"))
        inbox.close()
        prop = core.propose(self.ent, require_closed=True)
        it = prop["items"][0]
        it["category"], it["subtype"] = "人员", "职称证书"
        it["person"] = "方业华"
        it["keywords"] = ["高级工程师", "建筑电气"]
        it["dates"] = []
        res = core.apply(self.ent, prop)
        self.assertEqual(res["summary"]["archived"], 1, res["failed"])
        self.assertTrue((self.libroot / "人员" / "方业华" / "职称证书" / "高级工程师_建筑电气.png").exists())

    def test_title_same_person_final_name_with_year_no_conflict(self):
        """职称证书：同人同等级同专业但评审年份不同（final_name 带年份区分）→ 不判同名，并存。"""
        self._archive_credential("裘义文", "职称证书", ["工程师", "市政道桥"], [],
                                 "工程师_市政道桥.png")
        inbox = core.Inbox(self.ent)
        inbox.open()
        inbox.add(self._make_file("PixPin_2026-10-03_12-58-41.png"))
        inbox.close()
        prop = core.propose(self.ent, require_closed=True)
        it = prop["items"][0]
        it["category"], it["subtype"] = "人员", "职称证书"
        it["person"] = "裘义文"
        it["keywords"] = ["工程师", "市政道桥"]
        it["dates"] = []
        it["final_name"] = "工程师_市政道桥_2009"
        res = core.apply(self.ent, prop)
        self.assertEqual(res["summary"]["archived"], 1, res["failed"])
        self.assertTrue((self.libroot / "人员" / "裘义文" / "职称证书" / "工程师_市政道桥_2009.png").exists())

    def test_retirement_base_name_distinguishes_form(self):
        """退休证：退休证_长期 与 final_name 指定的 退休证_登记表 → 基名不同，不判同名并存。"""
        self._archive_credential("陈美生", "退休证", [], ["长期"], "退休证_长期.png")
        inbox = core.Inbox(self.ent)
        inbox.open()
        inbox.add(self._make_file("PixPin_2026-10-03_13-31-05.png"))
        inbox.close()
        prop = core.propose(self.ent, require_closed=True)
        it = prop["items"][0]
        it["category"], it["subtype"] = "人员", "退休证"
        it["person"] = "陈美生"
        it["keywords"] = []
        it["dates"] = []
        it["final_name"] = "退休证_登记表"
        res = core.apply(self.ent, prop)
        self.assertEqual(res["summary"]["archived"], 1, res["failed"])
        self.assertTrue((self.libroot / "人员" / "陈美生" / "退休证" / "退休证_登记表.png").exists())

    def test_retirement_same_person_same_cert_conflicts(self):
        """退休证：同人再传同基名退休证 → 判同名（更新语义）。"""
        self._archive_credential("陈美生", "退休证", [], ["长期"], "退休证_长期.png")
        inbox = core.Inbox(self.ent)
        inbox.open()
        inbox.add(self._make_file("PixPin_2026-10-03_13-31-05.png"))
        inbox.close()
        prop = core.propose(self.ent, require_closed=True)
        it = prop["items"][0]
        it["category"], it["subtype"] = "人员", "退休证"
        it["person"] = "陈美生"
        it["keywords"] = []
        it["dates"] = ["长期"]
        res = core.apply(self.ent, prop)
        self.assertEqual(len(res["failed"]), 1, "同人同基名退休证应判同名并拒绝未确认的 apply")


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
