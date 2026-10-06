# -*- coding: utf-8 -*-
"""L1 单元测试：M4 通道A 文档解析规则引擎（rule_extract.extract_fields）。
纯逻辑无 I/O。"""
import os
import sys
import unittest

_SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scripts")
sys.path.insert(0, os.path.abspath(_SCRIPTS))
from m4_tender import rule_extract  # noqa: E402

SAMPLE = """和县2026年老旧小区改造项目（EPC总承包）监理采购
项目编号：HXTD-2026-018
最高投标限价：48.86万元
投标截止时间：2026年8月10日 14:00
开标时间：2026年8月10日 14:00
服务期：自合同签订之日起至缺陷责任期结束
投标有效期：90日历天
投标保证金：不采用
本次招标不接受联合体投标。
采用纸质投标，正本1份副本2份，现场递交。
法定代表人须实名制核验，须提供身份证原件。
投标人须具有房屋建筑工程监理甲级资质。
拟派总监理工程师1名、专业监理工程师2名、监理员2名。
监理费率报价不得超过1.5%。
评分：监理大纲50分、企业实力18分、荣誉8分、总监荣誉4分、价格20分，合计100分。
"""


class TestExtractFields(unittest.TestCase):
    def test_single_value_fields(self):
        f = rule_extract.extract_fields(SAMPLE)
        self.assertEqual(f["project_no"]["value"], "HXTD-2026-018")
        self.assertEqual(f["budget"]["value"], "48.86")
        self.assertIn("2026年8月10日 14:00", f["bid_deadline"]["value"])
        self.assertIn("2026年8月10日 14:00", f["open_time"]["value"])
        self.assertIn("缺陷责任期", f["service_period"]["value"])
        self.assertIn("90日历天", f["valid_period"]["value"])
        self.assertIn("不采用", f["deposit"]["value"])
        self.assertIn("不接受", f["joint_venture"]["value"])
        self.assertIn("纸质投标", f["electronic"]["value"])
        self.assertIn("实名制", f["real_name"]["value"])

    def test_qualification(self):
        f = rule_extract.extract_fields(SAMPLE)
        self.assertIn("房屋建筑工程监理甲级资质", f["qualification"]["value"])

    def test_multi_value_fields(self):
        f = rule_extract.extract_fields(SAMPLE)
        self.assertIsInstance(f["staff_count"]["value"], list)
        self.assertIn("总监理工程师1名", f["staff_count"]["value"])
        self.assertIn("专业监理工程师2名", f["staff_count"]["value"])
        self.assertIn("1.5", f["percent"]["value"])

    def test_lines_anchor(self):
        f = rule_extract.extract_fields(SAMPLE)
        # "项目编号：HXTD-2026-018" 在第 2 行（1 基）
        self.assertIn(2, f["project_no"]["lines"])
        self.assertTrue(f["project_no"]["evidence"])

    def test_no_hit_absent(self):
        f = rule_extract.extract_fields("没有任何可抽取字段的普通文本。")
        self.assertEqual(f, {})

    def test_spaced_date_and_deadline_variants(self):
        """原文日期带空格、截止表述为「响应文件提交截止时间」（真实项目句式）。"""
        text = ("开标时间：2026年 8 月 10 日14：00\n"
                "响应文件提交截止时间：同开标时间\n"
                "递交响应文件截止时间：2026年8月10日 14:00\n")
        f = rule_extract.extract_fields(text)
        self.assertIn("2026年 8 月 10 日14：00", f["open_time"]["value"])
        self.assertIn("同开标时间", f["bid_deadline"]["value"])   # 单值字段取首中

    def test_empty_text(self):
        self.assertEqual(rule_extract.extract_fields(""), {})

    def test_label_module_mapping(self):
        f = rule_extract.extract_fields(SAMPLE)
        self.assertEqual(f["project_no"]["module"], "basic")
        self.assertEqual(f["qualification"]["module"], "qualification")
        self.assertEqual(f["staff_count"]["module"], "staff")
        self.assertEqual(f["percent"]["module"], "pricing")

    def test_score_points(self):
        """v2.4：评分分值抽取（模块5 scoring）。"""
        f = rule_extract.extract_fields(SAMPLE)
        self.assertEqual(f["score_points"]["module"], "scoring")
        vals = f["score_points"]["value"]
        self.assertIn("50", vals)
        self.assertIn("18", vals)
        self.assertIn("20", vals)

    def test_score_sum_check(self):
        """v2.4：评分分值合计校验派生字段（参考合计 vs 100）。"""
        f = rule_extract.extract_fields(SAMPLE)
        sc = f["score_sum_check"]
        self.assertEqual(sc["label"], "评分分值合计校验")
        self.assertEqual(sc["module"], "scoring")
        # SAMPLE 中抽取分值含 50+18+8+4+20=100（含 1.5 费率与 100 合计 行内的干扰值）
        self.assertEqual(sc["value"]["参考总分"], 100)
        self.assertTrue(sc["note"])


if __name__ == "__main__":
    unittest.main()
