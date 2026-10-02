# -*- coding: utf-8 -*-
"""L2 集成测试：M4 存储层（项目级目录 / DOCX 提取 / 产物落盘 / 素材对照）。
全部使用临时根，绝不触碰真实素材库与真实项目。"""
import json
import os
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

_SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scripts")
sys.path.insert(0, os.path.abspath(_SCRIPTS))
from _shared import core           # noqa: E402
from m4_tender import rules, tender  # noqa: E402


class TenderBase(unittest.TestCase):
    ENT = "测试监理有限公司"
    PROJECT = "测试安置房项目监理"

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="bid_m4_")
        self.root = Path(self.tmp)
        self.lib = core.Library(self.root)
        self.ent, _ = self.lib.init_enterprise(self.ENT)
        self.ent_dir = Path(self.ent)
        self.tdir = tender.ensure_project_dir(self.ent, self.PROJECT)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _make_docx(self, paras):
        """用标准库构造最小 docx（含 word/document.xml）。"""
        p = Path(self.tmp) / "招标文件.docx"
        runs = []
        for para in paras:
            txt = "".join("<w:t>%s</w:t>" % t for t in para.split("\n"))
            runs.append("<w:p>%s</w:p>" % txt)
        body = "<w:document xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'><w:body>%s</w:body></w:document>" % "".join(runs)
        with zipfile.ZipFile(p, "w") as z:
            z.writestr("word/document.xml", body)
        return p

    def _make_txt(self, name, content):
        p = Path(self.tmp) / name
        p.write_text(content, encoding="utf-8")
        return p

    def _make_points(self, project="P"):
        md = "# 投标要点\n## 项目概况\n- 项目名称：XX"
        doc = {"project": project, "modules": [
            {"id": "m1", "title": "项目概况", "type": "fields",
             "fields": {"project_name": {"value": "XX", "evidence": "第1页"}}}]}
        return self._write_pair("points", md, doc)

    def _make_list(self, items=None, project="P"):
        md = "# 素材清单\n| 大类 | 子类 | 用途 |"
        doc = {"project": project, "items": items or [
            {"category": "资质", "subtype": "企业资质证书", "keywords": ["房屋建筑工程监理甲级"],
             "purpose": "资格要求", "required": True, "source": "3.1"}]}
        return self._write_pair("list", md, doc)

    def _write_pair(self, kind, md, doc):
        md_p = Path(self.tmp) / ("%s.md" % kind)
        json_p = Path(self.tmp) / ("%s.json" % kind)
        md_p.write_text(md, encoding="utf-8")
        json_p.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
        return md_p, json_p


class TestProjectDir(TenderBase):
    def test_ensure_creates_and_idempotent(self):
        p = tender.project_tender_dir(self.ent, self.PROJECT)
        self.assertTrue(p.is_dir())
        self.assertEqual(str(p).replace("\\", "/").endswith("项目级/%s/招标解析" % self.PROJECT), True)
        # 项目级目录结构：招标解析 + 项目资料（项目独享资料）
        data_dir = Path(self.ent) / "项目级" / self.PROJECT / "项目资料"
        self.assertTrue(data_dir.is_dir(), "tender-init 应同时创建项目资料目录")
        p2 = tender.ensure_project_dir(self.ent, self.PROJECT)
        self.assertEqual(p2, p)
        self.assertTrue(data_dir.is_dir(), "重复调用应幂等且不删除项目资料目录")

    def test_illegal_project_name(self):
        with self.assertRaises(core.LibraryError):
            tender.ensure_project_dir(self.ent, "a/b")


class TestExtract(TenderBase):
    def test_docx_extract(self):
        p = self._make_docx(["第一章 招标公告", "项目名称：XX项目", "投标截止时间：2026年10月30日"])
        text = tender.extract_docx(p)
        self.assertIn("第一章 招标公告", text)
        self.assertIn("投标截止时间：2026年10月30日", text)
        self.assertEqual(text.count("\n"), 2)

    def test_bad_docx(self):
        p = Path(self.tmp) / "bad.docx"
        p.write_text("not a zip", encoding="utf-8")
        with self.assertRaises(core.LibraryError):
            tender.extract_text_file(p)

    def test_txt_and_gbk(self):
        p = Path(self.tmp) / "a.txt"
        p.write_text("招标文件正文", encoding="utf-8")
        self.assertIn("招标文件正文", tender.extract_text_file(p))
        gp = Path(self.tmp) / "b.txt"
        gp.write_bytes("资质要求".encode("gb18030"))
        self.assertIn("资质要求", tender.read_text(gp))

    def test_unsupported_ext(self):
        p = Path(self.tmp) / "c.pdf"
        p.write_text("x", encoding="utf-8")
        with self.assertRaises(core.LibraryError):
            tender.extract_text_file(p)

    def test_write_original(self):
        rel = tender.write_original(self.tdir, "招标文件", "正文内容")
        self.assertEqual(rel, "原文_招标文件.txt")
        self.assertTrue((self.tdir / rel).exists())


class TestArchiveSource(TenderBase):
    def test_archive_docx(self):
        p = self._make_docx(["第一章 招标公告"])
        dst, created = tender.archive_source(self.tdir, self.PROJECT, p)
        self.assertTrue(created)
        self.assertEqual(dst.name, "源文件_%s.docx" % self.PROJECT)
        self.assertTrue(dst.exists())

    def test_archive_idempotent_same_content(self):
        p = self._make_docx(["第一章 招标公告"])
        _, created1 = tender.archive_source(self.tdir, self.PROJECT, p)
        _, created2 = tender.archive_source(self.tdir, self.PROJECT, p)
        self.assertTrue(created1)
        self.assertFalse(created2, "同内容重复归档应幂等跳过")

    def test_archive_conflict_different_content(self):
        p1 = self._make_docx(["第一章 招标公告"])
        tender.archive_source(self.tdir, self.PROJECT, p1)
        p2 = Path(self.tmp) / "other.docx"
        p2.write_bytes(b"different content")
        with self.assertRaises(core.LibraryError):
            tender.archive_source(self.tdir, self.PROJECT, p2)

    def test_archive_missing_source(self):
        with self.assertRaises(core.LibraryError):
            tender.archive_source(self.tdir, self.PROJECT, Path(self.tmp) / "nope.pdf")


