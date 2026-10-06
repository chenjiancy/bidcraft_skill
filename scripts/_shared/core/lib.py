# -*- coding: utf-8 -*-
"""⑦ core 拆包 · Library（多企业容器：初始化/解析/企业列表）。"""
from pathlib import Path

from .basic import (CLASSIFY_DIRS, ENTERPRISE_SUBDIRS, LEDGER_CSV, LEDGER_JSON,
                    LibraryError, META_JSON, lib_root, now_iso, write_json)
from .ledger import save_ledger

__all__ = ["Library"]


class Library:
    def __init__(self, root):
        self.root = Path(root)

    # -- 企业 -------------------------------------------------------------
    def ensure_root(self):
        self.root.mkdir(parents=True, exist_ok=True)

    def enterprises(self):
        if not self.root.exists():
            return []
        out = []
        for d in sorted(self.root.iterdir()):
            if not d.is_dir() or d.name.startswith("."):
                continue
            lib = lib_root(d)
            if (lib / LEDGER_JSON).exists() or (lib / LEDGER_CSV).exists() or \
               any((lib / s).is_dir() for s in CLASSIFY_DIRS):
                out.append(d.name)
        return out

    def resolve(self, name=None):
        ents = self.enterprises()
        if name:
            target = self.root / name
            if not target.is_dir():
                raise LibraryError(
                    "企业不存在：%s（现有：%s）" % (name, "、".join(ents) or "无")
                )
            return target
        if len(ents) == 1:
            return self.root / ents[0]
        if not ents:
            raise LibraryError("尚未创建任何企业，请先执行 init-enterprise 创建企业")
        raise LibraryError("存在多个企业，请用 --enterprise 指定：%s" % "、".join(ents))

    def init_enterprise(self, name, credit_code=None, owner=None):
        """
        初始化企业（三层结构）：
          软件根/<企业>/
            ├── 回收站/           ← 公司级统一回收站（删除的项目/素材均先进此处，30 天保留）
            ├── 企业级/
            │   ├── 素材库/        ← 素材库：资质/人员/业绩/荣誉/财务/收件箱 + 台账
            │   └── 模板库/
            └── 项目级/
        """
        self.ensure_root()
        dirname = ("%s_%s" % (name, credit_code)) if credit_code else name
        ent = self.root / dirname
        existed = ent.is_dir()
        ent.mkdir(parents=True, exist_ok=True)
        (ent / "回收站").mkdir(exist_ok=True)       # 公司级统一回收站（删除动作先进此处）
        (ent / "项目级").mkdir(exist_ok=True)
        (ent / "企业级" / "模板库").mkdir(parents=True, exist_ok=True)
        lib = lib_root(ent)                      # 企业级/素材库
        lib.mkdir(parents=True, exist_ok=True)
        for sub in ENTERPRISE_SUBDIRS:
            (lib / sub).mkdir(exist_ok=True)
        meta_path = lib / META_JSON
        if not meta_path.exists():
            write_json(meta_path, {
                "name": name,
                "credit_code": credit_code,
                "dir": dirname,
                "owner": owner or name,
                "schema": 1,
                "created_at": now_iso(),
            })
        if not (lib / LEDGER_JSON).exists() and not (lib / LEDGER_CSV).exists():
            save_ledger(ent, [])
        return ent, existed

    def remove_empty_enterprise(self, ent):
        """仅当企业目录为空骨架时删除（用于误创建回滚）。"""
        pass  # 保守起见不提供删除，避免误删素材
