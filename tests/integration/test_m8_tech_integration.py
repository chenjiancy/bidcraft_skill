# -*- coding: utf-8 -*-
"""M8 T16 集成测试（L2）：真实项目 eval-run → techText 发现 + outline 章节注入 + 产物落盘。

覆盖：M4 产物（scoring 含 outline 主观项）+ M6 技术标（章节树 + 正文 + 覆盖矩阵）→
cmd_eval_run → 模拟评标 json 带 techText（found）+ standard outline 项带 techChapters；
无 M6 文本 → techText found=False（通道B 降级"无文本"）。
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "..", "scripts"))

from _shared import core                       # noqa: E402
import m8_eval as M8                           # noqa: E402  （包命名空间=__init__.py）
from m8_eval import tech_text as T             # noqa: E402

PROJECT = "T16集成项目"
ENT = "T16集成企业"


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
            "performance": [{"name": "T16业绩", "path": perf_path}],
            "qualification_required": [], "iso_certificates": [], "honors": [],
            "items": [{"category": "业绩", "name": "T16业绩", "subtype": "业绩",
                       "path": perf_path}]}


def _mk_tech(proj):
    tech = proj / "技术标"
    (tech / "章节").mkdir(parents=True)
    (tech / "章节树.json").write_text(
        json.dumps({"project": PROJECT, "chapters": [
            {"id": "ch-01", "no": "1", "title": "工程概况与监理范围", "level": 1,
             "scoreRefs": [{"idx": 0, "item": "监理大纲（50分）", "weight": 50}],
             "keyPoints": ["工程概况", "监理范围", "质量"], "wordCnt": 3000}]},
            ensure_ascii=False), encoding="utf-8")
    (tech / "章节" / "ch-01.md").write_text(
        "第一章 工程概况与监理范围\n本节覆盖工程概况、监理范围与质量控制要点，"
        "对施工全过程实施三控三管一协调。", encoding="utf-8")
    (tech / "检查").mkdir(exist_ok=True)
    (tech / "检查" / ("覆盖矩阵_%s.json" % PROJECT)).write_text(
        json.dumps({"project": PROJECT, "rows": [
            {"idx": 0, "item": "监理大纲（50分）", "kind": "outline", "weight": 50,
             "enforced": True, "covered": True, "weak": False, "ratio": 1.0,
             "chapters": ["ch-01"], "level": None, "note": ""}]},
            ensure_ascii=False), encoding="utf-8")


class M8TechIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.ent, _ = core.Library(self.root).init_enterprise(ENT)
        self.proj = self.ent / "项目级" / PROJECT
        self.tdir = self.proj / "招标解析"
        self.tdir.mkdir(parents=True)
        (self.tdir / ("投标要点_%s.json" % PROJECT)).write_text(
            json.dumps(_points(), ensure_ascii=False), encoding="utf-8")
        perf = self.proj / "业绩" / "T16业绩.pdf"
        perf.parent.mkdir(parents=True)
        perf.write_bytes(b"%PDF-1.4 fake")
        (self.tdir / ("素材清单_%s.json" % PROJECT)).write_text(
            json.dumps(_material(str(perf)), ensure_ascii=False), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def _args(self, **kw):
        base = {"root": str(self.root), "enterprise": ENT, "project": PROJECT,
                "tdir": "", "mat": "", "bid": "", "quote": None}
        base.update(kw)
        from types import SimpleNamespace
        return SimpleNamespace(**base)

    def test_eval_run_discovers_tech_text(self):
        _mk_tech(self.proj)
        M8.cmd_eval_run(self._args())
        jp = self.proj / "模拟评标" / ("模拟评标_%s.json" % PROJECT)
        self.assertTrue(jp.is_file())
        doc = json.loads(jp.read_text(encoding="utf-8"))
        tt = doc.get("techText")
        self.assertIsNotNone(tt)
        self.assertTrue(tt["found"])
        self.assertEqual(tt["chapters"][0]["id"], "ch-01")
        self.assertGreater(tt["totalChars"], 0)
        # outline 项注入章节
        outline = next(x for x in doc["standard"]["items"] if x["kind"] == "outline")
        self.assertEqual(outline["techChapters"], ["ch-01"])
        self.assertTrue(outline["techCovered"])
        # 非主观项不受影响
        perf = next(x for x in doc["standard"]["items"] if x["kind"] == "perf")
        self.assertNotIn("techChapters", perf)

    def test_eval_run_without_tech_degrades(self):
        M8.cmd_eval_run(self._args())
        jp = self.proj / "模拟评标" / ("模拟评标_%s.json" % PROJECT)
        doc = json.loads(jp.read_text(encoding="utf-8"))
        tt = doc.get("techText")
        self.assertIsNotNone(tt)
        self.assertFalse(tt["found"])            # 降级：通道B 输出"无文本待 M6 精评"

    def test_discover_direct(self):
        _mk_tech(self.proj)
        r = T.discover_tech_text(str(self.proj), PROJECT)
        self.assertTrue(r["found"])
        self.assertEqual(len(r["chapters"]), 1)
        self.assertIsNotNone(r["coverage_rows"])


if __name__ == "__main__":
    unittest.main()
