# -*- coding: utf-8 -*-
"""中小企业声明函占位化（SME_PH_PATTERNS，V5 真实验证 v2.1）单元测试。

覆盖两种来源：
- 空白招标格式（空编号/空白从业数据）；
- **已填写的企业自有样本**（牛屯河项目完整实例）——项目编号/招标人/
  项目名称/企业名称/从业数据全部 → 【占位】，固定条款一字不改。
"""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
from m5_project.gen_common import SME_PH_PATTERNS  # noqa: E402


def _apply(text):
    for old, new in SME_PH_PATTERNS:
        if re.search(old, text):
            text = re.sub(old, new, text)
    return text


class SmeBlankFormatTest(unittest.TestCase):
    """招标空白格式：空编号/空数据行。"""

    def test_empty_project_no(self):
        t = "参加（招标人名称）的 某项目监理（项目编号：）招标活动"
        out = _apply(t)
        self.assertIn("【项目编号】", out)
        self.assertNotIn("（项目编号：）", out)

    def test_empty_biz_data(self):
        t = "从业人员  人，营业收入为  万元，资产总额为  万元，属于   ；"
        out = _apply(t)
        self.assertIn("【从业人员】", out)
        self.assertIn("【营业收入】", out)
        self.assertIn("【资产总额】", out)
        self.assertIn("【企业类型】", out)


class SmeFilledSampleTest(unittest.TestCase):
    """已填写企业样本（牛屯河实例）占位化。"""

    P1 = ("本公司（联合体）郑重声明，根据《政府采购促进中小企业发展管理办法》"
          "（财库〔2020〕46号）的规定，本公司（联合体）参加含山县陶厂镇人民政府"
          "（招标人名称）的 长江流域牛屯河陶厂段水生态保护修复项目监理"
          "（项目编号：皖E1-18-2026-0242）招标活动，工程的施工单位全部由符合政策"
          "要求的中小企业（或者：服务全部由符合政策要求的中小企业承接）。")
    P2 = ("1.长江流域牛屯河陶厂段水生态保护修复项目监理（项目名称），属于其他未列明"
          "行业  ；承建（承接）企业为（企业名称）和县建设工程监理有限公司，从业人员"
          "  62   人，营业收入为  493.43   万元，资产总额为  134.59  万元，属于"
          "    小型企业   ；")

    def test_bidder_org(self):
        out = _apply(self.P1)
        self.assertIn("【招标人名称】（招标人名称）", out)
        self.assertNotIn("含山县陶厂镇人民政府", out)

    def test_project_name_p1(self):
        out = _apply(self.P1)
        self.assertIn("的 【项目名称】（项目编号：【项目编号】）", out)
        self.assertNotIn("长江流域牛屯河陶厂段水生态保护修复项目监理（项目编号", out)

    def test_project_no_filled(self):
        out = _apply(self.P1)
        self.assertIn("【项目编号】", out)
        self.assertNotIn("皖E1-18-2026-0242", out)

    def test_project_name_p2(self):
        out = _apply(self.P2)
        self.assertIn("1.【项目名称】（项目名称）", out)
        self.assertNotIn("长江流域牛屯河陶厂段水生态保护修复项目监理（项目名称）", out)

    def test_enterprise_name(self):
        out = _apply(self.P2)
        self.assertIn("（企业名称）【企业名称】", out)
        self.assertNotIn("和县建设工程监理有限公司", out)

    def test_biz_data_filled(self):
        out = _apply(self.P2)
        self.assertIn("【从业人员】", out)
        self.assertIn("【营业收入】", out)
        self.assertIn("【资产总额】", out)
        self.assertIn("【企业类型】", out)
        self.assertNotIn("62", out)
        self.assertNotIn("493.43", out)
        self.assertNotIn("134.59", out)
        self.assertNotIn("小型企业", out)

    def test_fixed_clause_untouched(self):
        out = _apply(self.P1)
        self.assertIn("《政府采购促进中小企业发展管理办法》", out)
        self.assertIn("财库〔2020〕46号", out)

    def test_scale_standards_not_hit(self):
        """2026-10-11 真实验证回归：各行业划型标准为固定条款，占位规则不得误伤
        「从业人员…人以下/及以上」「营业收入…万元以下/及以上」「资产总额…万元以下」。"""
        lines = [
            "（一）农、林、牧、渔业。营业收入20000 万元以下的为中小微型企业。",
            "（二）工业。从业人员1000人以下或营业收入40000万元以下的为中小微型企业。",
            "（三）建筑业。营业收入80000万元以下或资产总额80000万元以下的为中小微型企业。",
            "（四）批发业。从业人员200人以下或营业收入40000万元以下的为中小微型企业。",
            "（十六）其他未列明行业。从业人员300人以下的为中小微型企业。其中，"
            "从业人员100人及以上的为中型企业；从业人员10人及以上的为小型企业。",
        ]
        for line in lines:
            out = _apply(line)
            self.assertEqual(out, line, "划型标准固定条款被误伤: %s -> %s" % (line, out))
            self.assertNotIn("【从业人员】", out)
            self.assertNotIn("【营业收入】", out)
            self.assertNotIn("【资产总额】", out)

    def test_no_double_placeholder(self):
        """2026-10-11 回归：SME 占位后标注不得被重复替换（GLOBAL_PH 双重占位）。
        【项目名称】正文两处（声明段+清单行）各一次为正确语义，其余占位每类一次。"""
        out = _apply(self.P1 + self.P2)
        self.assertEqual(out.count("【项目名称】"), 2, out)
        for kw in ("【招标人名称】", "【企业名称】",
                   "【从业人员】", "【营业收入】", "【资产总额】", "【企业类型】"):
            self.assertEqual(out.count(kw), 1, "%s 出现 %d 次: %s" % (kw, out.count(kw), out))
        # 不得出现双重占位（如「【招标人名称】【招标人名称】」）
        for dbl in ("【招标人名称】【招标人名称】", "【项目名称】【项目名称】",
                    "【企业名称】【企业名称】"):
            self.assertNotIn(dbl, out)

    def test_date_filled(self):
        """已填样本落款日期（带前缀+具体值）→ 日期：【日期】。"""
        out = _apply("投标人（盖单位公章）：\n日期：2026年8月31日")
        self.assertIn("日期：【日期】", out)
        self.assertNotIn("2026年8月31日", out)


if __name__ == "__main__":
    unittest.main()
