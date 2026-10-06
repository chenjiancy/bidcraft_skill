# -*- coding: utf-8 -*-
"""
bidcraft · M4 招标文件解析 —— 纯逻辑层（校验 / 命名 / 素材对照 / 双通道 / 格式章节，无 I/O）

v2.1 分工：语义解析由 agent 完成；本层只做确定性的格式校验、规范命名、对照表构建、
响应文件格式章节定位、双通道字段比对——全部函数不读写文件系统，可单元测试。

约定：规则/判定做成可增行表或纯函数，不写死分支；对照状态三态：
  ✅已有 / ❌缺失·必须（废标风险）/ ⚠️缺失·加分
"""

import json
import re

# --------------------------------------------------------------------------
# 产物 JSON 最小结构校验（agent 按操作手册模板产出，脚本校验后落盘）
# --------------------------------------------------------------------------
# 投标要点 JSON：{"project": str, "modules": [{"id","title","type",...}], "diffs": [...]}
POINTS_REQUIRED = ("modules",)
LIST_REQUIRED = ("items",)
LIST_ITEM_REQUIRED = ("category", "required")

# 解析内容框架 v5：9 个标准模块（v2.1 起强制全覆盖，可增行表；额外模块允许）
POINTS_MODULES = [
    ("basic", "项目基本信息"),
    ("qualification", "资格条件"),
    ("staff", "人员配备"),
    ("project_overview", "项目概况与监理工作内容"),
    ("scoring", "评分办法"),
    ("pricing", "报价要求"),
    ("submission", "响应文件编制与递交"),
    ("reject", "废标/否决红线"),
    ("pending", "待确认/缺失项"),
]
POINTS_MODULE_IDS = {mid for mid, _ in POINTS_MODULES}
# 双通道差异类型（v2.1）：事实值不同 / 存在性差异 / 语义冲突
DIFF_TYPES = ("事实值不同", "存在性差异", "语义冲突")


def validate_points_json(obj):
    """校验投标要点 JSON 最小结构 → (ok, issues)。v2.1：强制 9 模块覆盖 + diffs 结构。"""
    issues = []
    if not isinstance(obj, dict):
        return False, ["投标要点 JSON 顶层必须是对象"]
    modules = obj.get("modules")
    if not isinstance(modules, list) or not modules:
        return False, ["modules 必须是非空数组"]
    seen = set()
    for i, mod in enumerate(modules):
        if not isinstance(mod, dict):
            issues.append("modules[%d] 必须是对象" % i)
            continue
        for k in ("id", "title", "type"):
            if not mod.get(k):
                issues.append("modules[%d].%s 缺失（模块须含 id/title/type）" % (i, k))
        mid = mod.get("id")
        if mid:
            if mid in seen:
                issues.append("modules[%d].id 重复：%s" % (i, mid))
            seen.add(mid)
    # v2.1：9 模块框架强制全覆盖（缺模块 = 解析不完整，禁止落盘）
    missing = sorted(POINTS_MODULE_IDS - seen)
    for mid in missing:
        title = dict(POINTS_MODULES)[mid]
        issues.append("缺少标准模块 %s（%s）——9 模块框架须全覆盖" % (mid, title))
    # v2.1：双通道差异（可选数组，存在则校验结构）
    diffs = obj.get("diffs")
    if diffs is not None:
        if not isinstance(diffs, list):
            issues.append("diffs 必须是数组（双通道解析差异）")
        else:
            for i, d in enumerate(diffs):
                if not isinstance(d, dict):
                    issues.append("diffs[%d] 必须是对象" % i)
                    continue
                if not d.get("解析项"):
                    issues.append("diffs[%d].解析项 缺失（差异须指明解析项）" % i)
                if d.get("差异类型") and d["差异类型"] not in DIFF_TYPES:
                    issues.append("diffs[%d].差异类型 非法（须为 %s 之一）" % (i, "/".join(DIFF_TYPES)))
    # v2.4：已裁决事项（可选数组，存在则校验结构；裁决记录由 agent 在用户裁决后写入）
    verdicts = obj.get("verdicts")
    if verdicts is not None:
        if not isinstance(verdicts, list):
            issues.append("verdicts 必须是数组（已裁决事项）")
        else:
            for i, v in enumerate(verdicts):
                if not isinstance(v, dict):
                    issues.append("verdicts[%d] 必须是对象" % i)
                    continue
                if not v.get("item"):
                    issues.append("verdicts[%d].item 缺失（裁决对象）" % i)
                if not v.get("decision"):
                    issues.append("verdicts[%d].decision 缺失（裁决结论）" % i)
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


