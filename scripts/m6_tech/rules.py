# -*- coding: utf-8 -*-
"""
bidcraft · M6 技术标制作 —— 纯逻辑层门面（F1–F11，无 I/O）

业务实现按 500 行红线拆分（`规则对齐-M6-20261021.md` S4）：
  rules_chapters.py  F1/F2 章节树校验、F3 覆盖矩阵、F11 排版预设
  rules_check.py     F4 篇幅、F5 暗标敏感词、F6 一致性、F7 占位、
                     F8 状态机、F9 自述块、F10 双通道差异
  rules_base.py      契约常量与工具

T4（存储层）/ T5（CLI）一律只 import 本门面，不直接依赖子模块。
返回约定见各子模块文档字符串；本层不读写文件、不调用 agent。
"""
from .rules_base import (
    SCHEMA_ID, BID_MODES, STATUSES, STATUS_FLOW, GATES, DEPENDS_ENUM,
    DEFAULT_LAYOUT, LAYOUT_ALIAS_KEYS, COVER_RATIO, FONT_ALIASES,
    IMAGE_RATIO_ALIASES, IMAGE_RULE_ALIASES, IMAGE_LAYOUT_ALIASES,
)
from .rules_chapters import (
    validate_chapters_draft, validate_chapters_final, build_coverage, validate_layout,
)
from .rules_check import (
    count_chars, estimate_pages, judge_pages, scan_sensitive, check_consistency,
    scan_placeholders, validate_transition, next_states, parse_selfcheck_block,
    strip_selfcheck_block, compare_dual,
)

__all__ = [
    # 常量
    "SCHEMA_ID", "BID_MODES", "STATUSES", "STATUS_FLOW", "GATES", "DEPENDS_ENUM",
    "DEFAULT_LAYOUT", "LAYOUT_ALIAS_KEYS", "COVER_RATIO", "FONT_ALIASES",
    "IMAGE_RATIO_ALIASES", "IMAGE_RULE_ALIASES", "IMAGE_LAYOUT_ALIASES",
    # F1–F3 / F11
    "validate_chapters_draft", "validate_chapters_final", "build_coverage", "validate_layout",
    # F4–F10
    "count_chars", "estimate_pages", "judge_pages", "scan_sensitive", "check_consistency",
    "scan_placeholders", "validate_transition", "next_states", "parse_selfcheck_block",
    "strip_selfcheck_block", "compare_dual",
]
