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
# 常量
# --------------------------------------------------------------------------
ILLEGAL_CHARS = '/\\:*?"<>|'
LONG_TERM = "长期"
UNKNOWN_DATE = "日期不详"

DATE_TOKEN_RE_STR = r"(?:\d{8}|长期|日期不详)"
DATE_TOKEN_RE = re.compile(r"^(?:\d{8}|长期|日期不详)$")
PAGE_SUFFIX_RE = re.compile(r"_P(\d+)$")
EXT_RE = re.compile(r"^[A-Za-z0-9]{1,5}$")

# 段类型
CONST, KW, KW_OPT, DATE, ENUM = "const", "kw", "kw_opt", "date", "enum"


def _c(literal):
    return (CONST, literal)


def _enum(*options):
    return (ENUM, tuple(options))


C = _c
E = _enum

# --------------------------------------------------------------------------
# 规则表
# --------------------------------------------------------------------------
CATEGORY_META = {
    "资质": {"date_label": "到期日", "kind": "flat"},
    "人员": {"date_label": "到期日", "kind": "person"},
    "业绩": {"date_label": "签订日期", "kind": "project"},
    "荣誉": {"date_label": "颁发日期", "kind": "flat"},
    "财务": {"date_label": "到期日", "kind": "flat"},
}

# (大类, 子类) -> {"segs": [...], "ext": [...] 可选, "hint": 字段提示}
RULES = {
    # ---- 资质 ----
    ("资质", "营业执照"): {
        "segs": [C("营业执照"), (KW_OPT,), (DATE,)],
        "ext": [".png", ".jpg", ".jpeg", ".pdf"],
        "hint": "营业执照[_正副本]_到期日",
    },
    ("资质", "资质证书"): {"segs": [(KW,), (DATE,)], "hint": "资质证书关键字_到期日"},
    ("资质", "体系认证"): {"segs": [(KW,), (DATE,)], "hint": "证书关键字_到期日"},
    ("资质", "信用证书"): {"segs": [(KW,), (DATE,)], "hint": "证书关键字_到期日"},
    ("资质", "其他"): {"segs": [(KW,), (DATE,)], "hint": "关键字_到期日"},

    # ---- 人员 ----
    ("人员", "注册证书"): {
        "segs": [(KW,), (DATE,), (DATE,)],
        "hint": "注册证书名关键字_注册有效期_使用有效期到期日",
    },
    ("人员", "岗位证书"): {"segs": [(KW,), (DATE,)], "hint": "岗位证书关键字_到期日"},
    ("人员", "职称证书"): {"segs": [(KW,), (KW,)], "hint": "职称等级关键字_专业"},
    ("人员", "身份证"): {
        "segs": [C("身份证"), E("国徽面", "人像面"), (DATE,)],
        "hint": "身份证_国徽面|人像面_到期日",
    },
    ("人员", "毕业证"): {"segs": [C("毕业证"), (KW,)], "hint": "毕业证_专业"},
    ("人员", "个人荣誉"): {"segs": [(KW,), (DATE,)], "hint": "荣誉证书名关键字_颁发日期"},
    ("人员", "简历"): {"segs": [C("简历"), (DATE,)], "hint": "简历_上传日期"},
    ("人员", "退休证"): {"segs": [C("退休证"), (KW_OPT,), (DATE,)], "hint": "退休证[_关键字]_长期"},
    ("人员", "返聘协议"): {"segs": [C("返聘协议"), (KW_OPT,), (DATE,)], "hint": "返聘协议[_关键字]_到期日"},
    ("人员", "其他"): {"segs": [(KW,), (DATE,)], "hint": "关键字_到期日"},

    # ---- 业绩（文件层；项目文件夹另见 build_project_folder）----
    ("业绩", "业绩文件"): {"segs": [(KW,)], "hint": "文档类型_P0/P1"},

    # ---- 荣誉 ----
    ("荣誉", "荣誉证书"): {"segs": [(KW,), (DATE,)], "hint": "证书名关键字_颁发日期"},

    # ---- 财务 ----
    ("财务", "财务证照"): {"segs": [(KW,), (DATE,)], "hint": "证书名关键字_到期日"},
}

