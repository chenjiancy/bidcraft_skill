# -*- coding: utf-8 -*-
"""
bidcraft · M1 素材库 —— 命名规范引擎·构建/校验/解析（结构化字段 ↔ 规范名）。

从 naming.py 拆分（文件行数治理）；由 naming.py 在文件末尾 re-export，
对外接口（nm.build_name / nm.validate / nm.parse_name / ...）保持不变。
"""
import os
import re

from .naming_base import (CONST, DATE, DATE_OPT, DATE_TOKEN_RE, DATE_TOKEN_RE_STR, ENUM,
                          KW, KW_OPT, NamingError, YEAR, PROJECT_FOLDER_SEGS)
from .naming import (get_rule, list_subtypes, normalize_date, sanitize_keyword,
                     split_ext, split_page)

__all__ = ["build_name", "build_project_folder", "validate",
           "validate_project_folder", "guess_subtype", "parse_name",
           "_seg_atom", "_segs_to_regex", "_fill"]


# --------------------------------------------------------------------------
# 构建（结构化字段 → 规范名）
# --------------------------------------------------------------------------
def _seg_atom(seg, leading=True):
    kind = seg[0]
    prefix = "_" if leading else ""
    if kind == CONST:
        return prefix + re.escape(seg[1])
    if kind == KW:
        return prefix + r"[^_]+"
    if kind == KW_OPT:
        return r"(?:_[^_]+)?"
    if kind == DATE:
        return prefix + DATE_TOKEN_RE_STR
    if kind == DATE_OPT:
        return r"(?:_" + DATE_TOKEN_RE_STR + r")?"
    if kind == YEAR:
        return prefix + r"\d{4}"
    if kind == ENUM:
        return prefix + "(?:" + "|".join(re.escape(o) for o in seg[1]) + ")"
    raise NamingError("未知段类型：%r" % (seg,))


def _segs_to_regex(segs, allow_page=True):
    if not segs:
        return r"^$"
    body = _seg_atom(segs[0], leading=False) + "".join(_seg_atom(s) for s in segs[1:])
    if allow_page:
        body += r"(?:_P\d+)?"
    return "^" + body + "$"


def _fill(segs, keywords, dates):
    """按段规则消费 keywords / dates，返回段文本列表。"""
    kws = list(keywords or [])
    dts = list(dates or [])
    parts = []
    for seg in segs:
        kind = seg[0]
        if kind == CONST:
            parts.append(seg[1])
        elif kind == KW:
            if not kws:
                raise NamingError("缺少关键字字段（该位置需要一个关键字）")
            kw = sanitize_keyword(kws.pop(0))
            if not kw:
                raise NamingError("关键字清洗后为空（可能全是非法字符）")
            parts.append(kw)
        elif kind == KW_OPT:
            if kws:
                kw = sanitize_keyword(kws.pop(0))
                # 与固定段(CONST)或已消费关键字去重：如 退休证 + keywords=['退休证'] → 只保留一个"退休证"
                if kw and kw not in parts:
                    parts.append(kw)
        elif kind == DATE:
            if not dts:
                raise NamingError("缺少日期字段（该位置需要一个日期）")
            parts.append(normalize_date(dts.pop(0)))
        elif kind == DATE_OPT:
            if dts:
                parts.append(normalize_date(dts.pop(0)))
        elif kind == YEAR:
            if not dts:
                raise NamingError("缺少日期字段（该位置需要年度）")
            parts.append(str(dts.pop(0))[:4])
        elif kind == ENUM:
            if not kws:
                # 未提供关键字时取默认枚举项（如 组织架构 → 组织机构图）
                parts.append(seg[1][0])
            else:
                v = str(kws.pop(0)).strip()
                if v not in seg[1]:
                    raise NamingError("取值非法：%r（应为 %s）" % (v, "、".join(seg[1])))
                parts.append(v)
        else:
            raise NamingError("未知段类型：%r" % (seg,))
    return parts


