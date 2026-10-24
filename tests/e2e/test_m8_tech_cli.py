# -*- coding: utf-8 -*-
"""M8 T16 端到端测试（L3）：技术标章节评审 CLI 全链路 ——
eval-run（有 M6 技术标文本 → techText 入产物）→ eval-parse（主观评审含 techChapter）→
eval-report（HTML 含来源章节列）；无技术标文本 → eval-run 降级"无方案文本待 M6 精评"。
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "..", "scripts"))

import bidcraft                       # noqa: E402
from _shared import core              # noqa: E402

PROJECT = "T16端到端项目"
ENT = "T16端到端企业"


def _points():
    return {"project": PROJECT, "modules": [
        {"id": "scoring", "title": "评分办法", "type": "mixed",
         "method": {"value": "综合评分法", "evidence": "e"},
         "score_items": [
             {"idx": 0, "item": "监理大纲（50分）", "weight": 50, "unit": "分",
              "kind": "outline", "evidence": "E1"},
             {"idx": 1, "item": "类似工程业绩（每份4分，满分8分）", "weight": 8,
              "unit": "分", "evidence": "E2"}]},
        {"id": "reject", "title": "废标红线", "type": "items",
         "items": [{"type": "格式", "rule": "技术标总页数不超过 60 页；按明标编制", "evidence": "e"}]},
    ]}


def _material(perf_path):
    return {"project": PROJECT,
            "personnel": [{"name": "张三", "role": "总监理工程师"}],
            "企业基础信息": {"法定代表人姓名": "李四", "企业名称": ENT},
            "performance": [{"name": "端到端业绩", "path": perf_path}],
            "qualification_required": [], "iso_certificates": [], "honors": [],
            "items": [{"category": "业绩", "name": "端到端业绩", "subtype": "业绩",
                       "path": perf_path}]}


def _mk_tech(proj):
    tech = proj / "技术标"
    (tech / "章节").mkdir(parents=True)
    (tech / "章节树.json").write_text(
        json.dumps({"project": PROJECT, "chapters": [
            {"id": "ch-01", "no": "1", "title": "工程概况与监理范围", "level": 1,
             "scoreRefs": [{"idx": 0, "item": "监理大纲（50分）", "weight": 50}],
             "keyPoints": ["工程概况", "监理范围"], "wordCnt": 3000}]},
            ensure_ascii=False), encoding="utf-8")
    (tech / "章节" / "ch-01.md").write_text(
        "第一章 工程概况与监理范围\n本节覆盖工程概况与监理范围，对施工全过程实施三控三管一协调。",
        encoding="utf-8")
    (tech / "检查").mkdir(exist_ok=True)
    (tech / "检查" / ("覆盖矩阵_%s.json" % PROJECT)).write_text(
        json.dumps({"project": PROJECT, "rows": [
            {"idx": 0, "item": "监理大纲（50分）", "kind": "outline", "weight": 50,
             "enforced": True, "covered": True, "weak": False, "ratio": 1.0,
             "chapters": ["ch-01"], "level": None, "note": ""}]},
            ensure_ascii=False), encoding="utf-8")


def _subjective_json():
    return {"project": PROJECT, "channel": "B", "审查日期": "2026-10-24",
            "对象": "监理大纲（M6 技术标章节）",
            "主观评分": [{"子项": "监理大纲（50分）", "满分": 50,
                        "预估分": {"min": 40, "max": 45, "建议": 42},
                        "档次": "较齐全", "techChapter": "ch-01",
                        "证据锚点": "技术标/章节/ch-01.md 第1章（摘录：三控三管一协调）",
                        "失分原因": "综合比较阐述深度略欠", "补强建议": "第1章增补本项目针对性论证",
                        "风险": "🟢"}],
            "主观合计": {"min": 40, "max": 45, "建议": 42, "满分": 50},
            "失分诊断": [{"子项": "监理大纲", "失分": 8, "优先级": "中",
                        "说明": "综合比较阐述可再补强"}],
            "与通道A协作": "客观分/报价由通道A 评", "结论": "主观分预估 [40,45]，需补强综合比较阐述"}


class M8TechE2ETest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self._run("init-enterprise", "--name", ENT)
        self.ent = self.root / ENT
        self.proj = self.ent / "项目级" / PROJECT
        self.tdir = self.proj / "招标解析"
        self.tdir.mkdir(parents=True)
        (self.tdir / ("投标要点_%s.json" % PROJECT)).write_text(
            json.dumps(_points(), ensure_ascii=False), encoding="utf-8")
        perf = self.proj / "业绩" / "端到端业绩.pdf"
        perf.parent.mkdir(parents=True)
        perf.write_bytes(b"%PDF-1.4 fake")
        (self.tdir / ("素材清单_%s.json" % PROJECT)).write_text(
            json.dumps(_material(str(perf)), ensure_ascii=False), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, *argv):
        import io as _io
        from contextlib import redirect_stdout, redirect_stderr
        out, err, code = _io.StringIO(), _io.StringIO(), 0
        with redirect_stdout(out), redirect_stderr(err):
            try:
                bidcraft.main(["--root", str(self.root), "--enterprise", ENT] + list(argv))
            except SystemExit as e:
                code = e.code or 0
        return code, out.getvalue(), err.getvalue()

    def test_full_chain_with_tech_text(self):
        _mk_tech(self.proj)
        # 1) eval-run：发现技术标文本
        code, out, _ = self._run("eval-run", "--project", PROJECT)
        self.assertEqual(code, 0, out)
        self.assertIn("技术标文本已发现", out)
        jp = self.proj / "模拟评标" / ("模拟评标_%s.json" % PROJECT)
        doc = json.loads(jp.read_text(encoding="utf-8"))
        self.assertTrue(doc["techText"]["found"])
        outline = next(x for x in doc["standard"]["items"] if x["kind"] == "outline")
        self.assertEqual(outline["techChapters"], ["ch-01"])

        # 2) eval-parse：主观评审（含 techChapter）
        md_src = self.proj / "sub.md"
        md_src.write_text("# 主观评审\n结论：主观分预估 [40,45]。\n", encoding="utf-8")
        js_src = self.proj / "sub.json"
        js_src.write_text(json.dumps(_subjective_json(), ensure_ascii=False), encoding="utf-8")
        code, _, err = self._run("eval-parse", "--project", PROJECT,
                                 "--md", str(md_src), "--json-file", str(js_src))
        self.assertEqual(code, 0, err)

        # 3) eval-report：HTML 含来源章节列
        code, _, err = self._run("eval-report", "--project", PROJECT)
        self.assertEqual(code, 0, err)
        rp = self.proj / "模拟评标" / ("模拟评标报告_%s.html" % PROJECT)
        self.assertTrue(rp.is_file())
        html = rp.read_text(encoding="utf-8")
        self.assertIn("来源章节", html)
        self.assertIn("ch-01", html)
        self.assertIn("监理大纲（M6 技术标章节）", html)

    def test_degrades_without_tech_text(self):
        code, out, _ = self._run("eval-run", "--project", PROJECT)
        self.assertEqual(code, 0, out)
        self.assertIn("无方案文本待 M6 精评", out)
        jp = self.proj / "模拟评标" / ("模拟评标_%s.json" % PROJECT)
        doc = json.loads(jp.read_text(encoding="utf-8"))
        self.assertFalse(doc["techText"]["found"])


if __name__ == "__main__":
    unittest.main()
