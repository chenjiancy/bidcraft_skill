# -*- coding: utf-8 -*-
"""
bidcraft · M6 技术标制作 —— 排版预设读取与 tech-layout 命令（T13，契约 §3.2/§7）

预设文件：共享级 `<软件根>/共享资源/技术标风格/layout-presets.json`
  十五组均为数组（可增行表，全部统一为 10 套）：presets / palettes / covers / decorations / fontSchemes / imageRatios / imageRules / imageLayouts / pageSetups / headingSystems / tocStyles / tableStyles / captionSystems / paragraphStyles / headerFooters
缺失时：回退 `rules.DEFAULT_LAYOUT` 内置清单，并在输出中标注「内置兜底」
`--preview`：样张 docx 依赖 T10 导出排版引擎，未实现前显式报错（不静默跳过）
"""
import json

from _shared import core

from . import rules as m6rules
from . import sources

PRESETS_FILE = "layout-presets.json"
PRESETS_SCHEMA = "m6.layout-presets/v1"
GROUPS = (
    ("preset", "版面范式"),
    ("palette", "配色方案"),
    ("cover", "封面版式"),
    ("decoration", "装饰强度"),
    ("font", "字体方案"),
    ("imageRatio", "图文比例"),
    ("imageRule", "配图规则"),
    ("imageLayout", "配图排版"),
    ("pageSetup", "页面设置"),
    ("headingSystem", "标题体系"),
    ("tocStyle", "目录版式"),
    ("tableStyle", "表格样式"),
    ("captionSystem", "图表编号"),
    ("paragraphStyle", "段落样式"),
    ("headerFooter", "页眉页脚"),
)


# ---------------------------------------------------------------------------
# 读取
# ---------------------------------------------------------------------------
def find_presets(args):
    """→ 预设文件路径；共享资源在素材库根或其父目录下均可见（对齐 ctxpack 风格库）。"""
    root = sources.lib_root(args)
    for base in (root / "共享资源" / "技术标风格", root.parent / "共享资源" / "技术标风格"):
        p = base / PRESETS_FILE
        if p.is_file():
            return p
    return None


def load_presets(args):
    """读排版预设 → dict；文件缺失返回 None（调用方回退内置清单）。"""
    p = find_presets(args)
    if p is None:
        return None
    doc = core.read_json(str(p), None)
    if not isinstance(doc, dict):
        raise core.LibraryError("排版预设无法解析为 JSON 对象：%s" % p)
    return doc


def entries(doc, group):
    """某一组预设 → [{id, name, ...}]；兼容数组 / 对象数组 / dict 三写法。"""
    src = doc if isinstance(doc, dict) else {}
    for key in m6rules.LAYOUT_ALIAS_KEYS[group]:
        val = src.get(key)
        out = []
        if isinstance(val, list):
            for v in val:
                if isinstance(v, str):
                    out.append({"id": v, "name": v})
                elif isinstance(v, dict) and isinstance(v.get("id"), str) and v["id"]:
                    out.append(v)
        elif isinstance(val, dict):
            for k, v in val.items():
                if isinstance(k, str) and k:
                    out.append(dict(v, id=k) if isinstance(v, dict) else {"id": k, "name": k})
        if out:
            return out
    return [{"id": i, "name": i} for i in m6rules.DEFAULT_LAYOUT[group]]


def default_entry(doc):
    """十五组默认 id → {preset, palette, cover, decoration, font, imageRatio, imageRule, imageLayout, pageSetup, headingSystem, tocStyle, tableStyle, captionSystem, paragraphStyle, headerFooter}。"""
    out = dict(sources.DEFAULT_LAYOUT)
    src = doc.get("default") if isinstance(doc, dict) else None
    if isinstance(src, dict):
        for g, _ in GROUPS:
            v = src.get(g)
            if isinstance(v, str) and v.strip():
                out[g] = v.strip()
    return out


def palette_colors(doc, palette_id):
    """配色 → {id,name,primary,accent,heading,tableFill,coverBg[,coverBgEnd]}；未命中 None。"""
    for row in entries(doc, "palette"):
        if row.get("id") == palette_id:
            return row
    return None


def _name(doc, group, pid):
    for row in entries(doc, group):
        if row.get("id") == pid:
            return row.get("name") or pid
    return pid