def build_name(category, subtype=None, keywords=None, dates=None, page=None, ext=None):
    """
    生成规范文件名。

    例：
      build_name("资质", "营业执照", dates=["20281231"], ext=".jpg")
        -> "营业执照_20281231.jpg"
      build_name("人员", "身份证", keywords=["人像面"], dates=["20350101"])
        -> "身份证_人像面_20350101"
      build_name("人员", "注册证书", keywords=["监理工程师"], dates=["20270101","20280101"])
        -> "监理工程师_20270101_20280101"
      build_name("业绩", "业绩文件", keywords=["监理合同"], page=0)
        -> "监理合同_P0"
    """
    rule = get_rule(category, subtype)
    name = "_".join(_fill(rule["segs"], keywords, dates))
    if page is not None:
        name += "_P%d" % int(page)
    if ext:
        name += ext if str(ext).startswith(".") else "." + str(ext)
    return name


def build_project_folder(project_kw, sign_date, director=None):
    """业绩项目文件夹名：项目全名关键字_签订日期_总监（无总监则填「无总监」）。"""
    kws = [project_kw, director if director else "无总监"]
    return "_".join(_fill(PROJECT_FOLDER_SEGS, kws, [sign_date]))


# --------------------------------------------------------------------------
# 校验（规范名 → 是否合规）
# --------------------------------------------------------------------------
def validate(category, subtype=None, filename=""):
    """返回 (是否合规, 问题列表)。仅扩展名不符时不算致命（按“保持原格式”不强制转换）。"""
    rule = get_rule(category, subtype)
    stem, ext = split_ext(filename)
    issues = []
    if not re.match(_segs_to_regex(rule["segs"]), stem):
        issues.append(
            "主体名不符合规范，期望：%s（当前：%s）" % (rule.get("hint", ""), stem)
        )
    allowed_ext = rule.get("ext")
    if allowed_ext and ext and ext not in allowed_ext:
        issues.append(
            "扩展名 %s 不在期望范围 %s（仅提示，按规范不强制转换）" % (ext, "/".join(allowed_ext))
        )
    fatal = [i for i in issues if not i.endswith("（仅提示，按规范不强制转换）")]
    return (len(fatal) == 0), issues


def validate_project_folder(folder_name):
    stem, _ = split_ext(folder_name)
    if re.match(_segs_to_regex(PROJECT_FOLDER_SEGS, allow_page=False), stem):
        return True, []
    return False, ["项目文件夹不符合规范，期望：项目全名关键字_签订日期_总监（当前：%s）" % folder_name]


def guess_subtype(category, filename):
    """在给定大类内，猜出最匹配的子类；不匹配返回 None。"""
    stem, _ = split_ext(filename)
    for sub in list_subtypes(category):
        try:
            if re.match(_segs_to_regex(get_rule(category, sub)["segs"]), stem):
                return sub
        except NamingError:
            continue
    return None


def parse_name(category, subtype, filename):
    """
    反向解析规范名 → 结构化字段（{keywords, dates, page, ext, ok, issues}）。
    解析失败时尽量返回其中可抽出的部分，便于巡检报告使用。
    """
    stem, ext = split_ext(filename)
    base, page = split_page(stem)
    rule = get_rule(category, subtype)
    ok, issues = validate(category, subtype, filename)
    parts = base.split("_") if base else []

    keywords, dates = [], []
    if ok:
        segs = rule["segs"]
        idx = 0
        for seg in segs:
            kind = seg[0]
            if kind == CONST:
                idx += 1  # 常量段占位
            elif kind == KW_OPT:
                # 可选关键字段：若该位置是日期 token（说明未填关键字），则留给 DATE 段消费
                if idx < len(parts) and not DATE_TOKEN_RE.match(parts[idx]):
                    keywords.append(parts[idx])
                    idx += 1
            elif kind in (KW, ENUM):
                if idx < len(parts):
                    keywords.append(parts[idx])
                    idx += 1
            elif kind in (DATE, DATE_OPT):
                if idx < len(parts):
                    dates.append(parts[idx])
                    idx += 1
            elif kind == YEAR:
                if idx < len(parts):
                    dates.append(parts[idx])
                    idx += 1
    else:
        # 宽松兜底：把 8 位数字段当日期，其余当关键字
        for p in parts:
            if DATE_TOKEN_RE.match(p):
                dates.append(p)
            else:
                keywords.append(p)

    return {
        "ok": ok,
        "issues": issues,
        "keywords": keywords,
        "dates": dates,
        "date": dates[0] if dates else None,
        "page": page,
        "ext": ext,
        "stem": base,
    }
