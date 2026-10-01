# -*- coding: utf-8 -*-
"""
bidcraft · M4 招标文件解析 —— 纯逻辑层（校验 / 命名 / 素材对照，无 I/O）

v1.1 分工：语义解析由 agent 完成；本层只做确定性的格式校验、规范命名与对照表构建，
全部函数不读写文件系统，可单元测试。

约定：规则/判定做成可增行表或纯函数，不写死分支；对照状态三态：
  ✅已有 / ❌缺失·必须（废标风险）/ ⚠️缺失·加分
"""

import json
import re

# --------------------------------------------------------------------------
# 产物 JSON 最小结构校验（agent 按操作手册模板产出，脚本校验后落盘）
# --------------------------------------------------------------------------
# 投标要点 JSON：{"project": str, "modules": [{"id","title","type",...}]}
POINTS_REQUIRED = ("modules",)
LIST_REQUIRED = ("items",)
LIST_ITEM_REQUIRED = ("category", "required")


def validate_points_json(obj):
    """校验投标要点 JSON 最小结构 → (ok, issues)。"""
    issues = []
    if not isinstance(obj, dict):
        return False, ["投标要点 JSON 顶层必须是对象"]
    if not isinstance(obj.get("modules"), list) or not obj["modules"]:
        issues.append("modules 必须是非空数组")
    return (not issues), issues


def validate_list_json(obj):
    """校验素材清单 JSON 最小结构 → (ok, issues)。"""
    issues = []
    if not isinstance(obj, dict):
        return False, ["素材清单 JSON 顶层必须是对象"]
    items = obj.get("items")
    if not isinstance(items, list) or not items:
        issues.append("items 必须是非空数组")
        return False, issues
    for i, it in enumerate(items):
        if not isinstance(it, dict):
            issues.append("items[%d] 必须是对象" % i)
            continue
        if not it.get("category"):
            issues.append("items[%d].category 缺失（素材大类，对齐 M1）" % i)
        if "required" not in it or not isinstance(it.get("required"), bool):
            issues.append("items[%d].required 必须是布尔（true=必须，false=加分）" % i)
        for k in ("purpose", "source"):
            if not it.get(k):
                issues.append("items[%d].%s 缺失（用途/来源条款）" % (i, k))
    return (not issues), issues


# --------------------------------------------------------------------------
# 项目名校验
# --------------------------------------------------------------------------
PROJECT_NAME_PATTERN = re.compile(r"^[\w\u4e00-\u9fa5\-（）()【】\[\]、，,]+$")


def validate_project_name(name):
    """项目名禁路径分隔符与非法字符 → (ok, issue)。"""
    if not name or not name.strip():
        return False, "项目名不能为空"
    if name.strip() in (".", ".."):
        return False, "项目名不能是 . 或 .."
    if not PROJECT_NAME_PATTERN.match(name.strip()):
        return False, "项目名含非法字符（禁止 / \\ : * ? \" < > | 等）"
    return True, ""


# --------------------------------------------------------------------------
# 规范命名
# --------------------------------------------------------------------------
def original_name(src_stem):
    """原文文件名：原文_<源名去扩展名>.txt"""
    return "原文_%s.txt" % src_stem


def points_base(project):
    return "投标要点_%s" % project


def list_base(project):
    return "素材清单_%s" % project


def check_base(project):
    return "素材对照_%s" % project


# --------------------------------------------------------------------------
# 素材对照（纯逻辑：items + 素材库命中数 → 对照行）
# --------------------------------------------------------------------------
def classify_status(hits, required):
    """三态判定：hits>0 → 已有；否则按 must 分 缺失·必须 / 缺失·加分。"""
    if hits > 0:
        return "已有"
    return "缺失·必须" if required else "缺失·加分"


