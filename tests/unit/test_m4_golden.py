# -*- coding: utf-8 -*-
"""L1 单元测试：M4 Golden 基准测试集（建议④落实）。

基准样例来源：和县2026年老旧小区改造项目（EPC总承包）监理（首个完整实跑项目，
用户逐项裁决通过）。样例存 tests/fixtures/m4_golden/。

用途：提示词/规则/脚本改动前跑本文件 → 保证通道B 产物结构不回归
（9 模块全覆盖、diffs/verdicts 结构、通道A 字段结构）。纯逻辑无 I/O 副作用。
"""
import json
import os
import sys
import unittest

_SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scripts")
_FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "fixtures", "m4_golden")
sys.path.insert(0, os.path.abspath(_SCRIPTS))
from m4_tender import rules  # noqa: E402


def _load(name):
    with open(os.path.join(_FIXTURES, name), encoding="utf-8-sig") as f:
        return json.load(f)


class TestGoldenPoints(unittest.TestCase):
    """golden 投标要点：9 模块全覆盖 + diffs/verdicts 结构必须持续通过校验。"""

    def test_golden_points_file_exists(self):
        self.assertTrue(os.path.exists(os.path.join(_FIXTURES, "golden_points.json")),
                        "缺少 golden 基准样例（首个实跑项目沉淀）：tests/fixtures/m4_golden/golden_points.json")

    def test_validate_points_ok(self):
        doc = _load("golden_points.json")
        ok, issues = rules.validate_points_json(doc)
        self.assertTrue(ok, "golden 投标要点结构回归失败：%s" % "；".join(issues))

    def test_nine_modules_present(self):
        doc = _load("golden_points.json")
        ids = [m.get("id") for m in doc.get("modules", [])]
        for mid in rules.POINTS_MODULE_IDS:
            self.assertIn(mid, ids, "golden 缺少模块 %s（9 模块框架回归）" % mid)

    def test_verdicts_structure(self):
        doc = _load("golden_points.json")
        vs = doc.get("verdicts")
        self.assertTrue(isinstance(vs, list) and vs, "golden 应含已裁决事项（v2.4）")
        for v in vs:
            self.assertTrue(v.get("item") and v.get("decision"),
                            "已裁决事项须含 item/decision")


class TestGoldenDiff(unittest.TestCase):
    """golden 双通道差异：结构合法（diff_base 产物）。"""

    def test_diff_structure(self):
        doc = _load("golden_diff.json")
        self.assertIn("project", doc)
        diffs = doc.get("diffs")
        self.assertIsInstance(diffs, list)
        for d in diffs:
            self.assertTrue(d.get("解析项"))
            self.assertIn(d.get("差异类型"), rules.DIFF_TYPES)


class TestGoldenRule(unittest.TestCase):
    """golden 通道A 文档解析：字段结构 + 新规则（score_points/score_sum_check）在真实原文上的行为。"""

    def test_rule_fields_structure(self):
        doc = _load("golden_rule.json")
        fields = doc.get("fields") or {}
        self.assertTrue(fields)
        for fid, f in fields.items():
            self.assertTrue(f.get("label") and f.get("module"))
            self.assertIn("value", f)
            if fid != "score_sum_check":  # 派生校验字段无锚点，其余字段须带行号
                self.assertTrue(f.get("lines"), "字段 %s 须带原文行号锚点" % fid)

    def test_score_sum_check_present(self):
        doc = _load("golden_rule.json")
        fields = doc.get("fields") or {}
        self.assertIn("score_sum_check", fields,
                      "golden 通道A 应含评分分值合计校验（v2.4 规则扩展）")
        sc = fields["score_sum_check"]["value"]
        self.assertEqual(sc["参考总分"], 100)
        # 真实原文含合同性"分"语境干扰值 → 参考合计未必=100，仅要求 note 存在
        self.assertTrue(fields["score_sum_check"].get("note"))


class TestGoldenList(unittest.TestCase):
    """golden 素材清单：validate_list_json 通过（供 tender-check 对照）。"""

    def test_validate_list_ok(self):
        doc = _load("golden_list.json")
        ok, issues = rules.validate_list_json(doc)
        self.assertTrue(ok, "golden 素材清单结构回归失败：%s" % "；".join(issues))
        self.assertTrue(doc.get("items"))


if __name__ == "__main__":
    unittest.main()
