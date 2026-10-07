# -*- coding: utf-8 -*-
"""⑦ core 拆包 · 回收站（公司级统一回收站：30 天保留 + 巡检清理）。

统一规则：回收站位于 <企业>/回收站（公司根下）；公司内所有删除动作
（素材、项目等）一律先移入此处，默认保留 30 天后由 cleanup 清理。
旧版素材库回收站（<企业>/企业级/素材库/回收站）在首次访问时自动迁移。
"""
import shutil
from datetime import datetime, timedelta
from pathlib import Path

from .. import naming as nm

from .basic import (LibraryError, TRASH_JSON, TRASH_RETENTION_DAYS, lib_root,
                    norm_rel, now_iso, read_json, rel_to_path, write_json)

__all__ = ["trash_dir", "trash_manifest", "save_trash_manifest", "move_to_trash",
           "cleanup_trash", "lib_rel"]


def lib_rel(rel):
    """把相对素材库的路径转成相对公司根的路径（如 资质/x.jpg → 企业级/素材库/资质/x.jpg）。"""
    return "%s/%s" % ("/".join(("企业级", "素材库")), norm_rel(rel))


def trash_dir(ent):
    """公司级统一回收站：<企业>/回收站。首次访问时幂等迁移旧素材库回收站。"""
    ent = Path(ent)
    new = ent / "回收站"
    old = lib_root(ent) / "回收站"
    if old.exists():
        # 幂等迁移：内容与清单移入新位置；清单 original_rel 补公司根前缀
        new.mkdir(parents=True, exist_ok=True)
        rows = read_json(old / TRASH_JSON, []) or []
        migrated = []
        for item in old.iterdir():
            target = new / item.name
            if target.exists():
                stem, ext = nm.split_ext(item.name)
                target = new / ("%s_%s%s" % (stem, datetime.now().strftime("%Y%m%d%H%M%S"), ext))
            shutil.move(str(item), str(target))
            if item.name == TRASH_JSON:
                migrated.append(target)
        if migrated:
            rows = [dict(r, original_rel=lib_rel(r["original_rel"]))
                    for r in rows if isinstance(r, dict)]
            save_trash_manifest(ent, rows)
        try:
            old.rmdir()
        except OSError:
            pass
    new.mkdir(parents=True, exist_ok=True)
    return new


def trash_manifest(ent):
    return read_json(trash_dir(ent) / TRASH_JSON, []) or []


def save_trash_manifest(ent, rows):
    write_json(trash_dir(ent) / TRASH_JSON, rows)


def move_to_trash(ent, rel_path, reason=""):
    """把公司内任意文件或目录（rel_path 为相对公司根）移入公司回收站并登记。"""
    ent = Path(ent)
    src = rel_to_path(ent, rel_path)
    if not src.exists():
        raise LibraryError("待删除路径不存在：%s" % rel_path)

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

    # ---- 写后回读（fail fast；支持文件与目录，故直接查存在性）----
    if not dest.exists():
        raise LibraryError("写后回读失败：回收站目标不存在 %s" % dest)
    if src.exists():
        raise LibraryError("写后回读失败：源未移除 %s" % rel_path)
    if not any(r.get("file") == dest.name for r in trash_manifest(ent)):
        raise LibraryError("写后回读失败：回收站清单未登记 %s" % dest.name)
    return dest


def cleanup_trash(ent, days=TRASH_RETENTION_DAYS):
    """清理超期回收站文件/目录；返回被删列表。"""
    ent = Path(ent)
    rows = trash_manifest(ent)
    kept, removed = [], []
    cutoff = datetime.now() - timedelta(days=days)
    tdir = trash_dir(ent)

    def _remove(p):
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)
        else:
            p.unlink(missing_ok=True)

    for r in rows:
        try:
            deleted_at = datetime.fromisoformat(r.get("deleted_at", ""))
        except Exception:
            deleted_at = None
        f = tdir / r.get("file", "")
        if deleted_at and deleted_at < cutoff and f.exists():
            _remove(f)
            removed.append(r.get("file"))
        elif f.exists():
            kept.append(r)
    # 兜底：清掉清单外的孤儿文件/目录（按 mtime）
    known = {r.get("file") for r in kept}
    for f in tdir.iterdir():
        if f.name in (TRASH_JSON,) or f.name in known:
            continue
        try:
            mtime = datetime.fromtimestamp(f.stat().st_mtime)
        except OSError:
            continue
        if mtime < cutoff:
            _remove(f)
            removed.append(f.name)
    save_trash_manifest(ent, kept)
    return removed
