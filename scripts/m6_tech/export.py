# -*- coding: utf-8 -*-
"""
bidcraft · M6 技术标制作 —— T10 `tech-export`：合并 md → docx 导出排版引擎（契约 §3.2/§4/§7，T10/T13）

输入：
  1. 章节树（`技术标/m6.tree/v1`，tech-outline 产物；含各章 files.body 与 layout 预设组合）
  2. 各章正文（md，tech-parse 落盘；支持 #~###### 标题 / | 表格 / - 列表 / ![图题](路径)）
  3. 排版预设（共享级 `共享资源/技术标风格/layout-presets.json`，十五组 × 10 套）
  4. 上下文包（`章节/.meta/ch-xx.json`，供暗标判定与页数预算参考）

输出：
  `技术标/产出/技术标_<项目>.docx`（页面设置 / 封面 / 目录 TOC 域 / 标题体系 / 段落样式 /
  三线表 / 页眉页脚 pageMode 三态）+ `.meta/export.json`（预设组合 / 暗标 / 页数估算回写）

暗标（契约 §3.1 / D5 / dark-bid-page-number-routing 经验）：
  --bid-mode 显式声明，或章节树 layout.font=dark-safe 推断；暗标不开放风格选择——
  强制 font=dark-safe（宋体四号常规、全黑、不加粗/斜体/下划线/加色）、无封面、decoration=none、
  headerFooter 强制 hf9（无页码无页眉页脚）除非 --override headerFooter=hf10（页码双态按招标条款）。

验收（契约 §4）：docx 可被 python-docx 打开 + 段落数 > 0 + 目录域存在 + 页数估算回写。
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from _shared import core

from . import layout as layout_mod
from . import sources, store

EXPORT_SCHEMA = "m6.export/v1"

# 暗标双态页码：hf9=无页码（青海/海南/贵州/济南主流），hf10=仅页码（通辽 -N- / 雄县 Times 小五居中）
DARK_HF_NO_PAGE = "hf9-dark-none"
DARK_HF_PAGE_ONLY = "hf10-dark-page-only"

_MD_TABLE_ROW = re.compile(r"^\s*\|(.+)\|\s*$")
_MD_IMG = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")


# ---------------------------------------------------------------------------
# 预设解析
# ---------------------------------------------------------------------------
def _parse_margin(text):
    """'上2.54 下2.54 左3.18 右3.18cm' / '上3 下3 左2.6 右2.6cm' → [上,下,左,右] Cm。"""
    out = {"上": 2.54, "下": 2.54, "左": 3.18, "右": 3.18}
    if not isinstance(text, str):
        return out
    for m in re.finditer(r"(上|下|左|右)([\d.]+)", text):
        try:
            out[m.group(1)] = float(m.group(2))
        except ValueError:
            pass
    return out


def _parse_gutter(text):
    """'装订线0' / '装订线1.5' → 左侧装订增量 Cm（并入左边距）。"""
    if not isinstance(text, str):
        return 0.0
    m = re.search(r"装订线([\d.]+)", text)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return 0.0
    return 0.0


def _font_of_level_text(seg):
    """从 '章小4黑体' / '一级三号黑体非斜' / '标题正文宋体四号常规' 提取 (Pt, 字体名, bold)。"""
    size = None
    m = re.search(r"([\d.]+)pt", seg)
    if not m:
        for k in ("小四", "小5", "四号", "三号", "小三", "五号", "小五", "二号", "小二", "六号"):
            if k in seg:
                size = _pt(k)
                break
    else:
        size = Pt(float(m.group(1)))
    if size is None:
        size = Pt(12)
    bold = "加粗" in seg or "黑体（加粗）" in seg
    font = None
    for k in ("微软雅黑", "华文中宋", "仿宋_GB2312", "仿宋", "楷体", "黑体", "宋体"):
        if k in seg:
            font = k
            break
    return size, font, bold


def _parse_heading_system(levels_text):
    """'章小4黑体 节5号黑体 正文5号宋体' / '一、小四黑体 1.五号黑体 (1)三级' → {level: (Pt, font, bold), body: (...)}"""
    out = {}
    body = None
    if not isinstance(levels_text, str):
        return out, body
    # 按级别词分段：章/节/段/正文/一级…六级/阿拉伯编号/中文编号
    segs = re.split(r"(?=章|节|段|正文|一级|二级|三级|四级|五级|六级|1[.、]|\(1\)|（一）|一、)", levels_text)
    for seg in segs:
        seg = seg.strip()
        if not seg:
            continue
        size, font, bold = _font_of_level_text(seg)
        lvl = None
        if "正文" in seg:
            body = (size, font, bold)
            continue
        for k, v in (("一级", 1), ("二级", 2), ("三级", 3), ("四级", 4), ("五级", 5), ("六级", 6), ("章", 1), ("节", 2), ("段", 3)):
            if k in seg:
                lvl = v
                break
        if lvl is None:
            for pat, v in (("1[.、]", 1), ("（一）", 2), ("(1)", 3), ("1.1.1", 3), ("1.1", 2)):
                if re.search(pat, seg):
                    lvl = v
                    break
        if lvl is None:
            lvl = 1
        out[lvl] = (size, font, bold)
    return out, body


_NUM_STYLES = ("arabic", "chinese-first", "seven", "tongliao-arabic", "no-number")


def _parse_numbering(numbering_text):
    """'1 / 2.1 / 3.2.1 顶格+空1字，≤4级' → (style, max_level)。"""
    if not isinstance(numbering_text, str):
        return "arabic", 4
    style = "arabic"
    max_level = 4
    if "一、" in numbering_text and "（一）" in numbering_text and "1." in numbering_text:
        style = "seven"
    elif "一、" in numbering_text and "1." in numbering_text:
        style = "chinese-first"
    elif "一、" in numbering_text and "1.1" in numbering_text:
        style = "chinese-first"
    elif "1、" in numbering_text:
        style = "tongliao-arabic"
    m = re.search(r"≤?(\d+)\s*级|最多(\d+)级|(\d+)\s*级", numbering_text)
    if m:
        max_level = int((m.group(1) or m.group(2) or m.group(3) or 4))
    return style, max_level


def _heading_prefix(style, counters, level):
    """按编号风格生成标题前缀。counters[1..] 每级计数；调用方先递增再生成。"""
    if style == "no-number":
        return ""
    if style == "seven":
        seq = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十"]
        cn = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十"]
        if level == 1:
            return cn[counters[1] - 1] + "、"
        if level == 2:
            return "（" + cn[counters[2] - 1] + "）"
        if level == 3:
            return "%d." % counters[3]
        if level == 4:
            return "（%d）" % counters[4]
        if level == 5:
            return "%d）" % counters[5]
        return ""
    if style == "chinese-first":
        if level == 1:
            return ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十"][counters[1] - 1] + "、"
        return ".".join(str(counters[i]) for i in range(2, level + 1)) + "."
    if style == "tongliao-arabic":
        if level == 1:
            return "%d、" % counters[1]
        return ".".join(str(counters[i]) for i in range(1, level + 1)) + "."
    # arabic：1 / 1.1 / 1.1.1
    return ".".join(str(counters[i]) for i in range(1, level + 1)) + "."


def _parse_table_style(lines_text, header_fill=""):
    """'顶线底线1.5磅 表头线1磅 无竖线' → dict(outer_pt, header_pt, vertical, inner_pt, header_fill)。"""
    out = {"outer": 1.5, "header": 1.0, "vertical": False, "inner": 1.0,
           "header_fill": None, "kind": "three-line"}
    if not isinstance(lines_text, str):
        return out
    if "全框" in lines_text or "全线" in lines_text or "表框线+行线+栏线" in lines_text or "0.5pt" in lines_text and "竖线" not in lines_text:
        out["kind"] = "full"
        out["outer"] = 0.5 if "0.5" in lines_text else 1.0
        out["inner"] = 0.5
        out["vertical"] = True
    elif "无线" in lines_text or "无框线" in lines_text:
        out["kind"] = "none"
    elif "省线" in lines_text:
        out["kind"] = "saving"
        out["inner"] = 1.0
    elif "顶线底线" in lines_text:
        out["kind"] = "three-line"
    m = re.search(r"顶线底线([\d.]+)磅", lines_text)
    if m:
        out["outer"] = float(m.group(1))
    m = re.search(r"表头线([\d.]+)磅", lines_text)
    if m:
        out["header"] = float(m.group(1))
    if "无竖线" in lines_text or "无栏线" in lines_text:
        out["vertical"] = False
    if isinstance(header_fill, str):
        if "底纹" in header_fill and "无" not in header_fill[:2]:
            out["header_fill"] = "palette"
        elif "无" in header_fill:
            out["header_fill"] = None
    return out


def _parse_caption(caption_row):
    """captionSystem 行 → dict(fig_pos, table_pos, seq_mode, prefix)。"""
    out = {"fig_pos": "below", "table_pos": "above", "seq_mode": "seq", "fig_prefix": "图", "table_prefix": "表"}
    if not isinstance(caption_row, dict):
        return out
    fig_pos = caption_row.get("figPos") or ""
    table_pos = caption_row.get("tablePos") or ""
    if "表上" in fig_pos:
        out["fig_pos"] = "above"
    if "图下" in table_pos:
        out["table_pos"] = "below"
    numbering = caption_row.get("numbering") or ""
    if "分章" in numbering or "1-1" in numbering or "1.1" in numbering or "按一级标题连续" in numbering:
        out["seq_mode"] = "chapter"
    if "附录" in numbering:
        out["fig_prefix"] = "附图"
        out["table_prefix"] = "附表"
    return out


def _parse_toc(toc_row):
    """tocStyle 行 → dict(title_size, title_bold, page, max_level)。"""
    out = {"title_size": Pt(16), "title_bold": True, "page": True, "max_level": 3}
    if not isinstance(toc_row, dict):
        return out
    title = toc_row.get("title") or ""
    if "三号" in title:
        out["title_size"] = Pt(16)
    elif "四号" in title:
        out["title_size"] = Pt(14)
    if "加粗" in title:
        out["title_bold"] = True
    leading = toc_row.get("leading") or ""
    if "无页码" in leading or "不得标页码" in leading:
        out["page"] = False
    levels = toc_row.get("levels") or ""
    m = re.search(r"(\d+)[-到至](\d+)\s*级|(\d+)\s*级", levels)
    if m:
        out["max_level"] = int(m.group(2) or m.group(3) or 3)
    if "两级" in levels:
        out["max_level"] = 2
    if "3-4级" in levels:
        out["max_level"] = 4
    return out


def _pt(s):
    """'16pt' → Pt(16)；'三号' → 16pt 映射；'小四' → 12pt；'四号'→14；'五号'→10.5；'小五'→9。"""
    if not isinstance(s, str):
        return Pt(12)
    s = s.strip()
    m = re.match(r"([\d.]+)pt", s)
    if m:
        return Pt(float(m.group(1)))
    table = {"初号": 42, "小初": 36, "一号": 26, "小一": 24, "二号": 22, "小二": 18,
             "三号": 16, "小三": 15, "四号": 14, "小四": 12, "五号": 10.5, "小五": 9,
             "六号": 7.5, "小六": 6.5}
    for k, v in table.items():
        if k in s:
            return Pt(v)
    return Pt(12)


def _heading_size(sizes, key, default=14):
    if isinstance(sizes, dict):
        for k, v in sizes.items():
            if key in k:
                return _pt(v)
    return _pt(str(default))


def resolve_presets(args, doc, tree_layout=None):
    """→ dict(全 15 组 id)；优先级：--override 显式 > 章节树 layout > 预设 default。"""
    out = layout_mod.default_entry(doc)
    if isinstance(tree_layout, dict):
        for g, _ in layout_mod.GROUPS:
            v = tree_layout.get(g)
            if isinstance(v, str) and v.strip():
                out[g] = v.strip()
    ov = getattr(args, "override", "") or ""
    for seg in ov.split(";"):
        if "=" not in seg:
            continue
        k, v = seg.split("=", 1)
        k, v = k.strip(), v.strip()
        if k in out and v:
            out[k] = v
    return out


# ---------------------------------------------------------------------------
# docx 原语
# ---------------------------------------------------------------------------
def _set_font(run, font_cfg, size=Pt(12), color=None, bold=None, east="黑体", western="Times New Roman"):
    run.font.size = size
    if color is not None:
        run.font.color.rgb = color
    if bold is not None:
        run.font.bold = bold
    run.font.name = western or "Times New Roman"
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    rfonts.set(qn("w:ascii"), western or "Times New Roman")
    rfonts.set(qn("w:hAnsi"), western or "Times New Roman")
    rfonts.set(qn("w:eastAsia"), east or font_cfg or "宋体")


def _shade(el, fill):
    """给段落/单元格加底纹。"""
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill.lstrip("#"))
    el.get_or_add_pPr() if hasattr(el, "get_or_add_pPr") else None
    try:
        if hasattr(el, "get_or_add_pPr"):
            el.get_or_add_pPr().append(shd)
        elif hasattr(el, "get_or_add_tcPr"):
            el.get_or_add_tcPr().append(shd)
    except Exception:
        pass


def _add_field(paragraph, instr, placeholder="TOC 目录（打开文档后按 F9 或 Ctrl+A → F9 更新）"):
    run = paragraph.add_run()
    fld1 = OxmlElement("w:fldChar"); fld1.set(qn("w:fldCharType"), "begin")
    instr_el = OxmlElement("w:instrText"); instr_el.set(qn("xml:space"), "preserve"); instr_el.text = instr
    fld2 = OxmlElement("w:fldChar"); fld2.set(qn("w:fldCharType"), "separate")
    run._r.append(fld1)
    run._r.append(instr_el)
    run._r.append(fld2)
    p = paragraph.add_run(placeholder)
    p.font.size = Pt(12)
    run2 = paragraph.add_run()
    fld3 = OxmlElement("w:fldChar"); fld3.set(qn("w:fldCharType"), "end")
    run2._r.append(fld3)


def _page_field(paragraph, fmt='- {PAGE} -', size=Pt(9)):
    """页脚 PAGE 域。fmt 支持 {PAGE} / {NUMPAGES}。"""
    run = paragraph.add_run()
    fld1 = OxmlElement("w:fldChar"); fld1.set(qn("w:fldCharType"), "begin")
    run._r.append(fld1)
    instr = OxmlElement("w:instrText"); instr.set(qn("xml:space"), "preserve")
    instr.text = "PAGE"
    run._r.append(instr)
    fld2 = OxmlElement("w:fldChar"); fld2.set(qn("w:fldCharType"), "end")
    run._r.append(fld2)
    paragraph.add_run(" - ").font.size = size


def _table_borders(table, top=12, header=8, bottom=12, inside_h=None):
    """三线表：顶线/底线 1.5pt(12 eighths? 用 half-points: 1.5pt=3)，表头线 1pt=2；无竖线。"""
    tbl = table._tbl
    tblPr = tbl.tblPr
    borders = tblPr.find(qn("w:tblBorders"))
    if borders is None:
        borders = OxmlElement("w:tblBorders")
        tblPr.append(borders)
    for edge, sz in (("top", top), ("bottom", bottom)):
        el = borders.find(qn("w:" + edge))
        if el is None:
            el = OxmlElement("w:" + edge)
            borders.append(el)
        el.set(qn("w:val"), "single"); el.set(qn("w:sz"), str(sz)); el.set(qn("w:color"), "000000")
    for edge in ("left", "right", "insideV"):
        el = borders.find(qn("w:" + edge))
        if el is None:
            el = OxmlElement("w:" + edge)
            borders.append(el)
        el.set(qn("w:val"), "none"); el.set(qn("w:sz"), "0")
    ih = borders.find(qn("w:insideH"))
    if ih is None:
        ih = OxmlElement("w:insideH")
        borders.append(ih)
    ih.set(qn("w:val"), "single" if inside_h else "none"); ih.set(qn("w:sz"), str(inside_h or 4))


def _header_line_after(section):
    """页眉下方 0.5pt 分隔线。"""
    p = section.header.paragraphs[0] if section.header.paragraphs else None
    if p is None:
        return
    pPr = p._p.get_or_add_pPr()
    pBdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single"); bottom.set(qn("w:sz"), "4")
    bottom.set(qn("w:color"), "808080")
    pBdr.append(bottom)
    pPr.append(pBdr)


def _table_borders_color(table, color="B7B7B7"):
    """给已建三线表统一改边框色（minimal-clean 极淡色表线）。"""
    tbl = table._tbl
    tblPr = tbl.tblPr
    borders = tblPr.find(qn("w:tblBorders"))
    if borders is None:
        return
    for edge in ("top", "bottom", "insideH", "left", "right", "insideV"):
        el = borders.find(qn("w:" + edge))
        if el is not None:
            el.set(qn("w:color"), color)


def _box_borders(table, color="C9D2E2", sz=4):
    """全边框（卡片式/数据行布局）。"""
    tbl = table._tbl
    tblPr = tbl.tblPr
    borders = tblPr.find(qn("w:tblBorders"))
    if borders is None:
        borders = OxmlElement("w:tblBorders")
        tblPr.append(borders)
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = borders.find(qn("w:" + edge))
        if el is None:
            el = OxmlElement("w:" + edge)
            borders.append(el)
        el.set(qn("w:val"), "single"); el.set(qn("w:sz"), str(sz)); el.set(qn("w:color"), color)


def _no_borders(table):
    """无边框表格（左图右文等版式容器）。"""
    tblPr = table._tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement("w:" + edge)
        el.set(qn("w:val"), "none")
        borders.append(el)
    tblPr.append(borders)


# ---------------------------------------------------------------------------
# 正文解析与渲染
# ---------------------------------------------------------------------------
class _Renderer:
    def __init__(self, doc, cfg, dark, colors, sizes, ps=None, preset="single-column",
                 font_row=None, heading_row=None, toc_row=None, table_row=None,
                 caption_row=None, decoration_row=None, image_layout="split-h",
                 image_share=0.3, image_rule=None):
        self.doc = doc
        self.cfg = cfg
        self.dark = dark
        self.colors = colors
        self.sizes = sizes
        self.ps = ps or {}
        # 版面范式：暗标一律退回单栏全黑（渲染层兜底，不依赖数据注入）
        self.preset = "single-column" if dark else (preset or "single-column")
        # —— 设计数据层全量接入 ——
        fr = font_row or {}
        self.font_heading = (fr.get("heading") or "黑体").split("（")[0].strip() or "黑体"
        self.font_body = (fr.get("body") or "宋体").split("（")[0].strip() or "宋体"
        self.font_western = fr.get("western") or "Times New Roman"
        try:
            self.line_spacing = float(fr.get("lineSpacing") or 1.5)
        except Exception:
            self.line_spacing = 1.5
        # 标题体系（levels 解析覆盖 sizes；编号风格）
        self.heading_levels, self.heading_body = _parse_heading_system(
            (heading_row or {}).get("levels") if isinstance(heading_row, dict) else None)
        self.num_style, self.num_max = _parse_numbering(
            (heading_row or {}).get("numbering") if isinstance(heading_row, dict) else None)
        self._hcount = {i: 0 for i in range(1, 7)}
        self._chapter_no = 0  # 分章题注编号
        # 目录样式
        toc = _parse_toc(toc_row)
        self.toc_title_size = toc["title_size"]
        self.toc_title_bold = toc["title_bold"]
        self.toc_page = toc["page"]
        self.toc_max_level = toc["max_level"]
        # 表格样式（线型/底纹）
        tr = table_row if isinstance(table_row, dict) else {}
        self.table_style = _parse_table_style(tr.get("lines"), tr.get("headerFill"))
        # 题注系统（图/表位置 + 编号模式）
        self.caption = _parse_caption(caption_row if isinstance(caption_row, dict) else None)
        # 装饰强度
        deco = (decoration_row or {}).get("id") if isinstance(decoration_row, dict) else "standard"
        if dark:
            deco = "none"
        self.decoration = deco or "standard"
        # 图文布局 / 图文比例 / 配图规则
        self.image_layout = "none" if dark else (image_layout or "split-h")
        self.image_share = 0.0 if dark else float(image_share or 0.3)
        self.image_rule = image_rule or "hybrid"
        self.table_no = 0
        self.fig_no = 0

    def begin_chapter(self, no):
        """进入第 no 章：分章题注用章号；图/表序号每章重置（仅分章编号模式）。"""
        self._chapter_no = no
        if (self.caption or {}).get("seq_mode") == "chapter":
            self.table_no = 0
            self.fig_no = 0
        self._last_list = False
        self._list_seq = 0
        # two-column：封面/目录之后新建正文节，设双栏（页眉页脚默认继承节 0）
        if self.preset == "two-column":
            self._open_two_column_section()

    def _open_two_column_section(self):
        """正文双栏：doc.add_section(NEW_PAGE) 后写 w:cols num=2。"""
        from docx.enum.section import WD_SECTION_START

        sec2 = self.doc.add_section(WD_SECTION_START.NEW_PAGE)
        sectPr = sec2._sectPr
        cols = sectPr.find(qn("w:cols"))
        if cols is None:
            cols = OxmlElement("w:cols")
            sectPr.append(cols)
        cols.set(qn("w:num"), "2")
        cols.set(qn("w:space"), "360")

    def _heading(self, level, text):
        # 编号：文本自身已带编号（一、/（一）/1.等）则不加前缀；否则按 headingSystem 编号风格自动编号
        prefix = ""
        if not self.dark and self.num_style != "no-number" and level <= self.num_max:
            if not re.match(r"^([一二三四五六七八九十]+、|（[一二三四五六七八九十]+）|\d+[.、]|\(\d+\))", text.strip()):
                self._hcount[level] += 1
                for k in range(level + 1, 7):
                    self._hcount[k] = 0
                prefix = _heading_prefix(self.num_style, self._hcount, level)
                if prefix:
                    prefix += "　"
        full = prefix + text
        # 字号/字体：标题体系 levels 优先，否则 sizes 默认
        lvl_cfg = self.heading_levels.get(level) if self.heading_levels else None
        if lvl_cfg is not None:
            size, hfont, hbold = lvl_cfg
        else:
            sizes = self.sizes or {}
            size = _heading_size(sizes, {1: "chapter", 2: "section", 3: "item", 4: "item", 5: "body", 6: "body"}.get(level, "body"), 14)
            hfont, hbold = None, None
        bold = False if self.dark else (hbold if hbold is not None else (level <= 2))
        color = None if self.dark else self.colors.get("heading")
        if self.decoration == "none" or self.decoration == "table-fill":
            color = None
        p = self.doc.add_paragraph()
        p.style = self.doc.styles["Normal"]
        pf = p.paragraph_format
        pf.space_before = Pt(6 if level <= 2 else 3)
        pf.space_after = Pt(4 if level <= 2 else 2)
        pf.line_spacing = 1.2
        if level <= 3:
            pf.keep_with_next = True
        pPr = p._p.get_or_add_pPr()
        # 装饰（按 decoration 方案；复用单一 pBdr 合并元素，避免重复节点）
        deco = self.decoration
        pBdr = None
        if deco in ("heading-rule", "standard") and not self.dark and level <= 3:
            pBdr = OxmlElement("w:pBdr")
            bottom = OxmlElement("w:bottom")
            bottom.set(qn("w:val"), "single"); bottom.set(qn("w:sz"), "6")
            bottom.set(qn("w:color"), str(self.colors.get("primary", RGBColor.from_string("1B2C52"))))
            pBdr.append(bottom)
        if deco == "sidebar-tab" and not self.dark and level <= 3:
            pf.left_indent = Pt(14)
            if pBdr is None:
                pBdr = OxmlElement("w:pBdr")
            left = OxmlElement("w:left")
            left.set(qn("w:val"), "single"); left.set(qn("w:sz"), "18")
            left.set(qn("w:color"), str(self.colors.get("primary", RGBColor.from_string("1B2C52"))))
            pBdr.append(left)
        if deco == "rich" and not self.dark and level <= 2:
            _shade(p._p, str(self.colors.get("tableFill", "E8ECF4")))
        if deco == "section-band" and not self.dark and level == 1:
            _shade(p._p, str(self.colors.get("primary", RGBColor.from_string("1B2C52"))))
            color = RGBColor(0xFF, 0xFF, 0xFF)
        # hybrid-flow：一二级标题左侧色条（范式装饰，独立于 decoration）
        if self.preset == "hybrid-flow" and level <= 2 and not self.dark:
            pf.left_indent = Pt(12)
            if pBdr is None:
                pBdr = OxmlElement("w:pBdr")
            left = OxmlElement("w:left")
            left.set(qn("w:val"), "single")
            left.set(qn("w:sz"), "12")
            left.set(qn("w:color"), str(self.colors.get("primary", RGBColor.from_string("1B2C52"))))
            pBdr.append(left)
        if pBdr is not None:
            pPr.append(pBdr)
        # 大纲级别（TOC 按 outlineLvl 收集；level 0-5 对应 H1-H6）
        lvl = OxmlElement("w:outlineLvl")
        lvl.set(qn("w:val"), str(max(0, level - 1)))
        pPr.append(lvl)
        # 图标点缀
        icon = ""
        if deco == "icon-accent" and not self.dark and level <= 2:
            icon = "■ "
        r = p.add_run(icon + full)
        # minimal-clean：标题不加粗、无装饰
        if self.preset == "minimal-clean" and not self.dark:
            bold = False
        east = hfont or self.font_heading
        _set_font(r, None, size=size, color=color, bold=bold, east=east,
                  western=self.font_western)
        return p

    def _body(self, text, indent=True):
        ps = self.ps
        line_spacing = None
        if ps:
            if "固定" in str(ps.get("lineSpacing") or "") or "固定" in str(ps.get("note") or ""):
                m = re.search(r"固定(\d+)磅", str(ps.get("lineSpacing") or "") + str(ps.get("note") or ""))
                if m:
                    try:
                        line_spacing = Pt(float(m.group(1)))
                    except Exception:
                        pass
        p = self.doc.add_paragraph()
        p.style = self.doc.styles["Normal"]
        pf = p.paragraph_format
        if indent:
            pf.first_line_indent = Pt(24) if not self.dark else Pt(28)  # 2 字符近似
        align = (ps or {}).get("align") or "两端对齐"
        pf.alignment = WD_ALIGN_PARAGRAPH.LEFT if ("左对齐" in align and "两端" not in align) else WD_ALIGN_PARAGRAPH.JUSTIFY
        if line_spacing is not None:
            pf.line_spacing = line_spacing
        else:
            try:
                pf.line_spacing = self.line_spacing
            except Exception:
                pf.line_spacing = 1.5
        pf.space_before = Pt(0); pf.space_after = Pt(0)
        r = p.add_run(text)
        if self.dark:
            size, east = Pt(14), "宋体"
        elif self.heading_body is not None:
            size, east = self.heading_body[0], self.heading_body[1] or self.font_body
        else:
            size, east = _heading_size(self.sizes, "body", 12), self.font_body
        _set_font(r, None, size=size, east=east, western=self.font_western)
        return p

    def _list(self, text):
        # 版面范式：tabular → 序号/内容数据行；card → 卡片单元格
        if self.preset == "tabular":
            self._list_row(self._list_seq, text)
            return
        if self.preset == "card":
            self._list_card(text)
            return
        if self.preset == "data-row":
            self._list_data_row(self._list_seq, text)
            return
        if self.preset == "hybrid-flow":
            # 混合流式：项目符号段落（与正文散排混排）
            p = self.doc.add_paragraph()
            p.style = self.doc.styles["Normal"]
            pf = p.paragraph_format
            pf.left_indent = Pt(24)
            pf.line_spacing = 1.5
            r0 = p.add_run("•  ")
            _set_font(r0, None, size=Pt(10.5), color=self.colors.get("primary"), east=self.font_body if not self.dark else "宋体")
            r = p.add_run(text)
            _set_font(r, None, size=_heading_size(self.sizes, "body", 12) if not self.dark else Pt(14),
                      east=self.font_body if not self.dark else "宋体", western=self.font_western)
            return
        if self.preset == "minimal-clean":
            # 极简留白：无符号普通段落（缩进 2 字）
            p = self.doc.add_paragraph(style="List Paragraph")
            pf = p.paragraph_format
            pf.left_indent = Pt(24)
            pf.line_spacing = 1.6
            pf.space_after = Pt(3)
            r = p.add_run(text)
            _set_font(r, None, size=Pt(12) if not self.dark else Pt(14),
                      east=self.font_body if not self.dark else "宋体", western=self.font_western)
            return
        p = self.doc.add_paragraph(style="List Bullet")
        pf = p.paragraph_format
        pf.line_spacing = self.line_spacing
        r = p.add_run(text)
        _set_font(r, None, size=_heading_size(self.sizes, "body", 12) if not self.dark else Pt(14),
                  east=self.font_body if not self.dark else "宋体", western=self.font_western)

    def _table(self, header_cells, rows, table_fill):
        self.table_no += 1
        ts = self.table_style
        cap_text = self._caption_text("table")
        table_pos_above = self.caption["table_pos"] == "above"
        if table_pos_above:
            self._caption_para(cap_text)
        table = self.doc.add_table(rows=1 + len(rows), cols=len(header_cells))
        table.alignment = 1  # center
        table.autofit = True
        # 表格线型（tableStyle 解析；minimal-clean 范式细线淡色优先）
        kind = ts["kind"]
        if self.preset == "minimal-clean":
            _table_borders(table, top=6, header=4, bottom=6, inside_h=2)
            _table_borders_color(table, "B7B7B7")
        elif kind == "full":
            _box_borders(table, "000000" if self.dark else "808080", int(ts["outer"] * 8))
        elif kind == "none":
            _no_borders(table)
        elif kind == "saving":
            _table_borders(table, top=int(ts["outer"] * 8), header=int(ts["header"] * 8),
                           bottom=int(ts["outer"] * 8), inside_h=int(ts["inner"] * 8))
        else:
            _table_borders(table, top=int(ts["outer"] * 8), header=int(ts["header"] * 8),
                           bottom=int(ts["outer"] * 8), inside_h=None)
        tbl_sz = _heading_size(self.sizes, "table", 10.5) if self.sizes else Pt(10.5)
        for j, h in enumerate(header_cells):
            cell = table.rows[0].cells[j]
            cell.text = ""
            para = cell.paragraphs[0]
            run = para.add_run(h)
            _set_font(run, None, size=tbl_sz, bold=not self.dark, east=self.font_body if not self.dark else "宋体",
                      western=self.font_western)
            if (ts["header_fill"] == "palette" or (self.preset in ("card", "tabular") and not self.dark)) and not self.dark:
                _shade(cell._tc, table_fill or "E8ECF4")
        for i, row in enumerate(rows):
            for j, v in enumerate(row):
                cell = table.rows[i + 1].cells[j]
                cell.text = ""
                run = cell.paragraphs[0].add_run(v)
                _set_font(run, None, size=tbl_sz, east=self.font_body if not self.dark else "宋体" if self.dark else self.font_body,
                          western=self.font_western)
        if not table_pos_above:
            self._caption_para(cap_text)

    def _caption_text(self, kind):
        """题注文本：编号模式（全文连续 / 分章 N-N）+ 前缀（表/图/附表/附图）。"""
        cap = self.caption
        if kind == "table":
            seq = self.table_no
            pre = cap.get("table_prefix", "表")
        else:
            seq = self.fig_no
            pre = cap.get("fig_prefix", "图")
        if cap.get("seq_mode") == "chapter" and self._chapter_no:
            return "%s%d-%d" % (pre, self._chapter_no, seq)
        return "%s%d" % (pre, seq)

    def _caption_para(self, text):
        cap = self.doc.add_paragraph()
        cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
        cap.paragraph_format.space_before = Pt(6)
        cap.paragraph_format.space_after = Pt(2)
        csz = _heading_size(self.sizes, "caption", 9) if self.sizes else Pt(9)
        r = cap.add_run(text)
        _set_font(r, None, size=csz, east=self.font_body if not self.dark else "宋体" if self.dark else self.font_body, western=self.font_western)
        return cap

    def _list_row(self, idx, text):
        """tabular（表格化，含增强：交替行底纹 + 序号加粗）：列表项 → 序号/内容双列数据行。"""
        table = self.doc.add_table(rows=1, cols=2)
        table.autofit = True
        _box_borders(table, "C9D2E2", 4)
        try:
            table.columns[0].width = Cm(1.4)
            table.columns[1].width = Cm(13.0)
        except Exception:
            pass
        c0 = table.rows[0].cells[0]
        c0.text = ""
        p0 = c0.paragraphs[0]
        p0.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r0 = p0.add_run(str(idx))
        _set_font(r0, None, size=Pt(10.5), bold=not self.dark, east=self.font_body if not self.dark else "宋体")
        _shade(c0._tc, self.colors.get("tableFill", "E8ECF4"))
        c1 = table.rows[0].cells[1]
        c1.text = ""
        r1 = c1.paragraphs[0].add_run(text)
        _set_font(r1, None, size=Pt(10.5), east=self.font_body if not self.dark else "宋体")
        # 增强：交替行底纹（奇数行浅蓝、偶数行白）区分数据行
        if idx % 2 == 1:
            _shade(c1._tc, self.colors.get("tableFill", "E8ECF4"))
        else:
            _shade(c1._tc, "FFFFFF")

    def _list_data_row(self, idx, text):
        """data-row：数据行 —— 序号格深色主底白字 + 内容格浅底纹，行间细线。"""
        table = self.doc.add_table(rows=1, cols=2)
        table.autofit = True
        _box_borders(table, "B9C4D8", 3)
        try:
            table.columns[0].width = Cm(1.1)
            table.columns[1].width = Cm(13.3)
        except Exception:
            pass
        c0 = table.rows[0].cells[0]
        c0.text = ""
        p0 = c0.paragraphs[0]
        p0.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r0 = p0.add_run(str(idx))
        _set_font(r0, None, size=Pt(10.5), bold=not self.dark,
                  color=RGBColor(0xFF, 0xFF, 0xFF) if not self.dark else None,
                  east=self.font_body if not self.dark else "宋体")
        if not self.dark:
            _shade(c0._tc, str(self.colors.get("primary", RGBColor.from_string("1B2C52"))))
        c1 = table.rows[0].cells[1]
        c1.text = ""
        r1 = c1.paragraphs[0].add_run(text)
        _set_font(r1, None, size=Pt(10.5), east=self.font_body if not self.dark else "宋体")
        _shade(c1._tc, "EFF3F9")

    def _list_card(self, text):
        """card：列表项 → 单列卡片（边框 + 浅底纹）。"""
        table = self.doc.add_table(rows=1, cols=1)
        table.autofit = True
        _box_borders(table, "B9C4D8", 6)
        cell = table.rows[0].cells[0]
        cell.text = ""
        p = cell.paragraphs[0]
        r = p.add_run(text)
        _set_font(r, None, size=Pt(10.5), east=self.font_body if not self.dark else "宋体")
        _shade(cell._tc, "F4F7FB")

    def _image_left(self, cap, src, right_text=""):
        """image-left：左图右文 1×2 无边框表格（左图，右图题+紧跟正文）。"""
        table = self.doc.add_table(rows=1, cols=2)
        table.autofit = True
        _no_borders(table)
        try:
            table.columns[0].width = Cm(7.6)
            table.columns[1].width = Cm(6.8)
        except Exception:
            pass
        c0 = table.rows[0].cells[0]
        p0 = c0.paragraphs[0]
        p0.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p0.add_run().add_picture(str(src), width=Cm(7.2))
        c1 = table.rows[0].cells[1]
        p1 = c1.paragraphs[0]
        r1 = p1.add_run("%s　%s" % (self._caption_text("fig"), cap))
        _set_font(r1, None, size=Pt(9), east=self.font_body if not self.dark else "宋体")
        if right_text:
            p2 = c1.add_paragraph()
            r2 = p2.add_run(right_text)
            _set_font(r2, None, size=_heading_size(self.sizes, "body", 12), east=self.font_body)

    def _image_right(self, cap, src, right_text=""):
        """image-right：右图左文 1×2 无边框表格（左图题+紧跟正文，右图）。"""
        table = self.doc.add_table(rows=1, cols=2)
        table.autofit = True
        _no_borders(table)
        try:
            table.columns[0].width = Cm(6.8)
            table.columns[1].width = Cm(7.6)
        except Exception:
            pass
        c0 = table.rows[0].cells[0]
        p0 = c0.paragraphs[0]
        r0 = p0.add_run("%s　%s" % (self._caption_text("fig"), cap))
        _set_font(r0, None, size=Pt(9), east=self.font_body if not self.dark else "宋体")
        if right_text:
            p1 = c0.add_paragraph()
            r1 = p1.add_run(right_text)
            _set_font(r1, None, size=_heading_size(self.sizes, "body", 12), east=self.font_body)
        c1 = table.rows[0].cells[1]
        p2 = c1.paragraphs[0]
        p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p2.add_run().add_picture(str(src), width=Cm(7.2))

    def _img_width(self, default=9.0):
        """按 imageRatio 的 imageShare 映射图宽（占版心比例）。"""
        s = self.image_share
        if s <= 0:
            return 0.0
        if s <= 0.1:
            return 5.0
        if s <= 0.2:
            return 7.0
        if s <= 0.35:
            return 9.0
        if s <= 0.5:
            return 12.0
        if s <= 0.7:
            return 14.0
        return 15.5

    def _image_rule_ok(self, cap):
        """imageRule 过滤：photo-only 仅照片、chart-only 仅流程/程序图、plan-only 仅平面（无匹配跳过）。"""
        rule = self.image_rule or "hybrid"
        if rule in ("none", "no-source", "dark-safe-img"):
            return False
        if rule == "photo-only":
            return not re.search(r"流程|程序|平面|示意", cap)
        if rule == "chart-only":
            return bool(re.search(r"流程|程序|进度", cap))
        if rule == "plan-only":
            return bool(re.search(r"平面|布置|总图", cap))
        return True

    def _image_render(self, cap, src, right_text=""):
        """按 imageLayout 排版单张图；width 按 imageRatio 档位；图题按 captionSystem。"""
        w = self._img_width()
        if w <= 0:
            return
        layout = self.image_layout
        cap_text = "%s　%s" % (self._caption_text("fig"), cap)
        if layout in ("split-h",):
            if self.preset == "image-left":
                self._image_left(cap, src, right_text)
            elif self.preset == "image-right":
                self._image_right(cap, src, right_text)
            else:
                self._image_single(cap, src, w, cap_text)
        elif layout == "split-v":
            # 上图下文：1×1 无边框表，上图文、下图题+正文
            table = self.doc.add_table(rows=2, cols=1)
            table.autofit = True
            _no_borders(table)
            p0 = table.rows[0].cells[0].paragraphs[0]
            p0.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p0.add_run().add_picture(str(src), width=Cm(w))
            c1 = table.rows[1].cells[0]
            p1 = c1.paragraphs[0]
            p1.alignment = WD_ALIGN_PARAGRAPH.CENTER
            r1 = p1.add_run(cap_text)
            _set_font(r1, None, size=Pt(9), east=self.font_body if not self.dark else "宋体")
            if right_text:
                p2 = c1.add_paragraph()
                r2 = p2.add_run(right_text)
                _set_font(r2, None, size=_heading_size(self.sizes, "body", 12), east=self.font_body)
        elif layout == "inline":
            # 图文混排：小图嵌段落中
            p = self.doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.add_run().add_picture(str(src), width=Cm(min(w, 7.0)))
            cap2 = self.doc.add_paragraph()
            cap2.alignment = WD_ALIGN_PARAGRAPH.CENTER
            rc = cap2.add_run(cap_text)
            _set_font(rc, None, size=Pt(9), east=self.font_body if not self.dark else "宋体")
            if right_text:
                rp = self.doc.add_paragraph(right_text)
                _set_font(rp.add_run(), None, size=_heading_size(self.sizes, "body", 12), east=self.font_body)
        elif layout == "side-note":
            # 侧注式：1×2 左窄图右注文
            table = self.doc.add_table(rows=1, cols=2)
            table.autofit = True
            _no_borders(table)
            try:
                table.columns[0].width = Cm(6.0)
                table.columns[1].width = Cm(8.4)
            except Exception:
                pass
            c0 = table.rows[0].cells[0]
            p0 = c0.paragraphs[0]
            p0.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p0.add_run().add_picture(str(src), width=Cm(min(w, 5.8)))
            rc = c0.add_paragraph()
            rc.alignment = WD_ALIGN_PARAGRAPH.CENTER
            r1 = rc.add_run(cap_text)
            _set_font(r1, None, size=Pt(9), east=self.font_body if not self.dark else "宋体")
            c1 = table.rows[0].cells[1]
            r2 = c1.paragraphs[0].add_run(right_text or cap)
            _set_font(r2, None, size=_heading_size(self.sizes, "body", 12), east=self.font_body)
        elif layout == "banner":
            self._image_single(cap, src, 15.5, cap_text, note=right_text)
        elif layout == "timeline":
            self._image_single(cap, src, w, cap_text, note=(right_text or "里程碑/进度节点示意"))
        elif layout == "card-mix":
            # 图卡混排：1×1 边框图卡 + 图题
            table = self.doc.add_table(rows=1, cols=1)
            table.autofit = True
            _box_borders(table, "C9D2E2", 6)
            cell = table.rows[0].cells[0]
            p0 = cell.paragraphs[0]
            p0.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p0.add_run().add_picture(str(src), width=Cm(min(w, 9.0)))
            cap3 = cell.add_paragraph()
            cap3.alignment = WD_ALIGN_PARAGRAPH.CENTER
            rc2 = cap3.add_run(cap_text)
            _set_font(rc2, None, size=Pt(9), east=self.font_body if not self.dark else "宋体")
        elif layout == "appendix":
            self._image_single(cap, src, 14.0, cap_text, note="（正文引用：见图序）")
        elif layout == "grid":
            self._image_single(cap, src, 7.0, cap_text, note=right_text)
        else:
            self._image_single(cap, src, w, cap_text, note=right_text)

    def _image_single(self, cap, src, w, cap_text, note=""):
        """全宽/默认单图：图 + 图题（下/上按 captionSystem）。"""
        if self.caption["fig_pos"] == "above":
            self._caption_para(cap_text)
        p = self.doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.add_run().add_picture(str(src), width=Cm(w))
        if self.caption["fig_pos"] == "below":
            self._caption_para(cap_text)
        if note:
            pn = self.doc.add_paragraph()
            pn.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            rn = pn.add_run(note)
            _set_font(rn, None, size=_heading_size(self.sizes, "body", 12), east=self.font_body)

    def render_md(self, text, table_fill):
        lines = text.splitlines()
        i = 0
        while i < len(lines):
            line = lines[i].rstrip()
            if self._last_list and not (line.startswith("- ") or line.startswith("* ")):
                self._last_list = False
                self._list_seq = 0
            if not line.strip():
                i += 1
                continue
            m = re.match(r"^(#{1,6})\s+(.*)$", line)
            if m:
                self._heading(len(m.group(1)), m.group(2).strip())
                i += 1
                continue
            mimg = _MD_IMG.search(line)
            if mimg:
                if self.cfg.get("imageRatio") != "none" and self.image_layout != "none":
                    cap, src = mimg.group(1), mimg.group(2)
                    if Path(src).is_file() and self._image_rule_ok(cap):
                        self.fig_no += 1
                        right_text = ""
                        if i + 1 < len(lines):
                            nt = lines[i + 1].rstrip()
                            if (nt and not nt.startswith(("#", "!", "-", "*", "|"))
                                    and not _MD_TABLE_ROW.match(nt)):
                                right_text = nt
                                i += 1
                        self._image_render(cap, src, right_text)
                # 不渲染（暗标无图 / 图规则过滤 / 文件缺失）：整行连同说明文本跳过
                i += 1
                continue
            mtab = _MD_TABLE_ROW.match(line)
            if mtab:
                cells = [c.strip() for c in mtab.group(1).split("|")]
                header = cells
                rows = []
                i += 1
                if i < len(lines) and re.match(r"^\s*\|[\s\-:|]+\|\s*$", lines[i]):
                    i += 1
                while i < len(lines):
                    mt = _MD_TABLE_ROW.match(lines[i])
                    if not mt:
                        break
                    rows.append([c.strip() for c in mt.group(1).split("|")])
                    i += 1
                self._table(header, rows, table_fill)
                continue
            if line.startswith("- ") or line.startswith("* "):
                if self._last_list:
                    self._list_seq += 1
                else:
                    self._list_seq = 1
                    self._last_list = True
                self._list(line[2:].strip())
                i += 1
                continue
            self._body(line.strip())
            i += 1


def _is_dark(args, tree_layout, override_cfg):
    bid = getattr(args, "bid_mode", "") or ""
    if bid:
        return True
    if isinstance(tree_layout, dict) and (tree_layout.get("font") == "dark-safe" or tree_layout.get("_dark")):
        return True
    if override_cfg.get("font") == "dark-safe":
        return True
    return False


def _page_mode(cfg_hf):
    return (cfg_hf or {}).get("pageMode", "with-page")


def _estimate_pages(chars, dark):
    """字符数 → 页数估算（A4：明标小四 1.5 行距 ≈ 850 字/页；暗标四号 ≈ 600 字/页）。"""
    per = 600 if dark else 850
    return max(1, int(chars / per) + (1 if chars % per else 0))


def _chapter_divider(doc, title, colors):
    """divider：章节分隔页 —— 章标题居中大字号 + 下方主色条（outlineLvl 0 供目录收集）。"""
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    pf = p.paragraph_format
    pf.page_break_before = True
    pf.space_before = Pt(54)
    pf.space_after = Pt(14)
    pPr = p._p.get_or_add_pPr()
    lvl = OxmlElement("w:outlineLvl")
    lvl.set(qn("w:val"), "0")
    pPr.append(lvl)
    pBdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "14")
    bottom.set(qn("w:color"), str(colors.get("primary", RGBColor.from_string("1B2C52"))))
    pBdr.append(bottom)
    pPr.append(pBdr)
    r = p.add_run(title)
    _set_font(r, None, size=Pt(22), color=colors["heading"], bold=True, east="黑体")


def _render_cover(doc, cover_id, colors, project, enterprise, dark, samples_dir=None):
    """covers 10 方案：色块/细线/图底/渐变/四角框/通栏/对角/极简/徽标/底部缎带。"""
    pbg = str(colors.get("coverBg", "1B2C52"))
    pbg2 = str(colors.get("coverBgEnd", "3A5A96"))
    if dark:
        pbg = pbg2 = "000000"
    white = RGBColor(0xFF, 0xFF, 0xFF)
    heading_c = RGBColor(0xFF, 0xFF, 0xFF) if cover_id in ("full-block", "gradient", "split-diagonal", "top-banner", "image-underlay") else colors.get("heading")
    doc.add_paragraph()
    doc.add_paragraph()

    def _band(text, size, color, bg=None, bold=True, font="黑体", align=WD_ALIGN_PARAGRAPH.CENTER, before=0, after=0):
        p = doc.add_paragraph()
        p.alignment = align
        if before:
            p.paragraph_format.space_before = Pt(before)
        if after:
            p.paragraph_format.space_after = Pt(after)
        if bg:
            _shade(p._p, bg)
        r = p.add_run(text)
        _set_font(r, None, size=size, color=color, bold=bold, east=font)
        return p

    def _rule(pts=8, color=None):
        p = doc.add_paragraph()
        pPr = p._p.get_or_add_pPr()
        pBdr = OxmlElement("w:pBdr")
        top = OxmlElement("w:top")
        top.set(qn("w:val"), "single"); top.set(qn("w:sz"), str(pts))
        top.set(qn("w:color"), color or pbg)
        pBdr.append(top)
        pPr.append(pBdr)

    if cover_id == "minimal-type":
        doc.add_paragraph()
        _band("投标技术标（监理大纲）", Pt(30), colors.get("heading"), bold=True, font="黑体", before=120)
        _band(project, Pt(18), colors.get("heading"), bold=False, font="宋体", before=24)
        _band(enterprise, Pt(12), None, bold=False, font="宋体", before=48)
    elif cover_id == "line-white":
        doc.add_paragraph()
        _rule(12)
        _band("投标技术标（监理大纲）", Pt(30), colors.get("heading"), bold=True, font="黑体", before=150)
        _band(project, Pt(18), colors.get("heading"), bold=False, font="宋体", before=18)
        _band(enterprise, Pt(12), None, bold=False, font="宋体", before=40)
        _rule(12)
    elif cover_id == "frame-corners":
        doc.add_paragraph()
        _rule(14)
        _band("投标技术标（监理大纲）", Pt(28), colors.get("heading"), bold=True, font="黑体", before=150)
        _band(project, Pt(18), colors.get("heading"), bold=False, font="宋体", before=20)
        _band(enterprise, Pt(12), None, bold=False, font="宋体", before=44)
        _rule(14)
    elif cover_id == "top-banner":
        _band(project, Pt(24), white, bg=pbg, bold=True, font="黑体", before=18, after=6)
        doc.add_paragraph()
        _band("投标技术标（监理大纲）", Pt(32), colors.get("heading"), bold=True, font="黑体", before=110)
        _band(enterprise, Pt(14), None, bold=False, font="宋体", before=30)
    elif cover_id == "gradient":
        _band("投标技术标（监理大纲）", Pt(32), white, bg=pbg, bold=True, font="黑体", before=60, after=0)
        _band(project, Pt(22), white, bg=pbg2, bold=True, font="黑体", after=0)
        _band(enterprise, Pt(14), colors.get("heading"), bg=None, bold=False, font="宋体", before=26)
    elif cover_id == "split-diagonal":
        _band("投标技术标（监理大纲）", Pt(32), white, bg=pbg, bold=True, font="黑体", before=140, after=30)
        _band(project, Pt(22), white, bg=pbg2, bold=True, font="黑体", after=6)
        _band(enterprise, Pt(13), colors.get("heading"), bold=False, font="宋体", before=10)
    elif cover_id == "ribbon-bottom":
        _band("投标技术标（监理大纲）", Pt(32), colors.get("heading"), bold=True, font="黑体", before=100, align=WD_ALIGN_PARAGRAPH.RIGHT)
        _band(project, Pt(20), colors.get("heading"), bold=False, font="宋体", before=16, align=WD_ALIGN_PARAGRAPH.RIGHT)
        doc.add_paragraph()
        _band(enterprise, Pt(13), white, bg=pbg, bold=True, font="黑体", before=300)
    elif cover_id == "emblem-center":
        logo = None
        if samples_dir:
            for cand in sorted(Path(samples_dir).parent.glob("**/logo*")):
                if cand.is_file() and cand.suffix.lower() in (".png", ".jpg", ".jpeg"):
                    logo = cand
                    break
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        if logo is not None:
            p.add_run().add_picture(str(logo), width=Cm(4.5))
        else:
            r = p.add_run("◆ 企业 LOGO")
            _set_font(r, None, size=Pt(28), color=colors.get("heading"), east="黑体")
        _band("投标技术标（监理大纲）", Pt(28), colors.get("heading"), bold=True, font="黑体", before=30)
        _band(project, Pt(16), colors.get("heading"), bold=False, font="宋体", before=16)
        _band(enterprise, Pt(12), None, bold=False, font="宋体", before=36)
    elif cover_id == "image-underlay":
        bg_img = None
        if samples_dir:
            for cand in sorted(Path(samples_dir).glob("*")):
                if cand.is_file() and cand.suffix.lower() in (".png", ".jpg", ".jpeg"):
                    bg_img = cand
                    break
        if bg_img is not None:
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.add_run().add_picture(str(bg_img), width=Cm(15.5))
        _band("投标技术标（监理大纲）", Pt(30), white, bg=pbg, bold=True, font="黑体", before=14)
        _band(project, Pt(18), white, bg=pbg, bold=True, font="黑体")
        _band(enterprise, Pt(12), None, bold=False, font="宋体", before=12)
    else:  # full-block
        _band("投标技术标（监理大纲）", Pt(36), white, bg=pbg, bold=True, font="黑体", before=80)
        _band(project, Pt(22), white, bg=pbg, bold=True, font="黑体")
        _band(enterprise, Pt(14), white, bg=pbg, bold=False, font="黑体")
    doc.add_page_break()


def _render_chapter_title(doc, title, colors, preset, dark):
    """章标题统一入口：divider 走分隔页样式，其余走默认页首标题。"""
    if preset == "divider" and not dark:
        _chapter_divider(doc, title, colors)
        return
    p = doc.add_paragraph()
    r = p.add_run(title)
    _set_font(r, None, size=Pt(16), color=colors["heading"], bold=True, east="黑体")
    pf = p.paragraph_format
    pf.page_break_before = True
    pf.space_after = Pt(10)
    pPr = p._p.get_or_add_pPr()
    lvl = OxmlElement("w:outlineLvl")
    lvl.set(qn("w:val"), "0")
    pPr.append(lvl)


def cmd_tech_export(args):
    ent = sources.get_ent(args)
    proj = sources.proj_dir(ent, args.project)
    tech = sources.tech_dir(ent, args.project)
    tree = store.read_tree(tech)
    if not store.outline_confirmed(tree):
        raise core.LibraryError("闸门①未确认：章节树需先 tech-outline --confirm，禁止 tech-export")

    presets_doc = layout_mod.load_presets(args)
    tree_layout = tree.get("layout") if isinstance(tree, dict) else None
    cfg = resolve_presets(args, presets_doc, tree_layout)
    dark = _is_dark(args, tree_layout, cfg)
    if dark:
        # 暗标不开放风格选择（契约 D5 / bid-anbiao-mingbiao-routing 经验）
        cfg["font"] = "dark-safe"
        cfg["cover"] = "none" if not any(c.get("id") == "none" for c in (layout_mod.entries(presets_doc, "cover") if presets_doc else [])) else cfg["cover"]
        cfg["decoration"] = "none"
        if cfg.get("headerFooter") != DARK_HF_PAGE_ONLY:
            cfg["headerFooter"] = DARK_HF_NO_PAGE
        if cfg.get("imageRatio") == "none":
            pass
        else:
            cfg["imageRatio"] = "none"  # 暗标切断全部图片风险

    palette = layout_mod.palette_colors(presets_doc, cfg["palette"]) or {}
    colors = {
        "primary": RGBColor.from_string(palette.get("primary", "243B6B").lstrip("#")),
        "accent": RGBColor.from_string(palette.get("accent", "B08A4B").lstrip("#")),
        "heading": RGBColor.from_string(palette.get("heading", "1B2C52").lstrip("#")),
        "tableFill": palette.get("tableFill", "E8ECF4").lstrip("#"),
        "coverBg": palette.get("coverBg", "1B2C52").lstrip("#"),
    }
    font_row = {}
    for row in layout_mod.entries(presets_doc, "font") or []:
        if row.get("id") == cfg.get("font", "gov-gongwen"):
            font_row = row
            break
    sizes = font_row.get("sizes") or {}
    hf = {}
    for row in layout_mod.entries(presets_doc, "headerFooter") or []:
        if row.get("id") == cfg.get("headerFooter", "hf1-classic-enterprise"):
            hf = row
            break
    ps = {}
    for row in layout_mod.entries(presets_doc, "paragraphStyle") or []:
        if row.get("id") == cfg.get("paragraphStyle", "pa7-jianyu-15"):
            ps = row
            break

    out_dir = Path(getattr(args, "out", "") or (tech / "产出"))
    out_dir.mkdir(parents=True, exist_ok=True)
    out_docx = out_dir / ("技术标_%s.docx" % args.project)

    doc = Document()
    # 页面设置
    margins = _parse_margin("")
    ps_text = ""
    for row in layout_mod.entries(presets_doc, "pageSetup") or []:
        if row.get("id") == cfg.get("pageSetup", "p1-standard-a4"):
            ps_text = row.get("margin", "")
            break
    margins = _parse_margin(ps_text)
    sec = doc.sections[0]
    sec.top_margin = Cm(margins["上"]); sec.bottom_margin = Cm(margins["下"])
    sec.left_margin = Cm(margins["左"]); sec.right_margin = Cm(margins["右"])
    gutter = _parse_gutter("")
    for row in layout_mod.entries(presets_doc, "pageSetup") or []:
        if row.get("id") == cfg.get("pageSetup", "p1-standard-a4"):
            gutter = _parse_gutter(row.get("gutter", ""))
            break
    if gutter:
        sec.left_margin = sec.left_margin + Cm(gutter)
    sec.page_width = Cm(21.0); sec.page_height = Cm(29.7)

    enterprise = ""
    try:
        ent_dir = sources.ent_dir(ent, args.project) if hasattr(sources, "ent_dir") else None
    except Exception:
        ent_dir = None
    if ent_dir is not None:
        enterprise = Path(ent_dir).name
    if not enterprise:
        enterprise = getattr(args, "enterprise", "") or "安徽安硕工程咨询有限公司"

    # 数据层各行（font/heading/toc/table/caption/decoration/imageLayout/imageRatio/imageRule）
    def _row_of(group, cid, default_id):
        for row in layout_mod.entries(presets_doc, group) or []:
            if row.get("id") == cid:
                return row
        return None

    font_row = _row_of("font", cfg.get("font", "gov-gongwen"), "gov-gongwen")
    heading_row = _row_of("headingSystem", cfg.get("headingSystem", "h1-gbt-arabic"), "h1-gbt-arabic")
    toc_row = _row_of("tocStyle", cfg.get("tocStyle", "t1-jianyu-auto"), "t1-jianyu-auto")
    table_row = _row_of("tableStyle", cfg.get("tableStyle", "tb1-three-line"), "tb1-three-line")
    caption_row = _row_of("captionSystem", cfg.get("captionSystem", "c2-cy-chapter"), "c2-cy-chapter")
    decoration_row = _row_of("decoration", cfg.get("decoration", "standard"), "standard")
    image_layout = None
    image_share = 0.3
    image_rule = "hybrid"
    for row in layout_mod.entries(presets_doc, "imageLayout") or []:
        if row.get("id") == cfg.get("imageLayout", "split-h"):
            image_layout = row.get("id", "split-h")
            break
    for row in layout_mod.entries(presets_doc, "imageRatio") or []:
        if row.get("id") == cfg.get("imageRatio", "mid"):
            try:
                image_share = float(row.get("imageShare") or 0.3)
            except Exception:
                image_share = 0.3
            break
    for row in layout_mod.entries(presets_doc, "imageRule") or []:
        if row.get("id") == cfg.get("imageRule", "hybrid"):
            image_rule = row.get("id", "hybrid")
            break

    # 封面（仅明标；暗标无封面）
    cover_ok = not dark
    cover_id = cfg.get("cover", "full-block")
    if cover_ok and presets_doc:
        cover = _row_of("cover", cover_id, "full-block")
        if cover is not None and cover.get("darkOk") is False:
            cover_ok = False
    samples_dir = None
    try:
        samples_dir = layout_mod._sample_images()
    except Exception:
        samples_dir = None
    if cover_ok:
        _render_cover(doc, cover_id, colors, args.project, enterprise, dark, samples_dir=samples_dir)

    # 目录 + TOC 域（tocStyle：标题样式 / 页码开关 / 大纲级别）
    toc_parsed = _parse_toc(toc_row)
    th = doc.add_paragraph()
    th.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = th.add_run("目　录")
    _set_font(r, None, size=toc_parsed["title_size"], bold=(toc_parsed["title_bold"] and not dark),
              east="黑体" if not dark else "宋体")
    toc_switches = r"\z" if not toc_parsed["page"] else ""
    _add_field(doc.add_paragraph(), r'TOC \o "1-%d" \h %s \u' % (toc_parsed["max_level"], toc_switches))
    doc.add_page_break()

    # 页面背景（decoration=rich 明标浅色背景）
    if decoration_row is not None and decoration_row.get("id") == "rich" and not dark:
        try:
            bg = OxmlElement("w:background")
            bg.set(qn("w:color"), "EAF1F8")
            doc.element.body.append(bg)
        except Exception:
            pass

    # 正文渲染
    chapters = store.list_chapters(tree)
    renderer = _Renderer(doc, cfg, dark, colors, sizes, ps=ps, preset=cfg.get("preset", "single-column"),
                         font_row=font_row, heading_row=heading_row, toc_row=toc_row,
                         table_row=table_row, caption_row=caption_row, decoration_row=decoration_row,
                         image_layout=image_layout, image_share=image_share, image_rule=image_rule)
    total_chars = 0
    for idx, ch in enumerate(chapters):
        cid = ch["id"]
        title = ch.get("title") or cid
        body = store.read_chapter_body(tech, ch)
        total_chars += len(body)
        if not dark:
            _render_chapter_title(doc, title, colors, renderer.preset, dark)
        renderer.begin_chapter(idx + 1)
        renderer.render_md(body, colors["tableFill"])

    # 页眉页脚（headerFooters 方案：模板三态 + 页脚样式 + 角点装饰）
    page_mode = _page_mode(hf)
    fbody = (font_row or {}).get("body") or "宋体"
    if "仿宋" in fbody:
        fbody = "仿宋"
    dots = (decoration_row is not None and decoration_row.get("id") == "corner-dots")
    hf_text = (hf or {}).get("header") or ""
    hf_footer = (hf or {}).get("footer") or ""
    if not dark:
        if page_mode in ("with-page", "page-only"):
            footer = sec.footer
            fp = footer.paragraphs[0]
            fp.alignment = WD_ALIGN_PARAGRAPH.RIGHT if "右对齐" in hf_footer else WD_ALIGN_PARAGRAPH.CENTER
            dot_l = ("● " if dots else "")
            dot_r = (" ●" if dots else "")
            if dot_l:
                rl = fp.add_run(dot_l)
                _set_font(rl, None, size=Pt(9), color=colors["primary"], east="宋体")
            if " -" in hf_footer or "页脚居中 -" in hf_footer:
                rm = fp.add_run(" - ")
                _set_font(rm, None, size=Pt(9), east="宋体")
            _page_field(fp, size=Pt(9))
            if " -" in hf_footer or "页脚居中 -" in hf_footer:
                rp2 = fp.add_run(" -")
                _set_font(rp2, None, size=Pt(9), east="宋体")
            if dot_r:
                rr = fp.add_run(dot_r)
                _set_font(rr, None, size=Pt(9), color=colors["primary"], east="宋体")
        if page_mode == "with-page":
            hp = sec.header.paragraphs[0]
            if "居中" in hf_text:
                hp.alignment = WD_ALIGN_PARAGRAPH.CENTER
                r = hp.add_run("%s" % enterprise)
            else:
                r = hp.add_run("%s　|　%s" % (enterprise, "投标技术标"))
            _set_font(r, None, size=Pt(9), color=colors["heading"], east=fbody)
            if dots:
                rd = hp.add_run("　●")
                _set_font(rd, None, size=Pt(9), color=colors["primary"], east="宋体")
            _header_line_after(sec)
    else:
        if cfg.get("headerFooter") == DARK_HF_PAGE_ONLY:
            fp = sec.footer.paragraphs[0]
            fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
            _page_field(fp, size=Pt(9))
        # 其余暗标：无页码、无页眉页脚（hf9）

    doc.save(str(out_docx))

    # 回读校验（契约 §4 验收：可打开 + 段落数>0 + 目录域存在）
    verify = Document(str(out_docx))
    para_count = len(verify.paragraphs)
    xml = verify.element.xml
    has_toc = ("TOC" in xml and "fldChar" in xml)
    if para_count <= 0:
        raise core.LibraryError("回读校验失败：导出的 docx 段落数为 0：%s" % out_docx)
    if not has_toc:
        raise core.LibraryError("回读校验失败：目录域缺失：%s" % out_docx)

    pages = _estimate_pages(total_chars, dark)
    meta = {
        "schema": EXPORT_SCHEMA,
        "project": args.project,
        "out": str(out_docx),
        "dark": dark,
        "layout": cfg,
        "chapters": len(chapters),
        "chars": total_chars,
        "pages_estimate": pages,
        "verified": {"paragraphs": para_count, "toc_field": True},
        "exported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    meta_p = tech / "章节" / ".meta" / "export.json"
    store.write_json_inside(tech, "章节/.meta/export.json", meta)
    print("T10 tech-export → %s" % out_docx)
    print("  暗标=%s 预设=%s 页数估算=%d 段落=%d TOC=%s" % (
        dark, " ".join("%s=%s" % (k, cfg[k]) for k in ("preset", "palette", "font", "headerFooter")),
        pages, para_count, has_toc))
    print("  回写: %s" % meta_p)
    return 0


def add_sub(sub):
    sp = sub.add_parser("tech-export", help="M6·T10 导出排版引擎：合并 md → docx（标题样式 + TOC 域 + 页眉页脚 pageMode 三态）→ 回读 + 页数回写（契约 §3.2/§4）")
    sp.add_argument("--project", required=True, help="项目名（项目级/<项目>，章节树/正文在 技术标/ 下）")
    sp.add_argument("--out", default="", help="输出目录（默认 技术标/产出）")
    sp.add_argument("--override", default="", help="预设覆盖：'preset=single-column;palette=deep-indigo;...'（分号分隔，键=十五组名）")
    sp.add_argument("--bid-mode", default="", help="暗标显式声明（任何非空值即暗标；缺省从章节树 layout.font=dark-safe 推断）")
    sp.add_argument("--enterprise", default="", help="企业名称（页眉用；缺省取企业目录名）")
    sp.add_argument("--force", action="store_true", help="预留：闸门②存在 error 时强制导出（本次未接入闸门②检查）")
    sp.set_defaults(handler=cmd_tech_export)
