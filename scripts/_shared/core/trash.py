# -*- coding: utf-8 -*-
"""⑦ core 拆包 · 回收站（30 天保留 + 巡检清理）。"""
import shutil
from datetime import datetime, timedelta
from pathlib import Path

from .. import naming as nm

from .basic import (LibraryError, TRASH_JSON, TRASH_RETENTION_DAYS, lib_root,
                    norm_rel, now_iso, read_json, rel_to_path, write_json)

__all__ = ["trash_dir", "trash_manifest", "save_trash_manifest", "move_to_trash",
           "cleanup_trash"]


def trash_dir(ent):
    d = lib_root(ent) / "回收站"
    d.mkdir(parents=True, exist_ok=True)
    return d


def trash_manifest(ent):
    return read_json(trash_dir(ent) / TRASH_JSON, []) or []


def save_trash_manifest(ent, rows):
    write_json(trash_dir(ent) / TRASH_JSON, rows)


def move_to_trash(ent, rel_path, reason=""):
    """把企业内某文件移入回收站并登记删除时间/到期时间。"""
    ent = Path(ent)
    src = rel_to_path(lib_root(ent), rel_path)
    if not src.exists():
        raise LibraryError("待删除文件不存在：%s" % rel_path)

    name = src.name
    dest = trash_dir(ent) / name
    if dest.exists():
        stem, ext = nm.split_ext(name)
        dest = trash_dir(ent) / ("%s_%s%s" % (stem, datetime.now().strftime("%Y%m%d%H%M%S"), ext))

    shutil.move(str(src), str(dest))
    rows = trash_manifest(ent)
    rows.append({
        "file": dest.name,
        "original_rel": norm_rel(rel_path),
        "reason": reason,
        "deleted_at": now_iso(),
        "expire_at": (datetime.now() + timedelta(days=TRASH_RETENTION_DAYS)).isoformat(timespec="seconds"),
    })
    save_trash_manifest(ent, rows)
    return dest


def cleanup_trash(ent, days=TRASH_RETENTION_DAYS):
    """清理超期回收站文件；返回被删列表。"""
    ent = Path(ent)
    rows = trash_manifest(ent)
    kept, removed = [], []
    cutoff = datetime.now() - timedelta(days=days)
    tdir = trash_dir(ent)
    for r in rows:
        try:
            deleted_at = datetime.fromisoformat(r.get("deleted_at", ""))
        except Exception:
            deleted_at = None
        f = tdir / r.get("file", "")
        if deleted_at and deleted_at < cutoff and f.exists():
            f.unlink(missing_ok=True)
            removed.append(r.get("file"))
        elif f.exists():
            kept.append(r)
    # 兜底：清掉清单外的孤儿文件（按 mtime）
    known = {r.get("file") for r in kept}
    for f in tdir.iterdir():
        if f.name in (TRASH_JSON,) or f.is_dir() or f.name in known:
            continue
        try:
            mtime = datetime.fromtimestamp(f.stat().st_mtime)
        except OSError:
            continue
        if mtime < cutoff:
            f.unlink(missing_ok=True)
            removed.append(f.name)
    save_trash_manifest(ent, kept)
    return removed
