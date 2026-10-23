# -*- coding: utf-8 -*-
"""
bidcraft · M6 技术标制作 —— M4 数据源读取与设置推导（T5，无 CLI / 无正文生成）

职责：
  - 项目内路径硬校验（对齐 M8 `_ensure_inside`）
  - 读 M4 `投标要点_<项目>.json` / `素材清单_<项目>.json`
  - 推导 `技术标/设置.json`：bidMode、页数约束、术语表、拟派人员、风格/排版默认值
  - tech-init 落盘该设置；tech-outline/tech-ctx 在设置缺失时用同一函数兜底
"""
import json
import os
import re
from pathlib import Path

from _shared import core
from m4_tender import rules as t_rules

SETTINGS_FILE = "设置.json"
SETTINGS_SCHEMA = "m6.settings/v1"
DEFAULT_MAX_PAGES = 80
DEFAULT_CHARS_PER_PAGE = 1000
DEFAULT_STYLE = {"id": "strict", "name": "严谨正式", "promptRef": "styles.json#strict"}
DEFAULT_LAYOUT = {
    "preset": "single-column", "palette": "deep-indigo",
    "cover": "full-block", "decoration": "standard", "font": "gov-gongwen",
    "imageRatio": "mid", "imageRule": "hybrid", "imageLayout": "split-h",
    "pageSetup": "p1-standard-a4", "headingSystem": "h1-gbt-arabic",
    "tocStyle": "t1-jianyu-auto", "tableStyle": "tb1-three-line",
    "captionSystem": "c2-cy-chapter", "paragraphStyle": "pa7-jianyu-15",
    "headerFooter": "hf1-classic-enterprise",
}
# 暗标默认注入：微观六组 + 页眉页脚按招标条款自动匹配（默认占位为多地区通行值，条款解析后须覆盖）
DARK_LAYOUT_INJECT = {
    "font": "dark-safe",
    "imageRatio": "none",
    "pageSetup": "p7-hb-25-20",
    "headingSystem": "h2-tender-arabic",
    "tocStyle": "t3-qinghai-nopage",
    "tableStyle": "tb7-dark-0.5",
    "captionSystem": "c9-dark-appendix",
    "paragraphStyle": "pa3-hebei-30",
    "headerFooter": "hf9-dark-none",
}

RE_PAGES = [
    re.compile(r"(?:不超过|不得超过|不多于|最多)\s*(\d+)\s*页"),
    re.compile(r"(\d+)\s*页(?:以内|以下|之内)"),
    re.compile(r"页数[^0-9\n]{0,8}(\d+)\s*页"),
]


# ---------------------------------------------------------------------------
# CLI 公共路径
# ---------------------------------------------------------------------------
def lib_root(args):
    root = args.root or os.environ.get("BIDCRAFT_LIB_ROOT") or os.path.join(os.getcwd(), "素材库")
    return Path(root)


def get_ent(args):
    return core.Library(lib_root(args)).resolve(getattr(args, "enterprise", None))


def proj_dir(ent, project):
    pd = Path(ent) / "项目级" / project
    if not pd.is_dir():
        raise core.LibraryError("项目目录不存在：%s（请先完成 M4 招标解析）" % pd)
    return pd


def ensure_inside(label, p, proj_dir_path):
    """数据源项目内硬校验：resolve 后必须位于本项目目录内。"""
    rp = Path(p).resolve()
    pd = Path(proj_dir_path).resolve()
    try:
        rp.relative_to(pd)
    except ValueError:
        raise core.LibraryError("%s 越界：%s 不在项目目录 %s 内（禁止跨项目）" % (label, rp, pd))
    return rp


def tdir(args, proj):
    base = Path(getattr(args, "tdir", "") or (Path(proj) / "招标解析"))
    base = ensure_inside("招标解析目录", base, proj)
    if not base.is_dir():
        raise core.LibraryError("招标解析目录不存在：%s" % base)
    return base


def tech_dir(ent, project):
    from . import store
    tech = store.tech_path(ent, project)
    if not tech.is_dir():
        raise core.LibraryError("技术标目录不存在：%s（请先 tech-init）" % tech)
    return tech


# ---------------------------------------------------------------------------
# M4 产物读取
# ---------------------------------------------------------------------------
def load_points(tdir_path, project):
    p = Path(tdir_path) / ("%s.json" % t_rules.points_base(project))
    if not p.is_file():
        raise core.LibraryError("投标要点 JSON 不存在：%s（M6 依赖 M4 产物，先执行 M4 招标解析）" % p)
    doc = core.read_json(str(p), None)
    if not isinstance(doc, dict):
        raise core.LibraryError("投标要点 JSON 无法读取：%s" % p)
    return doc


def module(points, mid):
    for m in (points.get("modules") or []):
        if isinstance(m, dict) and m.get("id") == mid:
            return m
    return None


def scoring_items(points):
    mod = module(points, "scoring")
    if not mod:
        raise core.LibraryError("投标要点缺少 scoring（评分办法）模块，M6 无法编制技术标")
    items = mod.get("score_items")
    if not isinstance(items, list) or not items:
        raise core.LibraryError("scoring 模块缺少 score_items（评分项明细），M6 无法编制技术标")
    return items


def field_values(points, mid):
    mod = module(points, mid) or {}
    fields = mod.get("fields") or {}
    out = {}
    for k, v in fields.items():
        if isinstance(v, dict) and isinstance(v.get("value"), str):
            out[k] = v["value"]
        elif isinstance(v, str):
            out[k] = v
    return out


