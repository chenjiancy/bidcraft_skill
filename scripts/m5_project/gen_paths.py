# -*- coding: utf-8 -*-
"""⑦ generator 拆包 · 路径解析（项目目录/契约/素材清单/招标文件默认路径）。"""
import glob
from pathlib import Path

from .gen_common import GenError

__all__ = ["_resolve_project_dir", "_default_contract_path", "_default_material_path",
           "_default_source_docx"]


def _resolve_project_dir(ent, project):
    root = Path(ent) / "项目级"
    cands = [d for d in root.iterdir() if d.is_dir()] if root.is_dir() else []
    if not cands:
        raise GenError("项目级下没有项目目录")
    for d in cands:
        if d.name == project:
            return d
    return None


def _default_contract_path(proj_dir):
    p = proj_dir / "招标解析" / "内容契约" / "内容契约.json"
    if not p.is_file():
        raise GenError("找不到内容契约：%s（先运行 proj-content-contract 生成）" % p)
    return p


def _default_material_path(proj_dir):
    p = proj_dir / "招标解析" / "素材清单.json"
    if p.is_file():
        return p
    # proj-mat 默认落盘命名 素材清单_<项目>.json → glob 兼容（跳过空白表）
    cands = sorted(glob.glob(str(proj_dir / "招标解析" / "素材清单_*.json")))
    if cands:
        return Path(cands[-1])
    raise GenError("找不到素材清单（招标解析/素材清单.json 或 素材清单_*.json）：%s" % p)


def _default_source_docx(proj_dir):
    # 兼容「招标文件-*.docx」与「招标文件_<项目>.docx」两种命名
    cands = sorted(glob.glob(str(proj_dir / "招标解析" / "招标文件-*.docx"))
                   + glob.glob(str(proj_dir / "招标解析" / "招标文件_*.docx")))
    if not cands:
        raise GenError("找不到招标文件 docx（招标解析/招标文件-*.docx）")
    return Path(cands[0])
