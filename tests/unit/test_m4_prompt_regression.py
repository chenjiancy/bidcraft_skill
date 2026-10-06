# -*- coding: utf-8 -*-
"""L1 单元测试：M4 通道B 提示词回归验证（建议④/⑤落实）。

提示词（references/M4-招标文件解析-提示词.md）是通道B 解析的硬性约定。
本测试把提示词的必守要素固化为断言：9 模块 id、铁律、v1.1 分段精读流程、
JSON 骨架、版本记录。提示词任何削弱（误删铁律/模块/流程）都会在此回归失败。
"""
import os
import sys
import unittest

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_PROMPT = os.path.join(_REPO, "references", "M4-招标文件解析-提示词.md")

# 铁律关键词（缺一即回归失败；提示词是通道B 生命线）
_IRON_RULES = [
    "响应文件格式_<项目名>.txt",          # 铁律5：格式全文一字不改
    "一个字都不能更改",
    "合同内容一律不解析",                 # 铁律4
    "双通道差异",                        # 铁律6
    "原文未提供",                        # 铁律2
    "不解析登记方式",                    # 模块2 排除项
    "不解析信用黑名单",                  # 模块8 排除项
    "报价金额由用户提供",                # 铁律3
    "禁止编造页码",
]
# v1.1 分段精读流程关键词
_SEGMENT_FLOW = [
    "分段精读执行流程",
    "模块归属表",
    "跨段汇总与交叉查重",
    "解析完整度声明",
    "严禁一次性整段通读",
]


def _prompt_text():
    if not os.path.exists(_PROMPT):
        raise FileNotFoundError("提示词文件不存在：%s" % _PROMPT)
    with open(_PROMPT, encoding="utf-8") as f:
        return f.read()


class TestPromptCore(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = _prompt_text()

    def test_prompt_file_exists(self):
        self.assertTrue(os.path.exists(_PROMPT))

    def test_version_header(self):
        self.assertIn("v1.1", self.text.splitlines()[0], "提示词头部版本须为 v1.1")
        self.assertIn("| v1.1 |", self.text, "版本记录表须含 v1.1 行")

    def test_nine_modules_all_present(self):
        for mid in ("basic", "qualification", "staff", "project_overview",
                    "scoring", "pricing", "submission", "reject", "pending"):
            self.assertIn(mid, self.text, "提示词缺少模块 %s（9 模块框架回归）" % mid)

    def test_json_skeleton(self):
        self.assertIn("投标要点 JSON 骨架", self.text)
        self.assertIn('"diffs"', self.text)

    def test_iron_rules_all_present(self):
        for kw in _IRON_RULES:
            self.assertIn(kw, self.text, "提示词缺少铁律要素：%s" % kw)


class TestPromptSegmentFlow(unittest.TestCase):
    """v1.1 分段精读执行流程（建议⑤：长文档分段解析）。"""

    @classmethod
    def setUpClass(cls):
        cls.text = _prompt_text()

    def test_segment_flow_present(self):
        for kw in _SEGMENT_FLOW:
            self.assertIn(kw, self.text, "提示词缺少 v1.1 分段精读要素：%s" % kw)


if __name__ == "__main__":
    unittest.main()