def build_check_rows(items, hit_fn):
    """
    把素材清单 items 逐项对照素材库 → 对照行列表（供 CSV / 人读 / JSON）。

    hit_fn(item) → {"hits": int, "paths": [rel_path, ...]}
    返回 [{category, subtype, keywords, purpose, required, source,
           status, hits, paths, suggestion}]（suggestion 由 agent/用户后续填，初始空）。
    """
    rows = []
    for it in items:
        hit = hit_fn(it) or {"hits": 0, "paths": []}
        rows.append({
            "category": it.get("category", ""),
            "subtype": it.get("subtype", ""),
            "keywords": it.get("keywords") or [],
            "purpose": it.get("purpose", ""),
            "required": bool(it.get("required")),
            "source": it.get("source", ""),
            "status": classify_status(hit.get("hits", 0), bool(it.get("required"))),
            "hits": hit.get("hits", 0),
            "paths": hit.get("paths", []),
            "suggestion": it.get("suggestion", ""),
        })
    return rows


def summarize(rows):
    """对照汇总 → {total, have, missing_required, missing_bonus, redlines}。"""
    s = {"total": len(rows), "have": 0, "missing_required": 0, "missing_bonus": 0, "redlines": []}
    for r in rows:
        if r["status"] == "已有":
            s["have"] += 1
        elif r["status"] == "缺失·必须":
            s["missing_required"] += 1
            s["redlines"].append("%s/%s" % (r["category"], r["subtype"] or r.get("keywords") or "?"))
        else:
            s["missing_bonus"] += 1
    return s


# --------------------------------------------------------------------------
# 人读文本渲染
# --------------------------------------------------------------------------
def render_points_text(doc):
    """投标要点 JSON → 人读 Markdown 文本（与 agent 产出的 md 一致性的参考渲染；仅用于 show）。"""
    if not isinstance(doc, dict) or not doc.get("modules"):
        return "（投标要点 JSON 结构不完整，无法渲染）"
    lines = ["# 投标要点 · %s" % (doc.get("project") or "")]
    for mod in doc["modules"]:
        lines.append("\n## %s" % mod.get("title", mod.get("id", "")))
        typ = mod.get("type")
        if typ == "fields":
            for k, f in (mod.get("fields") or {}).items():
                val = f.get("value") if isinstance(f, dict) else f
                ev = f.get("evidence") if isinstance(f, dict) else ""
                lines.append("- %s：%s%s" % (k, val or "（待补充）", ("（原文：%s）" % ev) if ev else ""))
        elif typ == "mixed":
            m = mod.get("method")
            if isinstance(m, dict) and m.get("value"):
                lines.append("- 评标方法：%s" % m["value"])
            for it in mod.get("score_items") or []:
                lines.append("- %s：%s%s%s" % (
                    it.get("item", ""), it.get("weight", ""), it.get("unit", ""),
                    ("（原文：%s）" % it.get("evidence", "")) if it.get("evidence") else ""))
        else:
            for it in mod.get("items") or []:
                head = " / ".join(str(it.get(k, "")) for k in ("event", "kind", "type", "rule")
                                  if it.get(k))
                tail = "（原文：%s）" % it.get("evidence", "") if it.get("evidence") else ""
                lines.append("- %s%s" % (head or it.get("rule") or "", tail))
    return "\n".join(lines)


def render_check_text(rows, summary, project):
    """对照行 → 人读文本（缺料标红提示）。"""
    lines = ["# 素材对照 · %s" % project]
    for r in rows:
        mark = {"已有": "✅", "缺失·必须": "🔴", "缺失·加分": "⚠️"}.get(r["status"], "?")
        paths = "、".join(r["paths"][:3]) if r["paths"] else "-"
        lines.append("%s %s/%s（%s）用途：%s　来源：%s　命中：%s%s" % (
            mark, r["category"], r["subtype"] or "、".join(r["keywords"]) or "?",
            r["status"], r["purpose"], r["source"], paths,
            "　建议：%s" % r["suggestion"] if r["suggestion"] else ""))
    lines.append("\n汇总：共 %d 项｜✅已有 %d｜🔴必缺 %d｜⚠️加分缺 %d" % (
        summary["total"], summary["have"], summary["missing_required"], summary["missing_bonus"]))
    if summary["redlines"]:
        lines.append("\n🔴 废标风险（必缺，需立即补充）：%s" % "、".join(summary["redlines"]))
    return "\n".join(lines)


def json_dumps(obj):
    return json.dumps(obj, ensure_ascii=False, indent=2)
