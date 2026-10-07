# -*- coding: utf-8 -*-
"""
bidcraft · M1 素材库 —— 命名规范引擎（纯逻辑，无 I/O）

命名总则
--------
1. 结构：以 `_` 分隔若干「段」，常规形态为 `<关键字>_<日期>`。
2. 日期：统一 8 位 YYYYMMDD；无到期日写「长期」；日期不可考写「日期不详」。
3. 关键字：不得含 `_`，不得含 Windows 非法字符 / \\ : * ? " < > |，
   出现时统一替换为 `-`（保住段结构不被撑破）。
4. 多页：文件名末尾追加 `_P0/_P1/...`（P0 为首页），按上传顺序排列。

设计原则：本模块只做「字符串 → 规范名」与「规范名 → 结构化字段」的确定性换算，
不碰文件系统，便于单元测试与跨平台复用。
"""

import os
import re
from datetime import date, datetime

# 常量 / 规则表 / NamingError —— 拆分至 naming_base（文件行数治理），此处 re-export
from .naming_base import *          # noqa: E402,F401,F403

__all__ = [
    "NamingError",
    "LONG_TERM",
    "UNKNOWN_DATE",
    "CATEGORY_META",
    "DEFAULT_SUBTYPE",
    "ILLEGAL_CHARS",
    "list_categories",
    "list_subtypes",
    "get_rule",
    "sanitize_keyword",
    "normalize_date",
    "build_name",
    "build_project_folder",
    "split_ext",
    "split_page",
    "validate",
    "validate_project_folder",
    "extract_date",
    "extract_dates",
    "classify",
    "guess_subtype",
    "parse_name",
    "PAGE_SUFFIX_RE",
]

# --------------------------------------------------------------------------
# 规则查询
# --------------------------------------------------------------------------
def list_categories():
    return list(CATEGORY_META.keys())


def list_subtypes(category):
    return [sub for (cat, sub) in RULES if cat == category]


def get_rule(category, subtype):
    if subtype is None:
        subtype = DEFAULT_SUBTYPE.get(category)
    rule = RULES.get((category, subtype))
    if rule is None:
        raise NamingError(
            "未定义的大类/子类：%s/%s（已知子类：%s）"
            % (category, subtype, "、".join(list_subtypes(category)) or "无")
        )
    return rule


def rule_hint(category, subtype):
    return get_rule(category, subtype).get("hint", "")


# --------------------------------------------------------------------------
# 原子清洗 / 归一
# --------------------------------------------------------------------------
def sanitize_keyword(value):
    """关键字清洗：去除 Windows 非法字符与分隔符 `_`，统一用 `-` 连接。"""
    if value is None:
        return ""
    s = str(value).strip()
    for ch in ILLEGAL_CHARS:
        s = s.replace(ch, "-")
    s = s.replace("_", "-")
    s = re.sub(r"[\r\n\t]+", " ", s)
    s = re.sub(r"\s{2,}", " ", s).strip()
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s


def normalize_date(value):
    """日期归一为 8 位 YYYYMMDD，或保留「长期 / 日期不详」。"""
    if value is None or (isinstance(value, str) and not value.strip()):
        raise NamingError("缺少日期字段（应填 8 位到期日，或「长期」/「日期不详」）")
    if isinstance(value, (datetime, date)):
        return value.strftime("%Y%m%d")

    s = str(value).strip()
    if s in (LONG_TERM, "长期有效", "无固定期限", "永久", "无期限"):
        return LONG_TERM
    if s in (UNKNOWN_DATE, "不详", "未知", "无"):
        return UNKNOWN_DATE

    digits = re.sub(r"\D", "", s)
    if len(digits) == 8:
        return digits
    if len(digits) == 6:  # YYYYMM → 视为该月首日
        return digits + "01"
    raise NamingError("日期无法归一化：%r（请提供 8 位 YYYYMMDD，或「长期」/「日期不详」）" % value)


# --------------------------------------------------------------------------
# 文件名拆解
# --------------------------------------------------------------------------
def split_ext(filename):
    """拆分 (主体名, 扩展名小写含点)。仅在末段像扩展名时才当作扩展名。"""
    base = os.path.basename(str(filename))
    stem, dot, tail = base.rpartition(".")
    if dot and tail and EXT_RE.match(tail) and "_" not in tail:
        return stem, "." + tail.lower()
    return base, ""


def split_page(stem):
    """拆出多页序号：(基础名, page:int|None)。"""
    m = PAGE_SUFFIX_RE.search(stem)
    if m:
        return stem[: m.start()], int(m.group(1))
    return stem, None


# --------------------------------------------------------------------------
# 构建/校验/解析 与 日期抽取/智能分类 —— 拆分至 naming_build / naming_classify
# （文件行数治理；此处 re-export 保持对外接口与 __all__ 兼容）
# --------------------------------------------------------------------------
from .naming_build import *        # noqa: E402,F401,F403
from .naming_classify import *     # noqa: E402,F401,F403
