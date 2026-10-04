# -*- coding: utf-8 -*-
"""
M5 · 项目模板冻结（⑥）：把人工修订后的项目模板「冻结」为商务标唯一信源。

流程：
  1) 校验项目模板目录存在且含 docx；
  2) 逐文件 fb.register 登记基线（sha256 + 文本指纹；重复冻结自动 bump 版本）；
  3) 写 冻结清单.json（项目/冻结时间/冻结版本/每文件 sha256+版本）；
  4) audit_frozen 检测冻结后模板是否被改动（已改=必须重新冻结，变更走 fb 流程）。

冻结版语义：商务标只认冻结版模板；模板任何修改 → proj-audit 报「已改」→ 重新冻结。
"""
import json
import re
from pathlib import Path

from _shared import core
from m_feedback import feedback as fb

FREEZE_JSON = "冻结清单.json"


def tpl_dir_of(ent, project):
    return Path(ent) / "项目级" / project / "项目模板"


def freeze_manifest_path(tpl_dir):
    return Path(tpl_dir) / FREEZE_JSON


def _next_freeze_version(tpl_dir):
    p = freeze_manifest_path(tpl_dir)
    if p.is_file():
        try:
            data = core.read_json(str(p), None) or {}
            m = re.match(r"v(\d+)", str(data.get("冻结版本", "")))
            if m:
                return "v%d" % (int(m.group(1)) + 1)
        except Exception:
            pass
    return "v1"


def freeze_project(ent, project, tpl_dir=None, note=""):
    """冻结项目模板：登记基线 + 写冻结清单。返回清单 dict。"""
    ent = Path(ent)
    tpl = Path(tpl_dir) if tpl_dir else tpl_dir_of(ent, project)
    if not tpl.is_dir():
        raise core.LibraryError("项目模板目录不存在：%s" % tpl)
    files = sorted(tpl.glob("*.docx"))
    if not files:
        raise core.LibraryError("项目模板目录无 docx 文件，无法冻结：%s" % tpl)
    ver = _next_freeze_version(tpl)
    rows = []
    for f in files:
        rel = core.norm_rel(str(f.relative_to(ent)))
        row = fb.register(ent, rel, level="项目级", project=project,
                          ptype="项目模板", generator="proj-freeze", note=note)
        rows.append({"文件": f.name, "sha256": row["sha256"], "版本": row["版本"]})
    manifest = {
        "项目": project,
        "冻结时间": core.now_iso(),
        "冻结版本": ver,
        "文件数": len(rows),
        "文件": rows,
        "说明": "商务标只认冻结版模板；模板改动需重新 proj-freeze（变更走 fb 基线流程）",
    }
    core.write_json(str(freeze_manifest_path(tpl)), manifest)
    return manifest


def audit_frozen(ent, project, tpl_dir=None):
    """冻结后审计：未变 / 已改 / 缺失（已改的必须重新冻结）。"""
    ent = Path(ent)
    tpl = Path(tpl_dir) if tpl_dir else tpl_dir_of(ent, project)
    res = fb.audit(ent, full=True, path=None)
    prefix = str(tpl.relative_to(ent)).replace("\\", "/")
    frozen = {"unchanged": [], "modified": [], "missing": []}
    for r in res["unchanged"]:
        if core.norm_rel(r.get("相对路径", "")).startswith(prefix + "/"):
            frozen["unchanged"].append(r)
    for r in res["modified"]:
        if core.norm_rel(r.get("相对路径", "")).startswith(prefix + "/"):
            frozen["modified"].append(r)
    for r in res["missing"]:
        if core.norm_rel(r.get("相对路径", "")).startswith(prefix + "/"):
            frozen["missing"].append(r)
    return frozen
