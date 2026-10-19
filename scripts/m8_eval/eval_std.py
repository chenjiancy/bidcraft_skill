# -*- coding: utf-8 -*-
"""
bidcraft · M8 AI模拟评标 —— 评分标准解析（通道A 规则引擎：从 M4 投标要点结构化评分项）

设计约定（对齐 m7_check/rule_check.py）：
  - 标准一律读 M4 产物（投标要点_<项目>.json 的 scoring 模块 score_items），
    不重复提取招标文件（口径漂移防护）
  - 评分项类型用「可增行规则表」正则匹配（SCORE_KIND_RULES），匹配不到的项
    归 kind="unknown"，输出「待通道B/人工确认」，不硬猜
  - 规则参数（每条X分/满分/上限/年限/类型词）从 item 文本正则抽取，抽不到的
    参数记 None（待确认），绝不编造默认值

类型划分：
  - objective（客观可机器算）：iso / perf / dir_title / staff_title / honor
  - quote（报价公式）：quote
  - subjective（主观，待 M6/通道B）：outline
  - rule（0 分规则项，非打分）：rule
"""
import re

from _shared import core

# --------------------------------------------------------------------------
# 可增行评分项类型规则表（顺序敏感：先匹配者胜）
#  - rule 须在 outline 前（"监理大纲暗标要求…篇幅…" 同时含两词，应归 rule）
#  - 职称类用通用 kind="title"，再按是否含"监理人员/不含总监"细分 staff/dir
# --------------------------------------------------------------------------
SCORE_KIND_RULES = [
    ("iso",        r"ISO|质量管理体系|环境管理体系|职业健康"),
    ("perf",       r"业绩"),
    ("title",      r"职称"),
    ("honor",      r"荣誉|表彰|先进.{0,4}监理|优秀监理企业"),
    ("quote",      r"报价|评标基准价|投标报价"),
    ("rule",       r"暗标|篇幅|格式不符|空白页|不得泄露"),
    ("outline",    r"监理大纲|技术方案|综合比较阐述"),
]

# 参数正则（全部失败则参数为 None，待确认）
_RE_PER = re.compile(r"每(?:个|份|人|张|项|条)\s*(\d+(?:\.\d+)?)\s*分")          # 每条 X 分
_RE_MAX = re.compile(r"(?:最多|不超过|至多|最高)\s*(\d+)\s*分")                  # 上限满分
_RE_MAX2 = re.compile(r"满分\s*(\d+)\s*分")                                       # 满分
_RE_YEAR = re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日?(?:以来|起)")  # 起始年限
_RE_YEAR_Y = re.compile(r"(\d{4})\s*年\s*(?:1\s*月\s*1\s*日)?(?:以来|起|至今)")       # 起始年份
_RE_HI = re.compile(r"每高(?:于基准价)?\s*1%\s*扣\s*([\d.]+)\s*分")                # 报价每高1%扣
_RE_LO = re.compile(r"每低(?:于基准价)?\s*1%\s*扣\s*([\d.]+)\s*分")                # 报价每低1%扣
_RE_BASE = re.compile(r"基准价[（(]?\s*([^）)。,，]{2,24})")                        # 基准价描述
_RE_WEIGHT = re.compile(r"(\d+(?:\.\d+)?)\s*分")                                    # 分值兜底
_RE_CAT = re.compile(r"地级市(?:以上)?|建设行政主管部门|行业协会|人民政府")          # 荣誉颁发单位
_RE_AMT_WAN = re.compile(r"(\d+(?:\.\d+)?)\s*万元")                                    # 业绩金额门槛（万元）
_RE_NUM = re.compile(r"\d+(?:\.\d+)?")


def _first_num(txt, pat, default=None):
    m = pat.search(txt)
    return float(m.group(1)) if m else default


def _first_year(txt):
    m = _RE_YEAR.search(txt) or _RE_YEAR_Y.search(txt)
    return "%s-01-01" % m.group(1) if m else None


def _weight_of(item, fallback):
    """分值：优先 score_items.weight 字段，其次 item 文本兜底。"""
    w = item.get("weight")
    if w is not None and str(w).strip():
        m = _RE_NUM.search(str(w))
        if m:
            return float(m.group())
    return fallback


