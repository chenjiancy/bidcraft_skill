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


if __name__ == "__main__":
    unittest.main()
