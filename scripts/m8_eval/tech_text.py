# -*- coding: utf-8 -*-
"""
bidcraft · M8 T16 技术标章节评审扩展 —— M6 技术标文本发现与评分项章节注入

职责（纯逻辑 + 轻量项目内扫描，无 UI 完整可用）：
  - discover_tech_text(proj_dir, project)：扫描项目级 <项目>/技术标/ 下 M6 正文
    （技术标/章节/ch-*.md，按章节树 章节树.json 过滤与排序，剥离 M6-REVISE/M6-COVERAGE 注释块）
    + 覆盖矩阵（技术标/检查/覆盖矩阵_<项目>.json）→ 返回 {found, chapters, totalChars,
    coverage_rows, source, note}；无 M6 产物 → found=False（通道B 维持"无方案文本待 M6 精评"）。
  - attach_tech_to_standard(standard, tech_text)：把覆盖矩阵按评分项 idx 注入通道A 标准项
    （kind=outline 类 → techChapters/techCovered/techWeak），供报告展示与通道B 引用。
"""
import json
import re
from pathlib import Path

_TECH_DIR = "技术标"
_CHAPTERS_DIR = "章节"
_CHECK_DIR = "检查"
_TREE = "章节树.json"


def _strip_blocks(text):
    """剥离 M6 元信息注释块（M6-REVISE 变更块 / M6-COVERAGE 自述块），只留正文。"""
    text = re.sub(r"<!--\s*M6-REVISE\b.*?-->", "", text, flags=re.S)
    text = re.sub(r"<!--\s*M6-COVERAGE\b.*?-->", "", text, flags=re.S)
    return text.strip()


def _chars(text):
    """有效字数（CJK + 词，与 M6 页数口径同源，仅用于标注体量）。"""
    return len(re.findall(r"[\u4e00-\u9fff]", text)) + len(re.findall(r"[A-Za-z0-9]+", text))


def _load_tree(tech):
    p = tech / _TREE
    if not p.is_file():
        return None
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except ValueError:
        return None
    return doc.get("chapters") if isinstance(doc, dict) else None


def _load_coverage(tech, project):
    p = tech / _CHECK_DIR / ("覆盖矩阵_%s.json" % project)
    if not p.is_file():
        return None
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except ValueError:
        return None
    return doc.get("rows") if isinstance(doc, dict) else None


def discover_tech_text(proj_dir, project):
    """发现 M6 技术标正文与覆盖矩阵 → dict（found=False 表示未交付 M6 文本）。"""
    tech = Path(proj_dir) / _TECH_DIR
    if not tech.is_dir():
        return {"found": False, "chapters": [], "totalChars": 0,
                "coverage_rows": None, "source": "", "note": "技术标目录不存在（M6 未交付）"}
    chapters_dir = tech / _CHAPTERS_DIR
    tree = _load_tree(tech)
    coverage = _load_coverage(tech, project)

    chapters = []
    if tree:
        for c in tree:
            cid = c.get("id") or ""
            if not cid:
                continue
            p = chapters_dir / ("%s.md" % cid)
            if not p.is_file():
                continue
            body = _strip_blocks(p.read_text(encoding="utf-8"))
            if not body:
                continue
            chapters.append({"id": cid, "no": c.get("no", ""),
                             "title": c.get("title", cid),
                             "path": str(p), "chars": _chars(body)})
    else:
        if not chapters_dir.is_dir():
            return {"found": False, "chapters": [], "totalChars": 0,
                    "coverage_rows": coverage,
                    "source": str(tech), "note": "M6 章节目录不存在（无正文，待 M6 交付）"}
        for p in sorted(chapters_dir.glob("ch-*.md")):
            if p.name.endswith(".draft.md"):
                continue
            body = _strip_blocks(p.read_text(encoding="utf-8"))
            if not body:
                continue
            cid = p.stem
            chapters.append({"id": cid, "no": "", "title": cid,
                             "path": str(p), "chars": _chars(body)})

    total = sum(c["chars"] for c in chapters)
    if not chapters:
        return {"found": False, "chapters": [], "totalChars": 0,
                "coverage_rows": coverage,
                "source": str(chapters_dir), "note": "技术标章节无正文（待 M6 撰写/精修）"}
    return {"found": True, "chapters": chapters, "totalChars": total,
            "coverage_rows": coverage, "source": str(chapters_dir),
            "note": "M6 技术标正文（%d 章 %d 字）" % (len(chapters), total)}


def attach_tech_to_standard(standard, tech_text):
    """把覆盖矩阵（评分项 idx → 章节/覆盖态）注入通道A 标准 items（outline 类）。

    kind 属主观分类型（outline/subjective/unknown 且 weight 非空）时注入：
      techChapters : [章节 id]（覆盖矩阵 chapters 字段）
      techCovered  : bool（有章节命中）
      techWeak     : bool（名义覆盖但 keyPoints 交集不足）
    无覆盖矩阵或非主观项不动（返回原 standard，字段保持 None 不误报）。
    """
    rows = (tech_text or {}).get("coverage_rows")
    by_idx = {r.get("idx"): r for r in rows} if rows else {}
    for it in (standard.get("items") or []):
        if it.get("kind") not in ("outline", "subjective", "unknown"):
            continue
        row = by_idx.get(it.get("idx"))
        if not row:
            continue
        it["techChapters"] = row.get("chapters") or []
        it["techCovered"] = bool(row.get("covered"))
        it["techWeak"] = bool(row.get("weak"))
    return standard