class TestSaveProducts(TenderBase):
    def test_save_points_list_ok(self):
        md_p, json_p = self._make_points()
        md_d, json_d = tender.save_points(self.tdir, self.PROJECT, md_p, json_p)
        self.assertTrue(md_d.exists())
        self.assertTrue(json_d.exists())
        self.assertEqual(md_d.name, "投标要点_%s.md" % self.PROJECT)
        # 双份内容一致（JSON 可读）
        doc = core.read_json(json_d)
        self.assertEqual(len(doc["modules"]), 1)

        md_l, json_l = self._make_list()
        md_d, json_d = tender.save_list(self.tdir, self.PROJECT, md_l, json_l)
        self.assertTrue(md_d.exists())
        self.assertTrue(json_d.exists())
        self.assertEqual(md_d.name, "素材清单_%s.md" % self.PROJECT)

    def test_save_points_bad_json_rejected(self):
        md, _ = self._make_points()
        bad = Path(self.tmp) / "bad.json"
        bad.write_text(json.dumps({"project": "P"}), encoding="utf-8")
        with self.assertRaises(core.LibraryError):
            tender.save_points(self.tdir, self.PROJECT, md, bad)

    def test_save_list_bad_item_rejected(self):
        md, _ = self._make_list()
        bad = Path(self.tmp) / "bad.json"
        bad.write_text(json.dumps({"items": [{"category": ""}]}), encoding="utf-8")
        with self.assertRaises(core.LibraryError):
            tender.save_list(self.tdir, self.PROJECT, md, bad)

    def test_save_accepts_bom_files(self):
        """Windows 工具常写带 BOM 的 md/json——落盘时剥 BOM、可解析。"""
        md_p = Path(self.tmp) / "bom.md"
        md_p.write_bytes("# 投标要点".encode("utf-8-sig"))
        json_p = Path(self.tmp) / "bom.json"
        json_p.write_bytes(json.dumps({"project": "P", "modules": [
            {"id": "m1", "title": "项目概况", "type": "fields", "fields": {}}]},
            ensure_ascii=False).encode("utf-8-sig"))
        md_d, _ = tender.save_points(self.tdir, self.PROJECT, md_p, json_p)
        self.assertEqual(md_d.read_text(encoding="utf-8")[0], "#", "落盘 md 不应带 BOM")


class TestCheck(TenderBase):
    def _seed_ledger(self):
        rows = [
            core.new_ledger_row(category="资质", subtype="企业资质证书",
                                keywords="房屋建筑工程监理甲级",
                                rel_path="资质/房屋建筑工程监理甲级.jpg"),
            core.new_ledger_row(category="人员", subtype="注册证书",
                                keywords="陈XX 注册监理工程师",
                                rel_path="人员/陈XX/注册证书/注册监理工程师_20281231.png"),
        ]
        core.save_ledger(self.ent, rows)

    def test_run_check_status(self):
        self._seed_ledger()
        items = [
            {"category": "资质", "subtype": "企业资质证书", "keywords": ["房屋建筑工程监理甲级"],
             "purpose": "资格要求", "required": True, "source": "3.1"},
            {"category": "人员", "subtype": "注册证书", "keywords": ["陈XX"],
             "purpose": "总监资格", "required": True, "source": "3.2"},
            {"category": "业绩", "subtype": "监理合同", "keywords": ["类似业绩"],
             "purpose": "评分项", "required": False, "source": "评标办法"},
        ]
        md_l, json_l = self._write_pair("list", "# 素材清单", {"project": self.PROJECT, "items": items})
        tender.save_list(self.tdir, self.PROJECT, md_l, json_l)
        rows, summary, csv_name = tender.run_check(self.ent, self.tdir, self.PROJECT)
        self.assertEqual(summary["total"], 3)
        self.assertEqual(summary["have"], 2)
        self.assertEqual(summary["missing_required"], 0)
        self.assertEqual(summary["missing_bonus"], 1)
        by_sub = {r["subtype"]: r for r in rows}
        self.assertEqual(by_sub["企业资质证书"]["status"], "已有")
        self.assertGreater(by_sub["企业资质证书"]["hits"], 0)
        self.assertEqual(by_sub["监理合同"]["status"], "缺失·加分")
        csv_p = self.tdir / csv_name
        self.assertTrue(csv_p.exists())
        content = csv_p.read_text(encoding="utf-8-sig")
        self.assertIn("房屋建筑工程监理甲级", content)
        self.assertIn("缺失·加分", content)

    def test_run_check_missing_required(self):
        items = [{"category": "资质", "subtype": "市政公用工程监理", "keywords": ["乙级"],
                  "purpose": "资格要求", "required": True, "source": "3.1"}]
        md_l, json_l = self._write_pair("list", "# 素材清单", {"project": self.PROJECT, "items": items})
        tender.save_list(self.tdir, self.PROJECT, md_l, json_l)
        rows, summary, _ = tender.run_check(self.ent, self.tdir, self.PROJECT)
        self.assertEqual(rows[0]["status"], "缺失·必须")
        self.assertEqual(summary["missing_required"], 1)
        self.assertEqual(summary["redlines"], ["资质/市政公用工程监理"])


if __name__ == "__main__":
    unittest.main()
