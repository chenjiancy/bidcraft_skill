# -*- coding: utf-8 -*-
"""M7 T15 技术标检查单测：TECH_CHECKS 三项（结构/暗标敏感词/页数对照）+ kind 判定 + 全链路落盘。

技术标 docx 用 python-docx 合成（TOC 域 fldChar + outlineLvl + 封面/目录/正文/结尾）。
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scripts"))

from _shared import core                       # noqa: E402
from m7_check import rule_check as R           # noqa: E402

PROJECT = "T15测试项目"


def _mk_tech_docx(path, n_paras=20, has_toc=True, has_outline=True,
                  tail="结尾段：本技术标制作完成，投标人承诺按本大纲执行。", leak=""):
    """合成技术标 docx：封面 + 目录域(TOC+fldChar) + 正文（含 outlineLvl 标题）+ 结尾。"""
    from docx import Document
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    doc = Document()
    doc.add_paragraph("封面：测试项目技术标")
    if has_toc:
        p = doc.add_paragraph()
        f1 = OxmlElement("w:fldChar"); f1.set(qn("w:fldCharType"), "begin")
        it = OxmlElement("w:instrText"); it.set(qn("xml:space"), "preserve")
        it.text = 'TOC \\o "1-2" \\h \\u'
        f2 = OxmlElement("w:fldChar"); f2.set(qn("w:fldCharType"), "separate")
        run = p.add_run()
        run._r.append(f1); run._r.append(it); run._r.append(f2)
        p.add_run("目录内容")
    for i in range(n_paras):
        if has_outline and i == 2:
            para = doc.add_paragraph("第1章 监理工作内容")
            pPr = para._p.get_or_add_pPr()
            ol = OxmlElement("w:outlineLvl"); ol.set(qn("w:val"), "0"); pPr.append(ol)
        else:
            doc.add_paragraph("监理正文段落%d：对工程实施全过程监理，覆盖质量控制、进度控制、造价控制。" % i)
    doc.add_paragraph(tail)
    if leak:
        doc.add_paragraph(leak)
    doc.save(str(path))


def _points(pages=10):
    return {"project": PROJECT, "modules": [
        {"id": "scoring", "title": "评分办法", "type": "mixed",
         "method": {"value": "综合评分法", "evidence": "e"},
         "score_items": [{"item": "监理大纲（50分）", "weight": 50, "unit": "分", "evidence": "E1"}]},
        {"id": "reject", "title": "废标红线", "type": "items",
         "items": [{"type": "格式", "rule": "技术标总页数不超过 %d 页；按明标编制" % pages, "evidence": "e"}]},
    ]}


def _material(anbiao_ok=True, perf_path="业绩/某小区.pdf"):
    return {"project": PROJECT,
            "personnel": [{"name": "张三", "role": "总监理工程师"}] if anbiao_ok else [],
            "企业基础信息": {"法定代表人姓名": "李四", "企业名称": "企业A"} if anbiao_ok else {},
            "performance": [{"name": "某小区改造监理", "path": perf_path}],
            "qualification_required": [], "iso_certificates": [], "honors": [], "items": []}


def _settings(bid_mode="明标", pages=10):
    return {"schema": "m6.settings/v1", "bidMode": bid_mode,
            "pageConstraint": {"max": pages},
            "personnel": [{"name": "张三", "post": "总监理工程师"}]}


class TechChecksTable(unittest.TestCase):
    def test_tech_checks_schema(self):
        # T17：检查项 3→6（图表位置/空白页/引用一致性）
        self.assertEqual([c["id"] for c in R.TECH_CHECKS],
                         ["tech_structure", "anbiao_leak", "tech_pages",
                          "tech_figure_placement", "tech_blank_pages", "tech_ref_consistency"])
        for item in R.TECH_CHECKS:
            self.assertTrue(callable(getattr(R, item["fn"], None)),
                            "检查实现缺失: %s" % item["fn"])
            self.assertIn("level", item)
            self.assertIn("category", item)


class TechStructureTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.proj = self.root / PROJECT

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, docx):
        return R.check_tech_structure(str(docx), str(self.proj), {}, {})

    def test_complete_docx_ok(self):
        f = self.proj / "t.docx"
        self.proj.mkdir(parents=True)
        _mk_tech_docx(f)
        ok, issues = self._run(f)
        self.assertTrue(ok, issues)

    def test_missing_toc_flagged(self):
        f = self.proj / "t.docx"
        self.proj.mkdir(parents=True)
        _mk_tech_docx(f, has_toc=False)
        ok, issues = self._run(f)
        self.assertFalse(ok)
        self.assertTrue(any("TOC" in x for x in issues))

    def test_missing_outline_flagged(self):
        f = self.proj / "t.docx"
        self.proj.mkdir(parents=True)
        _mk_tech_docx(f, has_outline=False)
        ok, issues = self._run(f)
        self.assertFalse(ok)
        self.assertTrue(any("outlineLvl" in x for x in issues))

    def test_missing_target_flagged(self):
        ok, issues = self._run(self.proj / "缺.docx")
        self.assertFalse(ok)
        self.assertTrue(any("未找到" in x for x in issues))


class AnbiaoLeakTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.proj = self.root / PROJECT
        self.proj.mkdir(parents=True)
        (self.proj / "技术标").mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def _settings(self, bid_mode):
        (self.proj / "技术标" / "设置.json").write_text(
            json.dumps(_settings(bid_mode), ensure_ascii=False), encoding="utf-8")

    def test_anbiao_leak_flagged(self):
        self._settings("暗标")
        f = self.proj / "t.docx"
        _mk_tech_docx(f, leak="本项目监理单位企业A，总监张三同志。")
        ok, issues = R.check_anbiao_leak(str(f), str(self.proj), _material(), {})
        self.assertFalse(ok)
        joined = "\n".join(issues)
        self.assertIn("企业A", joined)
        self.assertIn("张三", joined)

    def test_anbiao_clean_passes(self):
        self._settings("暗标")
        f = self.proj / "t.docx"
        _mk_tech_docx(f)
        ok, issues = R.check_anbiao_leak(str(f), str(self.proj), _material(), {})
        self.assertTrue(ok, issues)

    def test_mingbiao_skips(self):
        self._settings("明标")
        f = self.proj / "t.docx"
        _mk_tech_docx(f, leak="企业A 张三")
        ok, issues = R.check_anbiao_leak(str(f), str(self.proj), _material(), {})
        self.assertTrue(ok)
        self.assertTrue(any("跳过" in x for x in issues))

    def test_no_settings_skips(self):
        f = self.proj / "t.docx"
        _mk_tech_docx(f)
        ok, issues = R.check_anbiao_leak(str(f), str(self.proj), _material(), {})
        self.assertTrue(ok)
        self.assertTrue(any("跳过" in x for x in issues))


class TechPagesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.proj = self.root / PROJECT
        self.proj.mkdir(parents=True)
        (self.proj / "技术标").mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def _settings(self, pages):
        (self.proj / "技术标" / "设置.json").write_text(
            json.dumps(_settings("明标", pages), ensure_ascii=False), encoding="utf-8")

    def test_short_doc_ok(self):
        self._settings(10)
        f = self.proj / "t.docx"
        _mk_tech_docx(f, n_paras=8)
        ok, issues = R.check_tech_pages(str(f), str(self.proj), {}, _points(10))
        self.assertTrue(ok, issues)

    def test_long_doc_flagged(self):
        self._settings(1)
        f = self.proj / "t.docx"
        _mk_tech_docx(f, n_paras=60)
        ok, issues = R.check_tech_pages(str(f), str(self.proj), {}, _points(1))
        self.assertFalse(ok)
        self.assertTrue(any("估算" in x or "实际" in x for x in issues))

    def test_no_limit_skips(self):
        f = self.proj / "t.docx"
        _mk_tech_docx(f)
        ok, issues = R.check_tech_pages(str(f), str(self.proj), {}, {"project": PROJECT, "modules": []})
        self.assertTrue(ok)
        self.assertTrue(any("跳过" in x for x in issues))


class ExtractPageLimitTest(unittest.TestCase):
    def test_parses_reject_rule(self):
        self.assertEqual(R._extract_page_limit(_points(60)), 60)
        self.assertIsNone(R._extract_page_limit({"modules": [{"id": "reject", "items": [
            {"rule": "无页数条款"}]}]}))


class RunRuleChecksTechTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.ent, _ = core.Library(self.root).init_enterprise("T15企业")
        self.proj = self.ent / "项目级" / PROJECT
        self.tdir = self.proj / "招标解析"
        self.tdir.mkdir(parents=True)
        (self.tdir / ("投标要点_%s.json" % PROJECT)).write_text(
            json.dumps(_points(10), ensure_ascii=False), encoding="utf-8")
        (self.tdir / ("素材清单_%s.json" % PROJECT)).write_text(
            json.dumps(_material(), ensure_ascii=False), encoding="utf-8")
        tech = self.proj / "技术标"
        tech.mkdir(parents=True)
        (tech / "设置.json").write_text(json.dumps(_settings("明标", 10), ensure_ascii=False),
                                        encoding="utf-8")
        out = tech / "产出"
        out.mkdir(parents=True)
        self.docx = out / ("技术标_%s.docx" % PROJECT)
        _mk_tech_docx(self.docx)
        # T17：明标正文含清单业绩名/人员名（引用一致性正路径；暗标用例走 anbiao 专属 fixture）
        from docx import Document as _Doc
        _d = _Doc(str(self.docx))
        _d.add_paragraph("本工程由总监理工程师张三负责，企业近三年完成某小区改造监理项目。")
        _d.save(str(self.docx))
        # 素材落盘（material 检查：业绩 path 必须存在，用绝对路径规避 CWD 依赖）
        (self.proj / "业绩").mkdir(exist_ok=True)
        self._perf_path = str(self.proj / "业绩" / "某小区.pdf")
        Path(self._perf_path).write_bytes(b"%PDF-1.4 fake")
        (self.tdir / ("素材清单_%s.json" % PROJECT)).write_text(
            json.dumps(_material(perf_path=self._perf_path), ensure_ascii=False), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_kind_auto_detects_tech_by_path(self):
        res = R.run_rule_checks("", str(self.proj), out_dir=str(self.docx), kind="auto")
        self.assertEqual(res["tag"], "技术标")
        ids = [c["id"] for c in res["检查"]]
        self.assertIn("tech_structure", ids)
        self.assertIn("anbiao_leak", ids)
        self.assertIn("tech_pages", ids)
        self.assertIn("material", ids)                 # 素材存在性保留
        self.assertNotIn("quote", ids)                 # 商务标专属跳过

    def test_kind_tech_explicit(self):
        res = R.run_rule_checks("", str(self.proj), out_dir=str(self.docx), kind="tech", tag="")
        self.assertEqual(res["tag"], "技术标")
        self.assertTrue(res["ok"], [c["issues"] for c in res["检查"] if not c["ok"]])
        # 落盘产物
        jp = self.proj / "标书检查" / ("机器检查_%s_技术标.json" % PROJECT)
        self.assertTrue(jp.is_file())
        doc = json.loads(jp.read_text(encoding="utf-8"))
        self.assertEqual(doc["kind"], "tech")
        self.assertEqual(doc["tag"], "技术标")

    def test_kind_biz_keeps_original_rules(self):
        # biz：CHECK_RULES 全量（报价/证书/期限/素材），无 tech 检查项
        (self.proj / "商务标").mkdir(exist_ok=True)
        res = R.run_rule_checks("", str(self.proj), out_dir=str(self.proj / "商务标"),
                                kind="biz", tag="")
        ids = [c["id"] for c in res["检查"]]
        self.assertIn("quote", ids)
        self.assertIn("cert", ids)
        self.assertIn("deadline", ids)
        self.assertNotIn("tech_structure", ids)


if __name__ == "__main__":
    unittest.main()
