# -*- coding: utf-8 -*-
"""⑦ core 拆包 · 巡检 / 检索 / 概览 / 数据一致性对账。"""
import re
from datetime import datetime, timedelta
from pathlib import Path

from .. import naming as nm

from .basic import (CLASSIFY_DIRS, TRASH_JSON, TRASH_RETENTION_DAYS, lib_root,
                    norm_rel, now_iso, rel_to_path)
from .batch import Inbox
from .inbox import ownership_check
from .ledger import ledger_index, load_ledger
from .trash import trash_dir, trash_manifest

__all__ = ["inspect", "query", "enterprise_overview", "consistency_check"]


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
            kw_val = r.get("keywords") or ""
            if isinstance(kw_val, list):  # 兼容历史脏数据（空列表/列表关键词）
                kw_val = "、".join(str(x) for x in kw_val if str(x).strip())
            hay = " ".join([
                r.get("rel_path", ""), kw_val,
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


# --------------------------------------------------------------------------
# 数据一致性对账（台账 ↔ 磁盘 ↔ 回收站）
# --------------------------------------------------------------------------
def consistency_check(ent):
    """
    三方对账：
      1. 台账内部：重复 rel_path；
      2. 台账 ↔ 磁盘：悬空（台账有、磁盘无）/ 未登记（磁盘有、台账无）/ 路径越界（首段非分类目录）；
      3. 回收站清单 ↔ 回收站磁盘：清单悬空 / 孤儿文件 / 过期未清理。

    返回 {"enterprise", "scanned_at", "summary", "issues", "ok"}；
    issues 为空即 ok=True（不修改任何数据，纯只读对账）。
    """
    ent = Path(ent)
    lib = lib_root(ent)
    rows = load_ledger(ent)
    index = ledger_index(ent)
    issues = []

    # 1) 台账内部：重复 rel_path
    seen = {}
    for r in rows:
        rel = norm_rel(r.get("rel_path", ""))
        if not rel:
            continue
        if rel in seen:
            issues.append({
                "type": "台账重复路径", "rel_path": rel,
                "detail": "台账中同路径出现多行（id：%s 与 %s）" % (seen[rel], r.get("id", "")),
            })
        else:
            seen[rel] = r.get("id", "")

    # 2) 台账 ↔ 磁盘：悬空 / 越界
    for rel in index:
        first = rel.split("/")[0]
        if first not in CLASSIFY_DIRS:
            issues.append({
                "type": "台账路径越界", "rel_path": rel,
                "detail": "台账路径首段「%s」不在分类目录（%s）"
                          % (first, "、".join(CLASSIFY_DIRS)),
            })
        if not rel_to_path(lib, rel).exists():
            issues.append({
                "type": "台账悬空", "rel_path": rel,
                "detail": "台账有记录但磁盘无此文件（可能被手工移动/删除）",
            })

    # 3) 磁盘 ↔ 台账：未登记
    disk_files = []
    for cat in CLASSIFY_DIRS:
        d = lib / cat
        if not d.is_dir():
            continue
        for p in sorted(d.rglob("*")):
            if not p.is_file() or p.name.startswith("."):
                continue
            rel = norm_rel(p.relative_to(lib).as_posix())
            disk_files.append(rel)
            if rel not in index:
                issues.append({
                    "type": "未登记文件", "rel_path": rel,
                    "detail": "磁盘有文件但台账无记录（非常规上传或台账缺失）",
                })

    # 4) 回收站清单 ↔ 回收站磁盘
    tdir = trash_dir(ent)
    man = trash_manifest(ent)
    known = {}
    for r in man:
        f = r.get("file", "")
        known.setdefault(f, []).append(r)
    trash_disk = []
    if tdir.is_dir():
        for p in tdir.iterdir():
            if p.name.startswith(".") or p.name == TRASH_JSON:
                continue
            trash_disk.append(p.name)
    for f in known:
        if not (tdir / f).exists():
            issues.append({
                "type": "回收站清单悬空", "file": f,
                "detail": "回收站清单有记录但磁盘无此文件（可能被手工删除）",
            })
    for f in trash_disk:
        if f not in known:
            issues.append({
                "type": "回收站孤儿文件", "file": f,
                "detail": "回收站磁盘有文件但清单无记录（可能直接拷贝/旧版遗留）",
            })

    # 5) 回收站过期未清理
    cutoff = datetime.now() - timedelta(days=TRASH_RETENTION_DAYS)
    for r in man:
        try:
            deleted_at = datetime.fromisoformat(r.get("deleted_at", ""))
        except Exception:
            continue
        if deleted_at and deleted_at < cutoff and (tdir / r.get("file", "")).exists():
            issues.append({
                "type": "回收站过期未清理", "file": r.get("file"),
                "detail": "已超保留期 %d 天仍存在（deleted_at=%s）"
                          % (TRASH_RETENTION_DAYS, r.get("deleted_at")),
            })

    return {
        "enterprise": ent.name,
        "scanned_at": now_iso(),
        "summary": {
            "ledger_rows": len(rows),
            "ledger_unique_paths": len(index),
            "disk_files": len(disk_files),
            "trash_manifest": len(man),
            "trash_disk": len(trash_disk),
        },
        "issues": issues,
        "ok": not issues,
    }