# ---------------------------------------------------------------------------
# tech-layout
# ---------------------------------------------------------------------------
def _print_group(doc, group, label, default):
    rows = entries(doc, group)
    print("\n【%s · %d 种】" % (label, len(rows)))
    for row in rows:
        rid = row.get("id")
        name = row.get("name") or rid
        mark = " [默认]" if rid == default.get(group) else ""
        print("  %-18s %-10s%s" % (rid, name, mark))
        if group == "palette":
            colors = " ".join(row.get(k, "-") for k in
                              ("primary", "accent", "heading", "tableFill", "coverBg"))
            print("  %-18s %s" % ("", colors))
            flags = []
            if row.get("coverBgEnd"):
                flags.append("coverBgEnd=%s（两段近似）" % row["coverBgEnd"])
            if row.get("recommendedFor"):
                flags.append("推荐 %s" % "/".join(row["recommendedFor"]))
            if row.get("note"):
                flags.append(row["note"])
            if flags:
                print("  %-18s %s" % ("", "；".join(flags)))
        elif group == "font":
            parts = []
            for k in ("heading", "body", "western"):
                v = row.get(k)
                if isinstance(v, str) and v:
                    parts.append("%s=%s" % (k, v))
            if row.get("lineSpacing"):
                parts.append("行距%s" % row["lineSpacing"])
            if row.get("system"):
                parts.append(row["system"])
            if row.get("note"):
                parts.append(row["note"])
            if parts:
                print("  %-18s %s" % ("", " · ".join(parts)))
            sizes = row.get("sizes")
            if isinstance(sizes, dict) and sizes:
                print("  %-18s 字号：%s" % ("", " · ".join("%s %s" % (k, v) for k, v in sizes.items())))
        elif group == "cover" and row.get("darkOk") is False:
            print("  %-18s %s" % ("", row.get("note") or "暗标禁用"))
        elif group in ("imageRatio", "imageRule", "imageLayout"):
            flags = []
            if row.get("ratio"):
                flags.append("图:文 %s" % row["ratio"])
            if row.get("source"):
                flags.append("来源 %s" % row["source"])
            if row.get("darkOk") is False:
                flags.append("暗标禁用")
            if row.get("note"):
                flags.append(row["note"])
            print("  %-18s %s" % ("", "；".join(flags)))
        elif group in ("pageSetup", "headingSystem", "tocStyle", "tableStyle",
                       "captionSystem", "paragraphStyle", "headerFooter"):
            flags = []
            for k in ("margin", "gutter", "levels", "numbering", "title", "leading",
                      "lines", "headerFill", "figPos", "tablePos", "indent",
                      "lineSpacing", "align", "header", "footer", "pageMode"):
                v = row.get(k)
                if isinstance(v, str) and v:
                    flags.append(v)
            if row.get("darkOk") is False:
                flags.append("暗标禁用")
            if row.get("note"):
                flags.append(row["note"])
            print("  %-18s %s" % ("", "｜".join(flags)))
        elif row.get("docx"):
            print("  %-18s %s" % ("", row["docx"]))


def cmd_tech_layout(args):
    if getattr(args, "preview", ""):
        raise core.LibraryError(
            "tech-layout --preview=%s 依赖 T10 导出排版引擎（样张 docx），尚未实现；"
            "当前可用 tech-layout --list" % args.preview)
    path = find_presets(args)
    doc = load_presets(args)
    fallback = doc is None
    default = default_entry(doc)

    if getattr(args, "json", False):
        print(json.dumps({
            "source": str(path) if path else "",
            "fallback": fallback,
            "default": default,
            "groups": {g: entries(doc, g) for g, _ in GROUPS},
        }, ensure_ascii=False, indent=2))
        return 0

    if fallback:
        print("⚠ 未找到共享级排版预设（%s），已回退内置清单" % PRESETS_FILE)
    else:
        print("排版预设 · %s" % path)
    print("默认：%s %s / %s %s / %s %s / %s %s / 图文 %s(%s)：%s + %s + %s / 微观 %s(%s) %s(%s) %s(%s) %s(%s) %s(%s) %s(%s) / 页眉页脚 %s(%s)" % (
        default["preset"], _name(doc, "preset", default["preset"]),
        default["palette"], _name(doc, "palette", default["palette"]),
        default["cover"], _name(doc, "cover", default["cover"]),
        default["decoration"], _name(doc, "decoration", default["decoration"]),
        default.get("font", "gov-gongwen"), _name(doc, "font", default.get("font", "gov-gongwen")),
        _name(doc, "imageRatio", default.get("imageRatio", "mid")),
        _name(doc, "imageRule", default.get("imageRule", "hybrid")),
        _name(doc, "imageLayout", default.get("imageLayout", "split-h")),
        default.get("pageSetup", "p1-standard-a4"), _name(doc, "pageSetup", default.get("pageSetup", "p1-standard-a4")),
        default.get("headingSystem", "h1-gbt-arabic"), _name(doc, "headingSystem", default.get("headingSystem", "h1-gbt-arabic")),
        default.get("tocStyle", "t1-jianyu-auto"), _name(doc, "tocStyle", default.get("tocStyle", "t1-jianyu-auto")),
        default.get("tableStyle", "tb1-three-line"), _name(doc, "tableStyle", default.get("tableStyle", "tb1-three-line")),
        default.get("captionSystem", "c2-cy-chapter"), _name(doc, "captionSystem", default.get("captionSystem", "c2-cy-chapter")),
        default.get("paragraphStyle", "pa7-jianyu-15"), _name(doc, "paragraphStyle", default.get("paragraphStyle", "pa7-jianyu-15")),
        default.get("headerFooter", "hf1-classic-enterprise"), _name(doc, "headerFooter", default.get("headerFooter", "hf1-classic-enterprise"))))
    for group, label in GROUPS:
        _print_group(doc, group, label, default)
    print("\n提示：暗标禁用 cover=image-underlay；渐变蓝青在 docx 中以两段色块近似。")
    print("      章节树 layout 十五组 id 须在上表内（tech-outline 落盘前校验；暗标强制 font=dark-safe、图片二选一：none 或 dark-safe-img+appendix、页眉页脚二选一：hf9/hf10；微观六组按招标条款自动注入、不开放选择）。")
    return 0
