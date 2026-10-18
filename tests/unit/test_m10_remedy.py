# -*- coding: utf-8 -*-
"""M9 失分补救指引单元测试。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scripts"))

from m10_remedy import remedy  # noqa: E402


def _mk_eval(issues=None, unrated=None, risks=None, bands=None, standard_items=None):
    issues = issues or []
    unrated = unrated or []
    risks = risks or []
    bands = bands or []
    return {
        "project": "测试项目",
        "standard": {"items": standard_items or []},
        "summary": {
            "objective_score": 6.0, "objective_max": 20.0,
            "issues": issues,
            "unrated": unrated,
        },
        "quote": {"provided": True, "risks": risks, "bands": bands},
    }


def _mk_issue(kind, gap, per=None, item="评分项", max_=8.0, amount=6000.0, year_start="2021-01-01",
              first=None, next_=None):
    """模拟真实 M8 产物：issue 不含 params，params 在 standard.items 同 kind 项。"""
    params = {"max": max_}
    if per is not None:
        params["per"] = per
    if amount is not None:
        params["require_type"] = amount
    if year_start:
        params["year_start"] = year_start
    if first is not None:
        params["first"] = first
    if next_ is not None:
        params["next"] = next_
    return {"kind": kind, "item": item, "score": max_ - gap, "max": max_, "gap": gap,
            "advice": "补齐/核对证据后最多可加 %.1f 分" % gap}


def _std_items(*kinds_params):
    """standard.items：kinds_params = [(kind, params), ...]。"""
    return [{"kind": k, "params": p} for k, p in kinds_params]


class GenTasksTest(unittest.TestCase):
    def test_perf_gap4_promotes_one_task(self):
        doc = remedy.gen_tasks(_mk_eval(
            issues=[_mk_issue("perf", 4.0, per=4.0)],
            standard_items=_std_items(("perf", {"max": 8.0, "per": 4.0, "require_type": 6000.0, "year_start": "2021-01-01"}))))
        tasks = doc["tasks"]
        self.assertEqual(len(tasks), 1)
        t = tasks[0]
        self.assertEqual(t["类型"], "素材补齐")
        self.assertEqual(t["优先级"], "高")
        self.assertEqual(t["预期加分"], 4.0)
        self.assertEqual(t["涉及素材"]["category"], "业绩")
        self.assertIn("1 份", " ".join(t["动作步骤"]))
        self.assertIn("6000.0万", " ".join(t["动作步骤"]))
        self.assertEqual(doc["summary"]["可追分合计"], 4.0)

    def test_staff_title_gap2_promotes_two(self):
        doc = remedy.gen_tasks(_mk_eval(
            issues=[_mk_issue("staff_title", 2.0, per=1.0, max_=3.0)],
            standard_items=_std_items(("staff_title", {"max": 3.0, "per": 1.0}))))
        t = doc["tasks"][0]
        self.assertEqual(t["类型"], "素材补齐")
        self.assertIn("2 名", " ".join(t["动作步骤"]))
        self.assertEqual(t["优先级"], "中")

    def test_honor_gap2_one_next(self):
        doc = remedy.gen_tasks(_mk_eval(
            issues=[_mk_issue("honor", 2.0, first=3.0, next_=2.0, max_=5.0)],
            standard_items=_std_items(("honor", {"max": 5.0, "first": 3.0, "next": 2.0, "year_start": "2021-01-01"}))))
        t = doc["tasks"][0]
        self.assertEqual(t["预期加分"], 2.0)
        self.assertIn("2021", " ".join(t["动作步骤"]))

    def test_quote_risk_produces_strategy_task(self):
        doc = remedy.gen_tasks(_mk_eval(
            issues=[{"kind": "quote", "item": "报价分（反推）", "score": None, "max": 30.0,
                     "gap": None, "advice": "报价 156800 元：保住 24.0 分需基准价 ∈ [120615.38, 392000.0]"}],
            risks=["报价明显低于限价 50%%：须提供成本构成说明"], bands=[
            {"target": 24.0, "range": [120615.0, 392000.0]}]))
        t = doc["tasks"][0]
        self.assertEqual(t["类型"], "报价策略")
        self.assertEqual(t["优先级"], "高")
        self.assertIn("成本构成说明", " ".join(t["动作步骤"]))
        self.assertIn("保住 24.0 分", " ".join(t["动作步骤"]))

    def test_rule_unrated_produces_compliance_task(self):
        doc = remedy.gen_tasks(_mk_eval(unrated=[{"kind": "rule", "item": "暗标要求", "note": "篇幅≤10页"}]))
        t = doc["tasks"][0]
        self.assertEqual(t["类型"], "格式合规")
        self.assertEqual(t["优先级"], "高")
        self.assertIn("10页", " ".join(t["动作步骤"]))

    def test_subjective_diagnostics_produce_tasks(self):
        sub = {"主观合计": {"min": 47, "max": 50, "满分": 50},
               "失分诊断": [
                   {"子项": "第六章 协调案例", "失分": 1, "优先级": "中", "说明": "补多专业交叉协调场景推演"},
                   {"子项": "暗标篇幅", "失分": 0, "优先级": "高", "说明": "逐页人工确认"}]}
        doc = remedy.gen_tasks(_mk_eval(), subjective_doc=sub)
        tasks = doc["tasks"]
        self.assertEqual(len(tasks), 2)
        self.assertEqual(tasks[0]["类型"], "内容补强")
        self.assertEqual(tasks[0]["预期加分"], 1.0)
        self.assertEqual(tasks[1]["类型"], "合规确认")
        self.assertEqual(tasks[1]["优先级"], "高")
        self.assertEqual(doc["summary"]["主观分"]["min"], 47)

    def test_empty_gap_generates_nothing(self):
        doc = remedy.gen_tasks(_mk_eval())
        self.assertEqual(doc["tasks"], [])
        self.assertEqual(doc["summary"]["可追分合计"], 0)

    def test_priority_low_for_small_gap(self):
        doc = remedy.gen_tasks(_mk_eval(
            issues=[_mk_issue("honor", 0.5, first=3.0, next_=2.0, max_=5.0)],
            standard_items=_std_items(("honor", {"max": 5.0, "first": 3.0, "next": 2.0, "year_start": "2021-01-01"}))))
        self.assertEqual(doc["tasks"][0]["优先级"], "低")


class ToMdTest(unittest.TestCase):
    def test_md_contains_ids_and_priority(self):
        doc = remedy.gen_tasks(_mk_eval(issues=[_mk_issue("perf", 4.0, per=4.0)],
                                        standard_items=_std_items(("perf", {"max": 8.0, "per": 4.0, "require_type": 6000.0, "year_start": "2021-01-01"}))),
                               subjective_doc={"主观合计": {"min": 47, "max": 50, "满分": 50}, "失分诊断": []})
        md = remedy.to_md(doc)
        self.assertIn("# 失分补救任务单", md)
        self.assertIn("R01", md)
        self.assertIn("可追分合计", md)
        self.assertIn("素材补齐", md)

    def test_html_render_contains_kpi_cards_and_flow(self):
        import tempfile
        from pathlib import Path
        from m10_remedy import remedy_report
        doc = remedy.gen_tasks(_mk_eval(
            issues=[_mk_issue("perf", 4.0, per=4.0),
                    _mk_issue("staff_title", 2.0, per=1.0, max_=3.0)],
            standard_items=_std_items(("perf", {"max": 8.0, "per": 4.0, "require_type": 6000.0, "year_start": "2021-01-01"}),
                                      ("staff_title", {"max": 3.0, "per": 1.0})),
            risks=["低于成本审查"]),
            subjective_doc={"主观合计": {"min": 47, "max": 50, "满分": 50}, "失分诊断": []})
        tmp = Path(tempfile.mkdtemp()) / "task.html"
        remedy_report.render_task_html("测试项目", doc, tmp)
        t = tmp.read_text(encoding="utf-8")
        self.assertIn("<title>失分补救任务单", t)
        self.assertIn("可追分合计", t)
        self.assertIn("R01", t)
        self.assertIn("评标→补救→重评", t)
        self.assertIn("任务详情", t)
        self.assertIn("素材补齐", t)


if __name__ == "__main__":
    unittest.main()
