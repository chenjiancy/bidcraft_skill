# -*- coding: utf-8 -*-
"""M8 模拟评标单测：评分标准解析（kind 判定/参数抽取）+ 客观分计算 + 报价反推 + eval-run 产物落盘。"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scripts"))

from m8_eval import eval_std, evaluator   # noqa: E402
from m8_eval import rules as m8rules       # noqa: E402
import m8_eval as m8cli                   # noqa: E402  （包即 __init__）
from m4_tender import rules as t_rules                       # noqa: E402
from _shared import core                                     # noqa: E402


# --------------------------------------------------------------------------
# 构造 M4 产物
# --------------------------------------------------------------------------
def _points(score_items, pricing=None):
    mods = [
        {"id": "basic", "title": "基础信息", "type": "fields", "fields": {}},
        {"id": "scoring", "title": "评分办法", "type": "mixed",
         "method": {"value": "综合评分法（100分）", "evidence": "e"},
         "score_items": score_items},
    ]
    if pricing:
        mods.append({"id": "pricing", "title": "报价要求", "type": "fields", "fields": pricing})
    return {"project": "P", "modules": mods, "diffs": []}


def _mk_item(text, weight):
    return {"item": text, "weight": str(weight), "unit": "分", "evidence": "e"}


_SCORE_ITEMS = [
    _mk_item("ISO三体系认证（质量/环境/职业健康安全管理体系认证证书且在有效期内，各1分）", 3),
    _mk_item("业绩：2021年1月1日以来承担过单份合同工程施工投资估算价6000万元以上市政公用工程监理业绩，每个4分，满分8分", 8),
    _mk_item("总监具有市政工程相关专业中级以上（含）工程师职称得1分（附职称证书扫描件）", 1),
    _mk_item("监理人员（不含总监）市政工程相关专业中级以上职称每人1分最多3分（以附表7人员评审）", 3),
    _mk_item("投标人荣誉：2021年1月1日以来获得地级市以上表彰，1个3分，另1个2分，满分5分", 5),
    _mk_item("报价：与评标基准价（有效投标报价算术平均值）相同得30分；每高于基准价1%扣0.2分，每低于1%扣0.1分，扣完为止；高于最高限价无效", 30),
    _mk_item("监理大纲·综合比较阐述（10个子项，每项5分）", 50),
    _mk_item("监理大纲暗标要求：每子评分项篇幅最多不超过10页，超过则不予评审得分；不得泄露信息", 50),
]


def _mat(items):
    return {"project": "P", "items": items}


class TestParseScoring(unittest.TestCase):
    def setUp(self):
        self.std = eval_std.parse_scoring(_points(_SCORE_ITEMS))

    def test_kind_classification(self):
        kinds = [p["kind"] for p in self.std["items"]]
        self.assertEqual(kinds, ["iso", "perf", "dir_title", "staff_title",
                                 "honor", "quote", "outline", "rule"])

    def test_rule_before_outline(self):
        # 暗标规则项（含"监理大纲"+"篇幅"）必须归 rule 而非 outline
        rule_item = [p for p in self.std["items"] if "暗标" in p["item"]][0]
        self.assertEqual(rule_item["kind"], "rule")

    def test_title_subdivide(self):
        kinds = [p["kind"] for p in self.std["items"]]
        self.assertIn("dir_title", kinds)
        self.assertIn("staff_title", kinds)

    def test_quote_params(self):
        q = [p for p in self.std["items"] if p["kind"] == "quote"][0]
        self.assertEqual(q["params"]["max"], 30.0)
        self.assertEqual(q["params"]["hi_punish"], 0.2)
        self.assertEqual(q["params"]["lo_punish"], 0.1)
        self.assertIn("算术平均值", q["params"]["base_desc"] or "")

    def test_perf_params(self):
        p = [x for x in self.std["items"] if x["kind"] == "perf"][0]
        self.assertEqual(p["params"]["per"], 4.0)
        self.assertEqual(p["params"]["max"], 8.0)
        self.assertEqual(p["params"]["require_type"], 6000.0)
        self.assertEqual(p["params"]["year_start"], "2021-01-01")

    def test_unknown_kind(self):
        std = eval_std.parse_scoring(_points([_mk_item("某某特殊评分项", 2)]))
        self.assertEqual(std["items"][0]["kind"], "unknown")

    def test_totals(self):
        self.assertAlmostEqual(self.std["objective_total"], 20.0)
        self.assertAlmostEqual(self.std["quote_total"], 30.0)
        self.assertAlmostEqual(self.std["subjective_total"], 50.0)


class TestCalcObjective(unittest.TestCase):
    def setUp(self):
        self.std = eval_std.parse_scoring(_points(_SCORE_ITEMS))

    def _mat(self):
        return _mat([
            {"category": "体系认证", "subtype": "ISO三体系认证证书",
             "purpose": "质量/环境/职业健康安全管理体系认证各1分共3分"},
            {"category": "业绩", "subtype": "市政公用工程监理业绩合同", "purpose": "x"},
            {"category": "业绩", "subtype": "市政公用工程监理业绩合同", "purpose": "y"},
            {"category": "人员", "subtype": "总监职称证书", "purpose": "z"},
            {"category": "人员", "subtype": "监理人员职称证书", "purpose": "w"},
            {"category": "人员", "subtype": "监理人员职称证书", "purpose": "v"},
            {"category": "荣誉", "subtype": "先进监理企业表彰证书", "purpose": "u"},
            {"category": "荣誉", "subtype": "示范监理企业表彰证书", "purpose": "t"},
        ])

    def test_scores(self):
        res = evaluator.calc_objective(self.std, self._mat())
        got = {r["kind"]: r["score"] for r in res}
        self.assertEqual(got["iso"], 3.0)      # 1 条三体系 → 3
        self.assertEqual(got["perf"], 8.0)     # 2 条 × 4 → 满 8
        self.assertEqual(got["dir_title"], 1.0)
        self.assertEqual(got["staff_title"], 2.0)  # 2 条
        self.assertEqual(got["honor"], 5.0)    # 1 个 3 + 1 个 2 → 满 5

    def test_missing_dir_title(self):
        mat = self._mat()
        mat["items"] = [i for i in mat["items"] if i["subtype"] != "总监职称证书"]
        res = evaluator.calc_objective(self.std, mat)
        got = {r["kind"]: r["score"] for r in res}
        self.assertEqual(got["dir_title"], 0.0)


class TestQuoteAnalysis(unittest.TestCase):
    def setUp(self):
        q = [p for p in eval_std.parse_scoring(_points(_SCORE_ITEMS))["items"]
             if p["kind"] == "quote"][0]
        self.params = q["params"]

    @staticmethod
    def _nearest(curve, b):
        return min(curve, key=lambda c: abs(c["base"] - b))

    def test_score_at_base_equal(self):
        # B ≈ X → 满分 30（采样步长 ~3200，最近点偏差 ≤1.6% → 得分误差 ≤0.2）
        qa = evaluator.quote_analysis(100000.0, 1013600.0, self.params)
        pt = self._nearest(qa["curve"], 100000.0)
        self.assertGreaterEqual(pt["score"], 29.5)

    def test_high_penalty(self):
        # B = X/1.1 → 偏高约 10% → 扣 10*0.2=2 → ≈28
        qa = evaluator.quote_analysis(100000.0, 1013600.0, self.params)
        pt = self._nearest(qa["curve"], 100000 / 1.1)
        self.assertAlmostEqual(pt["score"], 28.0, delta=0.6)

    def test_low_penalty(self):
        # B = 1.1X → 偏低约 9.09% → 扣 ≈0.91 → ≈29.09
        qa = evaluator.quote_analysis(100000.0, 1013600.0, self.params)
        pt = self._nearest(qa["curve"], 110000.0)
        self.assertAlmostEqual(pt["score"], 29.09, delta=0.6)

    def test_bands_capped_at_cap(self):
        # 保住 24 分（80%）：B ∈ [120615, 392000]；上限裁剪到 1013600 以内（本用例远低于 cap 不受影响）
        qa = evaluator.quote_analysis(156800.0, 1013600.0, self.params)
        b24 = next(b for b in qa["bands"] if abs(b["target"] - 24.0) < 0.1)
        self.assertGreaterEqual(b24["range"][0], 120000.0)
        self.assertLessEqual(b24["range"][1], 1013600.0)

    def test_no_quote(self):
        qa = evaluator.quote_analysis(None, 1013600.0, self.params)
        self.assertFalse(qa["provided"])
        self.assertIn("未提供报价", qa["note"])

    def test_over_cap_risk(self):
        qa = evaluator.quote_analysis(2000000.0, 1013600.0, self.params)
        self.assertTrue(any("高于最高限价" in r for r in qa["risks"]))


class TestEvalRunE2E(unittest.TestCase):
    def _mk_project(self, root):
        ent = root / "企业X" / "项目级" / "P"
        tdir = ent / "招标解析"
        tdir.mkdir(parents=True)
        core.write_json(str(tdir / ("%s.json" % t_rules.points_base("P"))),
                        _points(_SCORE_ITEMS, {"报价上限（废标线）": {"value": "最高投标限价101.36万元"}}))
        core.write_json(str(tdir / ("%s.json" % t_rules.list_base("P"))),
                        _mat([{"category": "体系认证", "subtype": "ISO三体系认证证书",
                               "purpose": "质量/环境/职业健康"},
                              {"category": "业绩", "subtype": "市政公用工程监理业绩合同", "purpose": "x"}]))
        return ent

    def _run(self, ent, quote="156800"):
        args = argparse.Namespace(root=str(ent.parent.parent.parent), enterprise="企业X",
                                  project="P", quote=quote, tdir="", mat="", bid="")
        m8cli.cmd_eval_run(args)

    def test_eval_run_outputs(self):
        import argparse
        with tempfile.TemporaryDirectory() as td:
            ent = self._mk_project(Path(td))
            args = argparse.Namespace(root=str(Path(td)), enterprise="企业X",
                                      project="P", quote="156800", tdir="", mat="", bid="")
            m8cli.cmd_eval_run(args)
            out = ent / m8cli.OUT_DIR_NAME
            base = m8cli.sim_base("P")
            self.assertTrue((out / ("%s.json" % base)).is_file())
            self.assertTrue((out / ("%s.md" % base)).is_file())
            self.assertTrue((out / ("%s.html" % m8cli.report_base("P"))).is_file())
            back = core.read_json(str(out / ("%s.json" % base)), None)
            self.assertEqual(back["project"], "P")
            self.assertAlmostEqual(back["summary"]["objective_score"], 7.0)  # ISO3+业绩4

    def test_tdir_outside_rejected(self):
        import argparse
        with tempfile.TemporaryDirectory() as td:
            ent = self._mk_project(Path(td))
            other = Path(td) / "其它项目"
            other.mkdir()
            args = argparse.Namespace(root=str(Path(td)), enterprise="企业X",
                                      project="P", quote="156800",
                                      tdir=str(other), mat="", bid="")
            with self.assertRaises(core.LibraryError):
                m8cli.cmd_eval_run(args)


def _valid_subjective():
    return {
        "project": "P", "channel": "B", "审查日期": "2026-10-18", "对象": "监理大纲",
        "主观评分": [
            {"子项": "质量保证措施", "满分": 5,
             "预估分": {"min": 3, "max": 4, "建议": 4}, "档次": "较齐全",
             "证据锚点": "监理大纲 第3章 第2节（摘录）", "失分原因": "深度一般",
             "补强建议": "补充针对性论证", "风险": "🟠"}
        ],
        "主观合计": {"min": 30, "max": 40, "建议": 36, "满分": 50},
        "失分诊断": [{"子项": "质量保证措施", "失分": 1, "优先级": "中", "说明": "x"}],
        "与通道A协作": "客观分已由通道A 评", "结论": "主观分预估 [30,40]",
    }


class TestValidateSubjectiveJson(unittest.TestCase):
    def test_valid_passes(self):
        ok, issues = m8rules.validate_subjective_json(_valid_subjective())
        self.assertTrue(ok, issues)

    def test_channel_must_be_b(self):
        doc = _valid_subjective()
        doc["channel"] = "A"
        ok, _ = m8rules.validate_subjective_json(doc)
        self.assertFalse(ok)

    def test_missing_keys_rejected(self):
        doc = _valid_subjective()
        del doc["主观合计"]
        ok, issues = m8rules.validate_subjective_json(doc)
        self.assertFalse(ok)
        self.assertTrue(any("主观合计" in x for x in issues))

    def test_bad_risk_rejected(self):
        doc = _valid_subjective()
        doc["主观评分"][0]["风险"] = "🟣"
        ok, _ = m8rules.validate_subjective_json(doc)
        self.assertFalse(ok)

    def test_min_over_max_rejected(self):
        doc = _valid_subjective()
        doc["主观评分"][0]["预估分"] = {"min": 5, "max": 3, "建议": 4}
        ok, _ = m8rules.validate_subjective_json(doc)
        self.assertFalse(ok)

    def test_bad_priority_rejected(self):
        doc = _valid_subjective()
        doc["失分诊断"][0]["优先级"] = "极高"
        ok, _ = m8rules.validate_subjective_json(doc)
        self.assertFalse(ok)


class TestEvalParseAndReport(unittest.TestCase):
    def _mk_project(self, root):
        ent = root / "企业X" / "项目级" / "P"
        tdir = ent / "招标解析"
        tdir.mkdir(parents=True)
        core.write_json(str(tdir / ("%s.json" % t_rules.points_base("P"))),
                        _points(_SCORE_ITEMS, {"报价上限（废标线）": {"value": "最高投标限价101.36万元"}}))
        core.write_json(str(tdir / ("%s.json" % t_rules.list_base("P"))),
                        _mat([{"category": "体系认证", "subtype": "ISO三体系认证证书",
                               "purpose": "质量/环境/职业健康"},
                              {"category": "业绩", "subtype": "市政公用工程监理业绩合同", "purpose": "x"}]))
        return ent

    def test_eval_parse_and_report(self):
        import argparse
        with tempfile.TemporaryDirectory() as td:
            ent = self._mk_project(Path(td))
            common = dict(root=str(Path(td)), enterprise="企业X", project="P")
            m8cli.cmd_eval_run(argparse.Namespace(quote="156800", tdir="", mat="", bid="", **common))
            # 通道B 落盘
            sub = _valid_subjective()
            md_src = Path(td) / "sub.md"
            json_src = Path(td) / "sub.json"
            md_src.write_text("# 主观评审\n", encoding="utf-8")
            core.write_json(str(json_src), sub)
            m8cli.cmd_eval_parse(argparse.Namespace(md=str(md_src), json_file=str(json_src), **common))
            out = ent / m8cli.OUT_DIR_NAME
            self.assertTrue((out / ("%s.json" % m8cli.subjective_base("P"))).is_file())
            self.assertTrue((out / ("%s.md" % m8cli.subjective_base("P"))).is_file())
            # 合并渲染
            m8cli.cmd_eval_report(argparse.Namespace(**common))
            html = out / ("%s.html" % m8cli.report_base("P"))
            self.assertTrue(html.is_file())
            content = html.read_text(encoding="utf-8")
            self.assertIn("主观分明细", content)
            self.assertIn("质量保证措施", content)

    def test_eval_report_without_subjective(self):
        import argparse
        with tempfile.TemporaryDirectory() as td:
            ent = self._mk_project(Path(td))
            common = dict(root=str(Path(td)), enterprise="企业X", project="P")
            m8cli.cmd_eval_run(argparse.Namespace(quote="156800", tdir="", mat="", bid="", **common))
            m8cli.cmd_eval_report(argparse.Namespace(**common))
            html = ent / m8cli.OUT_DIR_NAME / ("%s.html" % m8cli.report_base("P"))
            self.assertTrue(html.is_file())
            self.assertIn("主观分未评", html.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
