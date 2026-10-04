# -*- coding: utf-8 -*-
"""⑦ core 拆包 · 收件箱批次（Inbox 类：open/add/sync/close/remove）。"""
import os
import shutil
import uuid
from datetime import datetime
from pathlib import Path

from .. import naming as nm

from .basic import (BATCH_JSON, LibraryError, lib_root, norm_rel, now_iso,
                    read_json, sha256_of, write_json)

__all__ = ["Inbox"]


class Inbox:
    def __init__(self, ent):
        self.ent = Path(ent)
        self.dir = lib_root(self.ent) / "收件箱"
        self.batch_path = self.dir / BATCH_JSON

    # -- 批次 -------------------------------------------------------------
    def open(self, note=None, force=False):
        self.dir.mkdir(parents=True, exist_ok=True)
        b = read_json(self.batch_path, None)
        if b and not b.get("closed_at") and not force:
            b["resumed"] = True
            return b
        b = {
            "batch_id": uuid.uuid4().hex[:8],
            "created_at": now_iso(),
            "closed_at": None,
            "note": note or "",
            "items": [],
        }
        # 接管「上一批次未归档、仍躺在收件箱里」的文件，避免丢跟踪
        carried = self._register_folder_files(b)
        b["carried_over"] = len(carried)
        write_json(self.batch_path, b)
        return b

    def load(self):
        return read_json(self.batch_path, None)

    def require_open(self):
        b = self.load()
        if not b:
            raise LibraryError("收件箱未打开，请先执行 open-inbox")
        if b.get("closed_at"):
            raise LibraryError("本批次已关闭（closed_at=%s），如需继续请重新 open-inbox" % b["closed_at"])
        return b

    def add(self, src_path, original_name=None):
        """逐张上传：单次调用只接收一个文件。"""
        src = Path(src_path)
        if not src.exists():
            raise LibraryError("文件不存在：%s" % src)
        if src.is_dir():
            raise LibraryError("一次只能上传一个文件（不支持目录/批量）：%s" % src)

        b = self.require_open()
        seq = (max([i.get("seq", 0) for i in b["items"]]) + 1) if b["items"] else 1

        orig = original_name or src.name
        target = self.dir / orig
        if target.exists():
            stem, ext = nm.split_ext(orig)
            n = 2
            while True:
                cand = self.dir / ("%s_dup%d%s" % (stem, n, ext))
                if not cand.exists():
                    target = cand
                    break
                n += 1

        shutil.copy2(src, target)
        os.utime(target, None)  # 刷新 mtime，便于顺序兜底

        item = {
            "seq": seq,
            "file": target.name,
            "original_name": orig,
            "via": "upload",
            "size": target.stat().st_size,
            "sha256": sha256_of(target),
            "written_at": datetime.fromtimestamp(target.stat().st_mtime).isoformat(timespec="seconds"),
            "uploaded_at": now_iso(),
        }
        b["items"].append(item)
        write_json(self.batch_path, b)
        return item

    def _register_folder_files(self, b):
        """把「直接拷进收件箱文件夹」的文件补登记进批次 b（就地修改，不落盘）。"""
        known = {i.get("file") for i in b.get("items", [])}
        reserved = {BATCH_JSON, "_归档提案.json"}
        found = []
        for p in sorted(self.dir.iterdir()):
            if not p.is_file() or p.name in reserved or p.name.startswith("."):
                continue
            if p.name not in known:
                found.append(p)
        found.sort(key=lambda p: (p.stat().st_mtime, p.name))

        seq = (max([i.get("seq", 0) for i in b.get("items", [])]) + 1) if b.get("items") else 1
        added = []
        for p in found:
            it = {
                "seq": seq,
                "file": p.name,
                "original_name": p.name,
                "via": "folder",
                "size": p.stat().st_size,
                "sha256": sha256_of(p),
                "written_at": datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds"),
                "uploaded_at": now_iso(),
            }
            b.setdefault("items", []).append(it)
            added.append(it)
            seq += 1
        return added

    def sync(self):
        """
        把「直接拷进收件箱文件夹」的文件补登记进当前批次（上传方式不限）。
        这类文件顺序只能靠写入时间推断，故标记 via=folder 并在撞车时提示人工确认。
        """
        b = self.require_open()
        added = self._register_folder_files(b)
        if added:
            write_json(self.batch_path, b)
        return added

    def items(self, order="seq"):
        b = self.load() or {"items": []}
        items = list(b.get("items", []))
        if order == "seq":
            items.sort(key=lambda i: i.get("seq", 0))
        elif order == "time":
            items.sort(key=lambda i: i.get("written_at", ""))
        return items

    def has_time_collision(self):
        """
        顺序风险检测。
        - 全部条目经 upload 逐张登记 → 序号即权威顺序，无风险。
        - 存在「直接丢进文件夹」的条目 → 顺序只能靠写入时间推断，同秒即视为撞车。
        """
        items = self.items()
        if not items:
            return False
        folder_items = [i for i in items if i.get("via") != "upload"]
        if not folder_items:
            return False
        times = [i.get("written_at", "") for i in folder_items]
        return len(times) != len(set(times))

    def close(self):
        b = self.load()
        if not b:
            raise LibraryError("收件箱未打开")
        b["closed_at"] = now_iso()
        write_json(self.batch_path, b)
        return b

    def remove_items(self, filenames):
        """从批次中移除已归档条目（文件已在归档时移走）。"""
        b = self.load()
        if not b:
            return
        drop = set(filenames)
        b["items"] = [i for i in b["items"] if i.get("file") not in drop]
        if not b["items"]:
            self.batch_path.unlink(missing_ok=True)
        else:
            write_json(self.batch_path, b)

    def path_of(self, filename):
        return self.dir / filename