DEFAULT_SUBTYPE = {
    "资质": "资质证书",
    "人员": "其他",
    "业绩": "业绩文件",
    "荣誉": "荣誉证书",
    "财务": "财务证照",
}

# 业绩项目文件夹：项目全名关键字_签订日期_总监
PROJECT_FOLDER_SEGS = [(KW,), (DATE,), (KW,)]


class NamingError(ValueError):
    """命名规则无法满足（缺字段 / 非法取值）时抛出。"""


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
                if kw:
                    parts.append(kw)
        elif kind == DATE:
            if not dts:
                raise NamingError("缺少日期字段（该位置需要一个日期）")
            parts.append(normalize_date(dts.pop(0)))
        elif kind == ENUM:
            if not kws:
                raise NamingError("缺少取值字段（可选：%s）" % "、".join(seg[1]))
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
            elif kind == DATE:
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


# --------------------------------------------------------------------------
# 日期抽取 / 智能分类（供归档建议使用）
# --------------------------------------------------------------------------
def extract_date(text):
    """从任意文本中抽取第一个日期归一值；支持 长期 / 日期不详。"""
    if text is None:
        return None
    s = str(text)
    if LONG_TERM in s or "长期有效" in s:
        return LONG_TERM
    if UNKNOWN_DATE in s or "不详" in s:
        return UNKNOWN_DATE
    m = re.search(r"(?<!\d)(\d{8})(?!\d)", s)
    if m:
        return m.group(1)
    m = re.search(r"(?<!\d)(\d{4})\s*[-./年]\s*(\d{1,2})\s*[-./月]\s*(\d{1,2})", s)
    if m:
        try:
            return "%04d%02d%02d" % (int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    return None


def extract_dates(text):
    """抽取全部日期归一值（保序、去重）。"""
    if text is None:
        return []
    s = str(text)
    found = re.findall(r"(?<!\d)(\d{8})(?!\d)", s)
    if not found:
        m = re.search(r"(?<!\d)(\d{4})\s*[-./年]\s*(\d{1,2})\s*[-./月]\s*(\d{1,2})", s)
        if m:
            found = ["%04d%02d%02d" % (int(m.group(1)), int(m.group(2)), int(m.group(3)))]
    out = []
    for f in found:
        if f not in out:
            out.append(f)
    return out


# 关键字 → (大类, 子类) 的启发式映射（顺序即优先级）
_HEURISTICS = [
    (("营业执照",), ("资质", "营业执照")),
    (("开户许可证", "基本户", "银行开户"), ("财务", "财务证照")),
    (("ISO", "质量管理体系", "环境管理体系", "职业健康", "体系认证", "认证证书"), ("资质", "体系认证")),
    (("信用", "AAA", "守合同", "重信用", "诚信"), ("资质", "信用证书")),
    (("身份证",), ("人员", "身份证")),
    (("毕业证", "学位证", "学历证书"), ("人员", "毕业证")),
    (("简历",), ("人员", "简历")),
    (("退休",), ("人员", "退休证")),
    (("返聘",), ("人员", "返聘协议")),
    (("注册", "建造师", "监理工程师", "造价工程师", "注册证", "执业"), ("人员", "注册证书")),
    (("岗位", "上岗", "培训", "继续教育"), ("人员", "岗位证书")),
    (("职称", "高级工程师", "中级工程师", "助理工程师", "工程师"), ("人员", "职称证书")),
    (("监理合同", "施工合同", "合同", "协议"), ("业绩", "业绩文件")),
    (("竣工", "验收", "备案", "中标通知书", "结算"), ("业绩", "业绩文件")),
    (("优秀", "先进", "示范工程", "标准化工地", "荣誉", "获奖", "奖状"), ("荣誉", "荣誉证书")),
    (("资质", "等级证书", "甲级", "乙级", "丙级"), ("资质", "资质证书")),
]


def classify(filename):
    """
    按文件名启发式判断归属。
    返回 (大类, 子类, 命中的关键字)；判不出返回 (None, None, None)。
    """
    stem, _ = split_ext(filename)
    text = stem
    for keys, target in _HEURISTICS:
        for k in keys:
            if k in text:
                return target[0], target[1], k
    return None, None, None
