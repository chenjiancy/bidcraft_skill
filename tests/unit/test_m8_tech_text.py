# -*- coding: utf-8 -*-
"""M8 T16 技术标章节评审扩展单测：文本发现（章节树/块剥离/降级）+ 评分项章节注入 + schema 扩展。"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scripts"))

from m8_eval import tech_text as T    # noqa: E402
from m8_eval import rules as R        # noqa: E402

PROJECT = "T16测试项目"


def _mk_tech(proj, tree=None, bodies=None, coverage=None):
    """合成 M6 技术标目录：章节树 + 正文（含块）+ 覆盖矩阵。bodies={cid: 正文文本}。"""
    tech = proj / "技术标"
    chdir = tech / "章节"
    chdir.mkdir(parents=True)
    if tree is not None:
        (tech / "章节树.json").write_text(
            json.dumps({"project": PROJECT, "chapters": tree}, ensure_ascii=False), encoding="utf-8")
    for cid, body in (bodies or {}).items():
        (chdir / ("%s.md" % cid)).write_text(body, encoding="utf-8")
    if coverage is not None:
        (tech / "检查").mkdir(exist_ok=True)
        (tech / "检查" / ("覆盖矩阵_%s.json" % PROJECT)).write_text(
            json.dumps({"project": PROJECT, "rows": coverage}, ensure_ascii=False), encoding="utf-8")
    return tech


def _tree():
    return [{"id": "ch-01", "no": "1", "title": "工程概况与监理范围", "level": 1,
             "scoreRefs": [{"idx": 0, "item": "监理大纲（50分）", "weight": 50}],
             "keyPoints": ["工程概况", "监理范围"], "wordCnt": 3000},
            {"id": "ch-02", "no": "2", "title": "质量管理", "level": 1, "scoreRefs": [],
             "keyPoints": [], "wordCnt": 1000}]


class DiscoverTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.proj = Path(self.tmp.name) / PROJECT

    def tearDown(self):
        self.tmp.cleanup()

    def test_no_tech_dir(self):
        r = T.discover_tech_text(str(self.proj), PROJECT)
        self.assertFalse(r["found"])
        self.assertIn("未交付", r["note"])

    def test_tech_dir_no_chapters(self):
        (self.proj / "技术标").mkdir(parents=True)
        r = T.discover_tech_text(str(self.proj), PROJECT)
        self.assertFalse(r["found"])

    def test_with_tree_and_bodies(self):
        _mk_tech(self.proj, tree=_tree(), bodies={
            "ch-01": "正文第一章：\n<!-- M6-COVERAGE\n{\"block\":\"M6-COVERAGE\",\"chapter\":\"ch-01\"}\n-->\n",
            "ch-02": "正文第二章内容较多。"})
        r = T.discover_tech_text(str(self.proj), PROJECT)
        self.assertTrue(r["found"])
        self.assertEqual([c["id"] for c in r["chapters"]], ["ch-01", "ch-02"])
        self.assertEqual(r["chapters"][0]["title"], "工程概况与监理范围")
        self.assertNotIn("M6-COVERAGE", r["chapters"][0]["path"] and "x")
        self.assertGreater(r["totalChars"], 0)
        self.assertIn("正文", r["note"])

    def test_strips_revise_block(self):
        _mk_tech(self.proj, tree=_tree(), bodies={
            "ch-01": "正文。\n<!-- M6-REVISE\n{\"changes\":[{\"where\":\"末尾\"}]}\n-->"})
        r = T.discover_tech_text(str(self.proj), PROJECT)
        self.assertTrue(r["found"])
        self.assertEqual(r["chapters"][0]["chars"], 2)     # 块被剥离，仅"正文。"计 2 字

    def test_glob_fallback_excludes_draft(self):
        _mk_tech(self.proj, tree=None, bodies={"ch-01": "正文一", "ch-02.draft": "草稿"})
        r = T.discover_tech_text(str(self.proj), PROJECT)
        self.assertEqual([c["id"] for c in r["chapters"]], ["ch-01"])
        self.assertNotIn("ch-02", [c["id"] for c in r["chapters"]])

    def test_coverage_loaded(self):
        _mk_tech(self.proj, tree=_tree(), bodies={"ch-01": "正文"},
                 coverage=[{"idx": 0, "item": "监理大纲（50分）", "kind": "outline",
                            "covered": True, "weak": False, "chapters": ["ch-01"]}])
        r = T.discover_tech_text(str(self.proj), PROJECT)
        self.assertIsNotNone(r["coverage_rows"])
        self.assertEqual(r["coverage_rows"][0]["chapters"], ["ch-01"])


class AttachTechTest(unittest.TestCase):
    def _std(self):
        return {"items": [
            {"idx": 0, "kind": "outline", "item": "监理大纲（50分）", "weight": 50.0},
            {"idx": 1, "kind": "perf", "item": "业绩", "weight": 8.0},
        ]}

    def test_outline_injected(self):
        tt = {"coverage_rows": [
            {"idx": 0, "covered": True, "weak": False, "chapters": ["ch-01"]}]}
        std = self._std()
        T.attach_tech_to_standard(std, tt)
        self.assertEqual(std["items"][0]["techChapters"], ["ch-01"])
        self.assertTrue(std["items"][0]["techCovered"])
        self.assertFalse(std["items"][0]["techWeak"])

    def test_non_outline_untouched(self):
        tt = {"coverage_rows": [{"idx": 1, "covered": True, "chapters": ["ch-02"]}]}
        std = self._std()
        T.attach_tech_to_standard(std, tt)
        self.assertNotIn("techChapters", std["items"][1])

    def test_no_coverage_untouched(self):
        std = self._std()
        T.attach_tech_to_standard(std, {"coverage_rows": None})
        self.assertNotIn("techChapters", std["items"][0])

    def test_missing_row_untouched(self):
        std = self._std()
        T.attach_tech_to_standard(std, {"coverage_rows": [{"idx": 5, "covered": True,
                                                           "chapters": []}]})
        self.assertNotIn("techChapters", std["items"][0])


class SchemaExtTest(unittest.TestCase):
    def _base(self):
        return {"project": "P", "channel": "B", "审查日期": "2026-10-24", "对象": "监理大纲（M6 技术标章节）",
                "主观评分": [{"子项": "a", "满分": 5, "预估分": {"min": 1, "max": 2, "建议": 2},
                            "档次": "一般", "证据锚点": "p", "失分原因": "r",
                            "补强建议": "b", "风险": "🟠"}],
                "主观合计": {"min": 1, "max": 2, "建议": 2, "满分": 5},
                "失分诊断": [], "结论": "c"}

    def test_tech_chapter_accepted(self):
        doc = self._base()
        doc["主观评分"][0]["techChapter"] = "ch-01"
        ok, issues = R.validate_subjective_json(doc)
        self.assertTrue(ok, issues)

    def test_tech_chapter_rejected_if_wrong_type(self):
        doc = self._base()
        doc["主观评分"][0]["techChapter"] = 123
        ok, _ = R.validate_subjective_json(doc)
        self.assertFalse(ok)

    def test_legacy_schema_still_valid(self):
        ok, issues = R.validate_subjective_json(self._base())
        self.assertTrue(ok, issues)


if __name__ == "__main__":
    unittest.main()