def fmt_base(project):
    return "响应文件格式_%s" % project


def rule_base(project):
    return "文档解析_%s" % project


def diff_base(project):
    return "双通道差异_%s" % project


def report_base(project):
    """投标要点 HTML 文件名（闸门① 展示，v2.3+；与 md/json 同基名，扩展 .html）。"""
    return "投标要点_%s" % project


def annex_base(project):
    """补遗/澄清原文文件名（v2.4+：补遗归档与跨文件比对前置）。"""
    return "补遗原文_%s" % project


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


# --------------------------------------------------------------------------
# 响应文件格式章节定位（v2.1 脚本化提取，纯逻辑）
# --------------------------------------------------------------------------
# 章节标题模式：「第X章 响应文件格式 / 投标文件格式」或独立行（压缩空白后等值）
CHAPTER_RE = re.compile(r"^\s*第[一二三四五六七八九十百零]+章")
FMT_TITLE_NAMES = ("响应文件格式", "投标文件格式")
_PAGE_NO_RE = re.compile(r"^\s*\d{1,3}\s*$")     # 孤立页码行（如「1」）


def _is_fmt_title(line):
    """响应文件格式章节标题行：章节号 + 名称，或独立行精确等于名称。"""
    t = line.strip()
    if not t:
        return False
    t = re.sub(r"\s+", "", t)
    m = re.match(r"第[一二三四五六七八九十百零]+章(.*)", t)
    if m and any(nm in m.group(1) for nm in FMT_TITLE_NAMES):
        return True
    return any(t == nm for nm in FMT_TITLE_NAMES)


def _is_next_chapter(line, start_idx, idx):
    """idx 行是否为 start 之后的下一个章节标题（用作终点，不含该行）。"""
    return idx > start_idx and bool(CHAPTER_RE.match(line or ""))


def find_fmt_span(lines, start=None, end=None):
    """
    定位响应文件格式章节 [start, end)（1 基行号，含 start 不含 end）。

    自动规则：起点 = 第一个「响应文件格式/投标文件格式」章节标题行；
    终点 = 其后下一个「第X章」标题行（不含）；无后续章节 → 文件尾并清理
    尾部噪声（连续空行 + 末尾孤立页码行）。start/end 显式给出时直接采用。
    返回 (start, end)；未定位起点 → 抛 ValueError（提示用 --start/--end）。
    """
    total = len(lines)
    start_given = start is not None
    end_given = end is not None
    if not start_given:
        # 取最后一个匹配标题行：目录条目（带点线页码）在前，正文章节标题在后
        start = next((i + 1 for i in range(len(lines) - 1, -1, -1)
                      if _is_fmt_title(lines[i])), None)
        if start is None:
            raise ValueError("未定位到「响应文件格式/投标文件格式」章节标题，"
                             "请用 --start/--end 指定行号（1 基）")
    else:
        start = int(start)
    if end_given:
        end = int(end)
    else:
        # 找 start 之后的下一个章节标题（1 基行号，不含）；无 → 文件尾（清理噪声）
        nxt = None
        for i in range(start, total):
            if _is_next_chapter(lines[i], start - 1, i):
                nxt = i + 1
                break
        if nxt is None:
            end = total
            # 清理尾部噪声：连续空行 + 末尾孤立页码
            e0 = total - 1                # 0 基最后行
            while e0 > start - 1:
                t = (lines[e0] or "").strip()
                if not t or _PAGE_NO_RE.match(t):
                    e0 -= 1
                else:
                    break
            end = e0 + 2                  # 0 基内容最后行 → 1 基不含 end
        else:
            end = nxt
    if not (1 <= start <= end <= total + 1):
        raise ValueError("非法行号区间：start=%d end=%d（总行数 %d）" % (start, end, total))
    return start, end


