# -*- coding: utf-8 -*-
"""
bidcraft · M6 技术标制作 —— 上下文包组装（`m6.ctx/v1`，T5）

严格按 `references/M6-技术标制作-提示词.md` 的上下文包 schema：
  chapter / tocBrief / scoreItems / terminology / personnel / materials /
  style / bidMode / personnelWriteMode / kbStatus
  expertPack（可选，R-T3 专家包注入，由 packs.attach_context 写入）

素材注入遵守 `dependsOnMaterials`：未声明依赖的素材不注入（提示词 R7）。
"""
from _shared import core

from . import store
from . import sources


def parent_no(no):
    return no.rpartition(".")[0] if "." in (no or "") else ""


def toc_brief(tree, ch):
    """父级标题 + 同级标题（不含正文）。"""
    chapters = store.list_chapters(tree)
    no = ch.get("no") or ""
    parent = parent_no(no)
    parts = []
    if parent:
        pch = next((c for c in chapters if c.get("no") == parent), None)
        if pch:
            parts.append("上级：%s %s" % (parent, pch.get("title") or ""))
    sibs = [c for c in chapters
            if parent_no(c.get("no") or "") == parent and c.get("id") != ch.get("id")]
    if sibs:
        parts.append("同级：" + "；".join("%s %s" % (c.get("no"), c.get("title") or "")
                                        for c in sibs))
    return "｜".join(parts)


def materials(tree, ch, points, material):
    deps = ch.get("dependsOnMaterials") or []
    out = []
    if "project_overview" in deps:
        facts = sources.field_values(points, "project_overview")
        if facts:
            out.append({"name": "项目概况与监理工作内容", "category": "project_overview",
                        "facts": facts})
    if "performance" in deps and material:
        perfs = [it for it in (material.get("performance") or []) if isinstance(it, dict)]
        if perfs:
            out.append({"name": "企业业绩", "category": "performance",
                        "facts": {"items": [{"名称": it.get("name", ""),
                                             "来源": "素材清单#performance[%d]" % i}
                                            for i, it in enumerate(perfs)]}})
    if "enterprise_profile" in deps and material:
        facts = {}
        if isinstance(material.get("企业基础信息"), dict):
            facts.update(material["企业基础信息"])
        for sec in ("qualification_required", "iso_certificates", "honors"):
            items = [it.get("name") for it in (material.get(sec) or []) if isinstance(it, dict)]
            if items:
                facts[sec] = items
        if facts:
            out.append({"name": "企业基础信息", "category": "enterprise_profile",
                        "facts": facts})
    if "regulation" in deps:
        out.append({"name": "法规规范", "category": "regulation",
                    "facts": {"kbStatus": "unavailable",
                              "note": "知识库未接入，禁止引用具体条文编号"}})
    return out


def style_pack(tree, args):
    """风格库（共享级 styles.json）命中则注入 prompt/require，缺失用空串。"""
    style = dict(tree.get("style") or {})
    pack = {"id": style.get("id", ""), "name": style.get("name", ""),
            "prompt": "", "require": ""}
    sid = (style.get("promptRef") or "").rpartition("#")[2] or pack["id"]
    root = sources.lib_root(args)
    for base in (root / "共享资源" / "技术标风格",
                 root.parent / "共享资源" / "技术标风格"):
        p = base / "styles.json"
        if not p.is_file():
            continue
        doc = core.read_json(str(p), None) or {}
        rows = doc.get("styles") if isinstance(doc, dict) else None
        if isinstance(rows, dict):
            entry = rows.get(sid)
        elif isinstance(rows, list):
            entry = next((r for r in rows if isinstance(r, dict) and r.get("id") == sid), None)
        else:
            entry = None
        if isinstance(entry, dict):
            pack["prompt"] = entry.get("prompt") or ""
            pack["require"] = entry.get("require") or ""
        break
    return pack


def build_context(tree, ch, material, args, points):
    deps = ch.get("dependsOnMaterials") or []
    score_items = [{"idx": ref.get("idx"), "item": ref.get("item", ""),
                    "weight": ref.get("weight"), "evidence": ""}
                   for ref in (ch.get("scoreRefs") or []) if isinstance(ref, dict)]
    return {
        "schema": store.CTX_SCHEMA,
        "chapter": {"id": ch.get("id"), "no": ch.get("no"), "title": ch.get("title"),
                    "keyPoints": list(ch.get("keyPoints") or []),
                    "wordCnt": ch.get("wordCnt")},
        "tocBrief": toc_brief(tree, ch),
        "scoreItems": score_items,
        "terminology": dict(tree.get("terminology") or {}),
        "personnel": list(tree.get("personnel") or []) if "personnel" in deps else [],
        "materials": materials(tree, ch, points, material),
        "style": style_pack(tree, args),
        "bidMode": tree.get("bidMode"),
        "personnelWriteMode": "post-only" if tree.get("bidMode") == "暗标" else "with-name",
        "kbStatus": "unavailable",
    }


def fill_score_items(pack, raw_items):
    """用投标要点原文补全 idx/item/weight/evidence。"""
    for row in pack["scoreItems"]:
        idx = row.get("idx")
        if isinstance(idx, int) and 0 <= idx < len(raw_items):
            src = raw_items[idx] if isinstance(raw_items[idx], dict) else {}
            row["item"] = src.get("item") or row["item"]
            row["weight"] = src.get("weight", row.get("weight"))
            row["evidence"] = src.get("evidence") or ""
    return pack