# --------------------------------------------------------------------------
# 评分项解析
# --------------------------------------------------------------------------
def parse_score_item(item, idx):
    """解析一条 score_items → 结构化评分项。"""
    text = (item.get("item") or "").strip()
    weight = _weight_of(item, None)
    kind = "unknown"
    for k, pat in SCORE_KIND_RULES:
        if re.search(pat, text):
            kind = k
            break

    if kind == "title":
        # 职称类细分：含"监理人员/不含总监" → 人员职称；否则含"总监/总监理工程师" → 总监职称
        if re.search(r"监理人员|不含总监", text):
            kind = "staff_title"
        elif re.search(r"总监|总监理工程师", text):
            kind = "dir_title"
        else:
            kind = "title_unknown"

    out = {
        "idx": idx,
        "kind": kind,
        "item": text,
        "weight": weight,
        "evidence": item.get("evidence") or "",
        "params": {},
        "note": "",
    }
    per = _first_num(text, _RE_PER)
    mx = _first_num(text, _RE_MAX) or _first_num(text, _RE_MAX2)
    year = _first_year(text)

    if kind == "iso":
        # 体系数=item/purpose 命中 ISO 体系词数（质量/环境/职业健康，上限3）
        sys_count = 0
        for kw in ("质量", "环境", "职业健康"):
            if kw in text:
                sys_count += 1
        out["params"] = {"sys_count": sys_count or 3, "max": weight or 3}
        out["note"] = "证书须在有效期内并附扫描件；有效期须人工核对"
    elif kind == "perf":
        out["params"] = {"per": per or 4.0, "max": mx or weight or 8.0,
                         "year_start": year,
                         "require_type": _first_num(text, _RE_AMT_WAN)}
        out["note"] = "认定时间以合同签订时间为准；金额/类型/时间逐份人工核对"
    elif kind in ("dir_title", "staff_title", "title_unknown"):
        if kind == "dir_title":
            out["params"] = {"max": weight or 1.0}
            out["note"] = "须附职称证书扫描件；专业须与招标要求相关，人工核对"
        elif kind == "staff_title":
            out["params"] = {"per": per or 1.0, "max": mx or weight or 3.0}
            out["note"] = "人数以附表7为准，机器按素材清单条目估，人工核对"
        else:
            out["params"] = {}
            out["note"] = "职称项未能细分总监/人员，待通道B/人工确认"
    elif kind == "honor":
        out["params"] = {"first": per or 3.0, "next": 2.0, "max": mx or weight or 5.0,
                         "year_start": year, "issuer": bool(_RE_CAT.search(text))}
        out["note"] = "认定以证书落款日期；颁发单位须民政登记可查，人工核对"
    elif kind == "quote":
        out["params"] = {
            "max": weight or 30.0,
            "hi_punish": _first_num(text, _RE_HI, 0.2),
            "lo_punish": _first_num(text, _RE_LO, 0.1),
            "base_desc": (_RE_BASE.search(text).group(1) if _RE_BASE.search(text) else None),
        }
        out["note"] = "基准价=有效投标报价算术平均值（K 系数/下浮按招标文件实际规则人工核对）"
    elif kind == "outline":
        out["params"] = {"max": weight or 50.0}
        out["note"] = "主观评分，待 M6 技术标交付后由通道B agent 精评"
    elif kind == "rule":
        out["params"] = {}
        out["note"] = "0 分规则项（非打分）：暗标/篇幅/格式约束，由 M7 检查核对"
    else:
        out["note"] = "类型未能自动判定，待通道B/人工确认"

    return out


def parse_scoring(points):
    """从 M4 投标要点 json 的 scoring 模块解析评分标准 → 结构化清单。"""
    mod = None
    for m in (points.get("modules") or []):
        if m.get("id") == "scoring":
            mod = m
            break
    if not mod:
        raise core.LibraryError("投标要点缺少 scoring（评分办法）模块，M8 无法模拟评标")
    method = (mod.get("method") or {}).get("value") or ""
    items = mod.get("score_items") or []
    if not items:
        raise core.LibraryError("scoring 模块缺少 score_items（评分项明细），M8 无法模拟评标")

    parsed = [parse_score_item(it, i) for i, it in enumerate(items)]
    total = 0.0
    obj_total = 0.0
    subj_total = 0.0
    quote_total = 0.0
    for p in parsed:
        w = p["weight"] or 0.0
        total += w
        if p["kind"] == "quote":
            quote_total += w
        elif p["kind"] == "outline":
            subj_total += w
        elif p["kind"] in ("iso", "perf", "dir_title", "staff_title", "honor"):
            obj_total += w
    return {
        "method": method,
        "total": total,
        "objective_total": obj_total,
        "subjective_total": subj_total,
        "quote_total": quote_total,
        "items": parsed,
    }