def extract_fmt(lines, start=None, end=None):
    """按 [start, end) 切片提取响应文件格式原文 → (text, start, end)。"""
    s, e = find_fmt_span(lines, start, end)
    return "\n".join(lines[s - 1:e - 1]), s, e


# --------------------------------------------------------------------------
# 双通道字段比对（v2.1，纯逻辑：通道A 规则抽取 vs 通道B agent 投标要点）
# --------------------------------------------------------------------------
def norm_value(v):
    """归一化值用于比对：去空白/全角半角空格/全角冒号，转小写。"""
    if v is None:
        return ""
    s = str(v)
    s = re.sub(r"[\s\u3000]", "", s)
    s = s.replace("：", ":").replace("（", "(").replace("）", ")")
    return s.lower()


_NUM_RE = re.compile(r"\d+(?:\.\d+)?")


def _numbers_equal(a, b):
    """数字归一化：两侧各取首个数字串，相等视为同一事实（忽略单位后缀/表述）。"""
    ma = _NUM_RE.search(str(a))
    mb = _NUM_RE.search(str(b))
    return bool(ma and mb and ma.group(0) == mb.group(0))


def collect_b_points(doc):
    """通道B（投标要点 JSON）→ {标签: [值, ...]}（fields/items/mixed 通用收集）。"""
    out = {}
    for mod in (doc or {}).get("modules") or []:
        if not isinstance(mod, dict):
            continue
        fields = mod.get("fields")
        if isinstance(fields, dict):
            for k, f in fields.items():
                val = f.get("value") if isinstance(f, dict) else f
                if val:
                    out.setdefault(str(k), []).append(str(val))
        for it in mod.get("items") or []:
            if not isinstance(it, dict):
                continue
            for k in ("event", "rule", "item", "kind"):
                if it.get(k):
                    out.setdefault(str(k), []).append(str(it[k]))
        for it in mod.get("score_items") or []:
            if isinstance(it, dict) and it.get("item"):
                out.setdefault(it["item"], []).append(str(it.get("weight", "")))
    return out


def compare_dual(fields_a, doc_b):
    """
    双通道差异比对：通道A 字段（{id: {label, value}}）vs 通道B 投标要点 doc。

    差异类型（v2.1 三类）：
      - 事实值不同：两通道同标签值不一致（归一化后）；
      - 存在性差异：通道A 有关键字段，通道B 未解析到。
    返回差异列表 [{解析项, 通道A, 通道B, 差异类型, 建议}]。
    多值字段（value 为数组）：任一分值在通道B 命中即不算差异。
    """
    b_map = collect_b_points(doc_b)
    diffs = []
    for fid, fa in (fields_a or {}).items():
        label = fa.get("label") or fid
        raw = fa.get("value")
        if isinstance(raw, list):
            vals_a = [norm_value(x) for x in raw if norm_value(x)]
            disp_a = " / ".join(str(x) for x in raw)
        else:
            va = norm_value(raw)
            vals_a = [va] if va else []
            disp_a = str(raw) if raw is not None else ""
        if not vals_a:
            continue
        bvals = b_map.get(str(label), [])
        if not bvals:
            diffs.append({"解析项": label, "通道A": disp_a,
                          "通道B": "（通道B 未解析到）",
                          "差异类型": "存在性差异",
                          "建议": "核对通道A 是否误报或通道B 遗漏"})
            continue
        bnorm = [norm_value(b) for b in bvals]
        matched = any(va in bnorm for va in vals_a)
        if not matched:
            # 数字归一化兜底：同数字不同单位后缀（48.86 vs 48.86万元）视为一致
            matched = any(_numbers_equal(va, b) for va in vals_a for b in bvals)
        if not matched:
            diffs.append({"解析项": label, "通道A": disp_a,
                          "通道B": " / ".join(str(b) for b in bvals),
                          "差异类型": "事实值不同",
                          "建议": "以招标原文为最终依据，用户裁决"})
    return diffs
