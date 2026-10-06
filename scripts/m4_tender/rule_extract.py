# -*- coding: utf-8 -*-
"""
bidcraft · M4 招标文件解析 —— 通道A 文档解析规则引擎（纯逻辑，无 I/O）

v2.1 双通道解析 · 通道A：用确定性正则规则从招标原文抽取「关键事实字段」，
与通道B（agent 语义解析 9 模块）互补。适用格式固定、表述规范的确定性要素；
开放性要素（评分细节、废标红线语义等）留给通道B。

设计约定：
  - RULES 为可增行表：id / label（通道B 对标签，比对用）/ module（归属 9 模块）/
    pattern / multi（是否多值）
  - 每条命中带原文行号锚点与上下文（evidence），供回看原文
  - 只做高置信度抽取；拿不准的字段不写规则（避免误报污染双通道差异）
"""

import re

# --------------------------------------------------------------------------
# 规则表（可增行：id, label, module, pattern, multi）
#   id      —— 机读字段名（文档解析 JSON 的 key）
#   label   —— 人读标签 = 通道B 投标要点中同字段的标签（双通道比对对齐用）
#   module  —— 归属 9 模块 id（POINTS_MODULES）
#   pattern —— 确定性正则（第一捕获组为值）
#   multi   —— True=多值字段（返回数组），False=单值（返回首中）
# --------------------------------------------------------------------------
RULES = [
    # -- 模块 1 项目基本信息 --
    {"id": "project_no", "label": "项目编号", "module": "basic",
     "pattern": re.compile(r"项目编号[:：\s]*([A-Za-z0-9][A-Za-z0-9\-—]{3,})")},
    {"id": "budget", "label": "最高投标限价", "module": "basic",
     "pattern": re.compile(r"最高投标限价[:：\s]*([\d.]+)\s*万元")},
    {"id": "bid_deadline", "label": "投标截止时间", "module": "basic",
     "pattern": re.compile(r"(?:投标截止时间|投标截止日期|递交(?:响应|投标)文件(?:提交)?截止(?:时间)?|响应文件(?:提交|递交)截止(?:时间)?)[:：\s]*(\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日(?:\s*\d{1,2}\s*[:：]\s*\d{2})?|[^，。；\n]{1,12})")},
    {"id": "open_time", "label": "开标时间", "module": "basic",
     "pattern": re.compile(r"(?:开标时间|开标日期)[:：\s]*(\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日(?:\s*\d{1,2}\s*[:：]\s*\d{2})?|[^，。；\n]{1,12})")},
    {"id": "service_period", "label": "服务期", "module": "basic",
     "pattern": re.compile(r"服务期[:：\s]*([^\n，。;；]{2,60})")},
    {"id": "valid_period", "label": "投标有效期", "module": "basic",
     "pattern": re.compile(r"投标有效期[:：\s]*([^\n，。;；]{2,30})")},
    {"id": "deposit", "label": "投标保证金", "module": "basic",
     "pattern": re.compile(r"(?:投标保证金|投标诚信保证金)[:：\s]*([^\n，。;；]{2,30})")},
    {"id": "joint_venture", "label": "联合体", "module": "basic",
     "pattern": re.compile(r"(接受|不接受|允许|不允许)[^。\n]{0,8}联合体")},
    {"id": "electronic", "label": "电子标或纸质标", "module": "basic",
     "pattern": re.compile(r"(电子投标|电子招投标|纸质投标|现场递交|邮寄递交|U盘|光盘|全流程电子化)")},
    {"id": "real_name", "label": "实名制或非实名制", "module": "basic",
     "pattern": re.compile(r"(实名制|身份证原件|授权委托书原件)")},
    # -- 模块 2 资格条件 --
    {"id": "qualification", "label": "资质要求", "module": "qualification",
     "pattern": re.compile(r"具有([\u4e00-\u9fa5（）]{2,16}资质)")},
    # -- 模块 3 人员配备 --
    {"id": "staff_count", "label": "人员数量", "module": "staff", "multi": True,
     "pattern": re.compile(r"((?:总监理工程师|专业监理工程师|监理员)[^。\n]{0,10}?\d+\s*名)")},
    # -- 模块 5 评标办法（v2.4 扩展：评分分值抽取 + 合计=100 校验）--
    {"id": "score_points", "label": "评分分值", "module": "scoring", "multi": True,
     "pattern": re.compile(r"(\d+(?:\.\d+)?)\s*分")},
    # -- 模块 6 报价要求（只解析费率/百分比规则，报价金额由用户提供）--
    {"id": "percent", "label": "百分比/费率", "module": "pricing", "multi": True,
     "pattern": re.compile(r"(\d+(?:\.\d+)?)\s*%")},
]


# --------------------------------------------------------------------------
# 抽取核心
# --------------------------------------------------------------------------
def _context(line, idx, all_lines):
    """行号锚点 + 上下文（前后各 1 行，各截 40 字）。"""
    ctx = []
    for j in (idx - 1, idx, idx + 1):
        if 0 <= j < len(all_lines):
            t = (all_lines[j] or "").strip()
            if t:
                ctx.append(t[:40])
    return ctx


def _score_sum_check(values):
    """评分分值合计校验（v2.4）：抽取分值去重求和，与 100 比较 → 确定性参考。

    评分分值抽取为宽松正则（\d+ 分），可能混入非评分语境分值；故仅做
    「参考合计 vs 100」提示，需人工核对，不强制一致。
    """
    nums = []
    for v in values:
        try:
            nums.append(float(v))
        except (TypeError, ValueError):
            continue
    total = round(sum(nums), 2)
    return {
        "label": "评分分值合计校验",
        "module": "scoring",
        "value": {"参考总分": 100, "抽取分值合计": total,
                  "一致": abs(total - 100) < 0.01},
        "count": len(nums),
        "note": "确定性参考：抽取到的『数字 分』去重求和。若混入非评分分值会偏差，须人工核对评分表后确认",
    }


def extract_fields(text):
    """
    按规则表抽取确定性字段 → {id: {label, value, module, count, lines, evidence}}。

    value：multi=True → 数组（去重保序）；multi=False → 首中字符串。
    lines：命中行号（1 基，可回看原文）。
    v2.4：命中 score_points 时附加 score_sum_check 派生校验字段。
    """
    lines = (text or "").splitlines()
    out = {}
    for r in RULES:
        found_lines, values = [], []
        for i, ln in enumerate(lines):
            ms = list(r["pattern"].finditer(ln or ""))
            if not ms:
                continue
            for m in ms:
                v = m.group(1)
                if v not in values:
                    values.append(v)
                if i + 1 not in found_lines:
                    found_lines.append(i + 1)
            if not r.get("multi"):
                break
        if not found_lines:
            continue
        if r.get("multi"):
            value = values
        else:
            value = values[0]
        idx0 = found_lines[0] - 1
        out[r["id"]] = {
            "label": r["label"],
            "value": value,
            "module": r["module"],
            "count": len(found_lines),
            "lines": found_lines,
            "evidence": _context(idx0, idx0, lines),
        }
    if "score_points" in out:
        out["score_sum_check"] = _score_sum_check(out["score_points"]["value"])
    return out