def non_scoring_text(points):
    """页数/暗标约束抽取文本：排除 scoring（避免「每项不超过10页」误当总页数）。"""
    mods = [m for m in (points.get("modules") or []) if isinstance(m, dict) and m.get("id") != "scoring"]
    return json.dumps(mods, ensure_ascii=False)


def load_material(tdir_path, project):
    p = Path(tdir_path) / ("%s.json" % t_rules.list_base(project))
    if not p.is_file():
        return None
    doc = core.read_json(str(p), None)
    return doc if isinstance(doc, dict) else None


# ---------------------------------------------------------------------------
# 设置推导
# ---------------------------------------------------------------------------
def _find_pages(text):
    for pat in RE_PAGES:
        m = pat.search(text or "")
        if m:
            try:
                n = int(m.group(1))
            except (TypeError, ValueError):
                continue
            if n > 0:
                return n
    return None


def _page_constraint(points, tdir_path, project, pages=None):
    if pages:
        return {"max": int(pages), "charsPerPage": DEFAULT_CHARS_PER_PAGE,
                "source": "命令行 --pages"}
    fmt = Path(tdir_path) / ("响应文件格式_%s.txt" % project)
    if fmt.is_file():
        try:
            n = _find_pages(fmt.read_text(encoding="utf-8"))
        except OSError:
            n = None
        if n:
            return {"max": n, "charsPerPage": DEFAULT_CHARS_PER_PAGE,
                    "source": "响应文件格式_%s.txt" % project}
    n = _find_pages(non_scoring_text(points))
    if n:
        return {"max": n, "charsPerPage": DEFAULT_CHARS_PER_PAGE,
                "source": "投标要点（非评分模块）"}
    return {"max": DEFAULT_MAX_PAGES, "charsPerPage": DEFAULT_CHARS_PER_PAGE,
            "source": "默认值（未从招标文件抽取到页数约束）"}


def _bid_mode(points, override=None):
    if override:
        return override
    return "暗标" if "暗标" in json.dumps(points, ensure_ascii=False) else "明标"


def _terminology(project, points):
    basic = field_values(points, "basic")

    def pick(*keys):
        for k in keys:
            v = basic.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
        return ""

    return {
        "招标人": pick("采购人", "招标人") or "{{待填:招标人}}",
        "项目名称": pick("项目名称") or project,
        "服务期": pick("服务期") or "{{待填:服务期}}",
    }


def _personnel(material, notes):
    out = []
    for i, p in enumerate((material or {}).get("personnel") or []):
        if not isinstance(p, dict):
            continue
        name = (p.get("name") or "").strip()
        post = (p.get("post") or p.get("role") or "").strip()
        if name and post:
            out.append({"name": name, "post": post,
                        "source": "素材清单#personnel[%d]" % i})
        elif name:
            notes.append("素材清单 personnel[%d]（%s）缺岗位，已跳过（不臆造岗位）" % (i, name))
    return out


def build_settings(project, points, tdir_path, bid_mode=None, pages=None):
    """从 M4 产物推导技术标设置（tech-init 落盘 / tech-outline 兜底）。"""
    notes = []
    material = load_material(tdir_path, project)
    if material is None:
        notes.append("素材清单缺失（招标解析/%s.json）——tech-ctx 人员为空，正文只写岗位"
                     % t_rules.list_base(project))
    elif not (material.get("personnel") or []):
        notes.append("素材清单无 personnel——正文只写岗位不写姓名")
    personnel = _personnel(material, notes)
    term = _terminology(project, points)
    for k, v in term.items():
        if v.startswith("{{待填"):
            notes.append("术语 %s 未能从投标要点取得，已保留占位待补" % k)
    mode = _bid_mode(points, bid_mode)
    pc = _page_constraint(points, tdir_path, project, pages)
    if pc["source"].startswith("默认值"):
        notes.append("未抽取到页数约束，暂按 %d 页处理（可 tech-init --pages 覆盖）" % pc["max"])
    layout = dict(DEFAULT_LAYOUT)
    if mode == "暗标":
        for k, v in DARK_LAYOUT_INJECT.items():
            layout[k] = v
        notes.append("暗标：微观排版六组 + 页眉页脚已按通用条款注入默认（%s），具体以招标原文为准，条款解析后须覆盖"
                     % "、".join(sorted(DARK_LAYOUT_INJECT)))
    return {
        "schema": SETTINGS_SCHEMA,
        "project": project,
        "bidMode": mode,
        "pageConstraint": pc,
        "style": dict(DEFAULT_STYLE),
        "layout": layout,
        "terminology": term,
        "personnel": personnel,
        "personnelWriteMode": "post-only" if mode == "暗标" else "with-name",
        "notes": notes,
    }


def read_settings(tech, project):
    from . import store
    p = Path(tech) / SETTINGS_FILE
    if not p.is_file():
        return None
    obj = store.read_json_inside(tech, SETTINGS_FILE)
    if not isinstance(obj, dict) or obj.get("project") != project:
        return None
    return obj


def sensitive_vocab(ent, tree):
    """A4 词表：企业名（企业目录名）+ 素材清单人员姓名 + 暗标口径。"""
    return {
        "enterprise_names": [Path(ent).name],
        "brands": [],
        "addresses": [],
        "persons": [p.get("name") for p in (tree.get("personnel") or [])
                    if isinstance(p, dict) and p.get("name")],
        "personnelWriteMode": "post-only" if tree.get("bidMode") == "暗标" else "with-name",
    }
