# -*- coding: utf-8 -*-
"""L1 单元测试：产物反馈机制存储层 + 项目模板生成器纯函数（免 python-docx）。"""
import json
import os
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scripts"))
from _shared import core                            # noqa: E402
from m_feedback import feedback as fb               # noqa: E402
from m5_project import generator as gen             # noqa: E402


def make_min_docx(path, text):
    import xml.sax.saxutils as sx
    paras = "".join("<w:p><w:r><w:t>%s</w:t></w:r></w:p>" % sx.escape(p)
                    for p in text.split("\n"))
    doc = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:body>%s</w:body></w:document>' % paras
    )
    ct = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
          '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
          '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
          '<Default Extension="xml" ContentType="application/xml"/>'
          '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
          '</Types>')
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml", ct)
        z.writestr("word/document.xml", doc)


class BaseFeedback(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="bid_fb_unit_")
        self.ent = Path(self.tmp) / "测试监理有限公司"
        (self.ent / "企业级").mkdir(parents=True)
        self.prod = self.ent / "项目级" / "测试项目" / "项目模板"
        self.prod.mkdir(parents=True)
        self.rel = "项目级/测试项目/项目模板/开标一览表.docx"
        make_min_docx(self.prod / "开标一览表.docx",
                      "开标一览表\n项目名称\n投标人名称\n【项目名称】\n【投标人名称】")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class TestRegister(BaseFeedback):
    def test_register_new(self):
        row = fb.register(self.ent, self.rel, level="项目级", project="测试项目",
                          ptype="项目模板", generator="m5-project-gen")
        self.assertEqual(row["相对路径"], self.rel)
        self.assertEqual(row["版本"], "v1")
        self.assertEqual(row["层级"], "项目级")
        self.assertEqual(len(row["sha256"]), 64)
        self.assertIn("文本指纹", row)
        rows = fb.load_baseline(self.ent)
        self.assertEqual(len(rows), 1)

    def test_register_refresh_bumps_version(self):
        fb.register(self.ent, self.rel, ptype="项目模板")
        make_min_docx(self.prod / "开标一览表.docx", "改了的内容")
        row = fb.register(self.ent, self.rel, ptype="项目模板")
        self.assertEqual(row["版本"], "v2")

    def test_register_explicit_version(self):
        fb.register(self.ent, self.rel, version="v7")
        row = fb.register(self.ent, self.rel, version="v9")
        self.assertEqual(row["版本"], "v9")

    def test_register_missing_file_raises(self):
        with self.assertRaises(fb.FeedbackError):
            fb.register(self.ent, "项目级/不存在.docx")

    def test_register_system_file_refused(self):
        (self.ent / fb.BASELINE_JSON).write_text("[]", encoding="utf-8")
        with self.assertRaises(fb.FeedbackError):
            fb.register(self.ent, fb.BASELINE_JSON)

    def test_unregister(self):
        fb.register(self.ent, self.rel)
        self.assertTrue(fb.unregister(self.ent, self.rel))
        self.assertFalse(fb.unregister(self.ent, self.rel))


class TestAudit(BaseFeedback):
    def setUp(self):
        super().setUp()
        fb.register(self.ent, self.rel, ptype="项目模板")

    def test_unchanged(self):
        res = fb.audit(self.ent)
        self.assertEqual(res["checked"], 1)
        self.assertEqual(len(res["unchanged"]), 1)
        self.assertEqual(res["modified"], [])
        self.assertEqual(res["missing"], [])

    def test_modified_and_diff(self):
        make_min_docx(self.prod / "开标一览表.docx", "第一行\n第二行\n【项目名称】\n新占位")
        res = fb.audit(self.ent, full=True)
        self.assertEqual(len(res["modified"]), 1)
        self.assertIn(self.rel, res["diffs"])
        diff = "\n".join(res["diffs"][self.rel])
        self.assertIn("第一行", diff)          # 新内容出现在差异中

    def test_missing(self):
        (self.prod / "开标一览表.docx").unlink()
        res = fb.audit(self.ent)
        self.assertEqual(len(res["missing"]), 1)

    def test_audit_single_path(self):
        make_min_docx(self.prod / "开标一览表.docx", "改了")
        res = fb.audit(self.ent, path=self.rel)
        self.assertEqual(res["checked"], 1)
        self.assertEqual(len(res["modified"]), 1)
        res2 = fb.audit(self.ent, path="项目级/不存在.docx")
        self.assertEqual(res2["checked"], 0)


class TestReport(BaseFeedback):
    def setUp(self):
        super().setUp()
        fb.register(self.ent, self.rel, ptype="项目模板")
        make_min_docx(self.prod / "开标一览表.docx", "开标一览表\n【项目名称】\n【新占位符】")

    def test_report_created(self):
        path = fb.report(self.ent)
        self.assertTrue(Path(path).is_file())
        txt = Path(path).read_text(encoding="utf-8")
        self.assertIn("系统功能更新评估报告", txt)
        self.assertIn("变更概览", txt)
        self.assertIn("完善点建议", txt)
        self.assertIn("确认栏", txt)
        self.assertIn("开标一览表.docx", txt)


class TestStatus(BaseFeedback):
    def test_status(self):
        fb.register(self.ent, self.rel, ptype="项目模板")
        st = fb.status(self.ent)
        self.assertEqual(st["baseline_total"], 1)
        self.assertEqual(st["by_type"].get("项目模板"), 1)
        self.assertEqual(st["enterprise"], "测试监理有限公司")


class TestGeneratorPure(unittest.TestCase):
    def test_clean_tag(self):
        self.assertEqual(gen._clean_tag("项目名称、所在地及类别"), "项目名称、所在地及类别")
        self.assertEqual(gen._clean_tag("（国内）  监理经历"), "国内监理经历")
        self.assertEqual(gen._clean_tag("序号"), "序号")

    def test_global_ph_pairs_safe(self):
        """GLOBAL_PH 的旧文本确为填空提示（不含固定条款关键词）。"""
        for old, new in gen.GLOBAL_PH:
            self.assertTrue(old.startswith("（"), old)
            self.assertTrue(new.startswith("【") and new.endswith("】"), new)

    def test_file_map_cover_all_contract_ids(self):
        ids = {m["id"] for m in gen.FILE_MAP}
        self.assertEqual(len(ids), 27)          # F01–F15（含 F06a–k 共 11 项）
        self.assertIn("F06i", ids)
        self.assertIn("F15", ids)

    def test_scan_placeholders(self):
        p = Path(tempfile.mkdtemp(prefix="bid_fb_ph_")) / "t.docx"
        make_min_docx(p, "【项目名称】\n【项目名称】\n【图片：营业执照】\n固定文字")
        ph = gen._scan_placeholders(p)
        self.assertEqual(ph, ["【图片：营业执照】", "【项目名称】"])

    def test_fingerprint_txt(self):
        p = Path(tempfile.mkdtemp(prefix="bid_fb_fp_")) / "a.md"
        p.write_text("内容A\n内容B", encoding="utf-8")
        self.assertEqual(fb._text_fingerprint(p), "内容A\n内容B")


if __name__ == "__main__":
    unittest.main()
