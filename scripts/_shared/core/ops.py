# -*- coding: utf-8 -*-
"""⑦ core 拆包 · 巡检 / 检索 / 概览。"""
import re
from pathlib import Path

from .. import naming as nm

from .basic import CLASSIFY_DIRS, lib_root, norm_rel, now_iso, rel_to_path
from .batch import Inbox
from .inbox import ownership_check
from .ledger import ledger_index, load_ledger
from .trash import trash_manifest

__all__ = ["inspect", "query", "enterprise_overview"]


# --------------------------------------------------------------------------
# 巡检（非常规上传 + 命名规范）
# --------------------------------------------------------------------------
def inspect(ent):
    """扫描分类目录：找出未经收件箱的素材（非常规上传）与命名不规范项。"""
    ent = Path(ent)
    index = ledger_index(ent)
    issues = []

    for cat in CLASSIFY_DIRS:
        d = lib_root(ent) / cat
        if not d.is_dir():
            continue
        for p in sorted(d.rglob("*")):
            if not p.is_file() or p.name.startswith("."):
                continue
            rel = norm_rel(p.relative_to(lib_root(ent)).as_posix())
            row = index.get(rel)

            if row:
                ok, msgs = nm.validate(row.get("category") or cat, row.get("subtype") or None, p.name)
                if not ok:
                    issues.append({
                        "type": "命名不规范",
                        "rel_path": rel,
                        "detail": "；".join(msgs),
                        "suggestion": nm.rule_hint(row.get("category") or cat, row.get("subtype") or None),
                    })
            else:
                guess_cat, guess_sub, _ = nm.classify(p.name)
                target_cat = guess_cat or cat
                ok, msgs = nm.validate(target_cat, guess_sub, p.name)
                issues.append({
                    "type": "非常规上传",
                    "rel_path": rel,
                    "detail": "该文件不在台账中（未经收件箱归档）",
                    "suggestion": nm.rule_hint(target_cat, guess_sub) if ok is False else "命名看似合规，仅需补登台账",
                    "guess": {"category": guess_cat, "subtype": guess_sub},
                })
                # 归属校验
                own = ownership_check(ent, p.name)
                if own.get("status") == "conflict":
                    issues.append({
                        "type": "企业归属疑似不符",
                        "rel_path": rel,
                        "detail": "文件名疑似属于其他企业：%s（命中“%s”）" % (own.get("other"), own.get("token")),
                    })

    # 台账有记录、磁盘上却已缺失
    for rel, row in index.items():
        if not rel_to_path(lib_root(ent), rel).exists():
            issues.append({
                "type": "台账悬空",
                "rel_path": rel,
                "detail": "台账有记录但文件已不存在（可能被手工移动/删除）",
            })

    return {
        "enterprise": ent.name,
        "scanned_at": now_iso(),
        "count": len(issues),
        "issues": issues,
    }


# --------------------------------------------------------------------------
# 检索
# --------------------------------------------------------------------------
def query(ent, category=None, keyword=None, subtype=None, expires_before=None,
          expires_after=None, owner=None):
    rows = load_ledger(ent)
    out = []
    for r in rows:
        if category and r.get("category") != category:
            continue
        if subtype and r.get("subtype") != subtype:
            continue
        if owner and owner not in (r.get("owner") or ""):
            continue
        if keyword:
            hay = " ".join([
                r.get("rel_path", ""), r.get("keywords", ""),
                r.get("subtype", ""), r.get("note", ""),
                r.get("original_filename", ""),
            ])
            if keyword not in hay:
                continue
        d = r.get("dates", "")
        first = (d.split("、")[0] if d else "") or ""
        dated = bool(re.match(r"^\d{8}$", first))
        if expires_before or expires_after:
            if not dated:
                continue  # 有日期筛选时，无有效日期的条目不计入
        if expires_before and dated and first >= expires_before:
            continue
        if expires_after and dated and first < expires_after:
            continue
        out.append(r)
    return out


# --------------------------------------------------------------------------
# 概览
# --------------------------------------------------------------------------
def enterprise_overview(ent):
    ent = Path(ent)
    rows = load_ledger(ent)
    by_cat = {}
    for r in rows:
        by_cat.setdefault(r.get("category", "未分类"), 0)
        by_cat[r.get("category", "未分类")] += 1

    disk = {}
    for cat in CLASSIFY_DIRS:
        d = lib_root(ent) / cat
        disk[cat] = sum(1 for p in d.rglob("*") if p.is_file()) if d.is_dir() else 0

    inbox = Inbox(ent)
    b = inbox.load()
    return {
        "enterprise": ent.name,
        "path": str(lib_root(ent)),
        "ledger_total": len(rows),
        "by_category": by_cat,
        "disk_files": disk,
        "inbox": {
            "open": bool(b and not b.get("closed_at")),
            "batch_id": (b or {}).get("batch_id"),
            "items": len((b or {}).get("items", [])),
        },
        "trash": len(trash_manifest(ent)),
    }
