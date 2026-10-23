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


# ---------------------------------------------------------------------------
# 正文解析与渲染
# ---------------------------------------------------------------------------
class _Renderer:
    def __init__(self, doc, cfg, dark, colors, sizes, ps=None):
        self.doc = doc
        self.cfg = cfg
        self.dark = dark
        self.colors = colors
        self.sizes = sizes
        self.ps = ps or {}
        self.table_no = 0
        self.fig_no = 0

    def _heading(self, level, text):
        sizes = self.sizes or {}
        size = _heading_size(sizes, {1: "chapter", 2: "section", 3: "item", 4: "item", 5: "body", 6: "body"}.get(level, "body"), 14)
        bold = False if self.dark else (level <= 2)
        color = None if self.dark else self.colors.get("heading")
        p = self.doc.add_paragraph()
        p.style = self.doc.styles["Normal"]
        pf = p.paragraph_format
        pf.space_before = Pt(6 if level <= 2 else 3)
        pf.space_after = Pt(4 if level <= 2 else 2)
        pf.line_spacing = 1.2
        if level <= 3:
            pf.keep_with_next = True
        # 大纲级别（TOC \o "1-3" 按 outlineLvl 收集；level 0-5 对应 H1-H6）
        pPr = p._p.get_or_add_pPr()
        lvl = OxmlElement("w:outlineLvl")
        lvl.set(qn("w:val"), str(max(0, level - 1)))
        pPr.append(lvl)
        r = p.add_run(text)
        _set_font(r, None, size=size, color=color, bold=bold,
                  east="黑体" if not self.dark else "宋体")
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
        pf.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        if line_spacing is not None:
            pf.line_spacing = line_spacing
        else:
            pf.line_spacing = 1.5
        pf.space_before = Pt(0); pf.space_after = Pt(0)
        r = p.add_run(text)
        _set_font(r, None, size=_heading_size(self.sizes, "body", 12) if not self.dark else Pt(14),
                  east="仿宋" if not self.dark else "宋体")
        return p

    def _list(self, text):
        p = self.doc.add_paragraph(style="List Bullet")
        pf = p.paragraph_format
        pf.line_spacing = 1.5
        r = p.add_run(text)
        _set_font(r, None, size=_heading_size(self.sizes, "body", 12) if not self.dark else Pt(14),
                  east="仿宋" if not self.dark else "宋体")

    def _table(self, header_cells, rows, table_fill):
        self.table_no += 1
        # 表题置于表上方居中（三线表规范：CY/T 170-2019；captionSystem 表题表上）
        cap = self.doc.add_paragraph()
        cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
        cap.paragraph_format.space_before = Pt(6)
        cap.paragraph_format.space_after = Pt(2)
        r = cap.add_run("表 %d　%s" % (self.table_no, header_cells[0] if header_cells else ""))
        _set_font(r, None, size=Pt(9), east="宋体")
        table = self.doc.add_table(rows=1 + len(rows), cols=len(header_cells))
        table.alignment = 1  # center
        table.autofit = True
        _table_borders(table)
        for j, h in enumerate(header_cells):
            cell = table.rows[0].cells[j]
            cell.text = ""
            para = cell.paragraphs[0]
            run = para.add_run(h)
            _set_font(run, None, size=Pt(10.5), bold=True, east="宋体")
            _shade(cell._tc, table_fill or "E8ECF4")
        for i, row in enumerate(rows):
            for j, v in enumerate(row):
                cell = table.rows[i + 1].cells[j]
                cell.text = ""
                run = cell.paragraphs[0].add_run(v)
                _set_font(run, None, size=Pt(10.5), east="宋体")

    def render_md(self, text, table_fill):
        lines = text.splitlines()
        i = 0
        while i < len(lines):
            line = lines[i].rstrip()
            if not line.strip():
                i += 1
                continue
            m = re.match(r"^(#{1,6})\s+(.*)$", line)
            if m:
                self._heading(len(m.group(1)), m.group(2).strip())
                i += 1
                continue
            mimg = _MD_IMG.search(line)
            if mimg and self.cfg.get("imageRatio") != "none":
                cap, src = mimg.group(1), mimg.group(2)
                if Path(src).is_file():
                    self.fig_no += 1
                    self.doc.add_picture(str(src), width=Cm(13))
                    cp = self.doc.add_paragraph()
                    r = cp.add_run("图 %d　%s" % (self.fig_no, cap))
                    _set_font(r, None, size=Pt(9), east="宋体")
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

    # 封面（仅明标；暗标无封面）
    cover_ok = not dark
    if cover_ok and presets_doc:
        cover_rows = layout_mod.entries(presets_doc, "cover")
        cover = None
        for row in cover_rows:
            if row.get("id") == cfg.get("cover", "full-block"):
                cover = row
                break
        if cover is not None and cover.get("darkOk") is False:
            cover_ok = False
    if cover_ok:
        doc.add_paragraph()
        doc.add_paragraph()
        t = doc.add_paragraph()
        t.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _shade(t._p, colors["coverBg"])
        r = t.add_run("投标技术标（监理大纲）")
        _set_font(r, None, size=Pt(36), color=RGBColor(0xFF, 0xFF, 0xFF), bold=True, east="黑体")
        t2 = doc.add_paragraph()
        t2.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _shade(t2._p, colors["coverBg"])
        r2 = t2.add_run(args.project)
        _set_font(r2, None, size=Pt(22), color=RGBColor(0xFF, 0xFF, 0xFF), bold=True, east="黑体")
        t3 = doc.add_paragraph()
        t3.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _shade(t3._p, colors["coverBg"])
        r3 = t3.add_run(enterprise)
        _set_font(r3, None, size=Pt(14), color=RGBColor(0xFF, 0xFF, 0xFF), east="黑体")
        doc.add_page_break()

    # 目录 + TOC 域
    th = doc.add_paragraph()
    th.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = th.add_run("目　录")
    _set_font(r, None, size=Pt(16), bold=True, east="黑体")
    _add_field(doc.add_paragraph(), r'TOC \o "1-3" \h \z \u')
    doc.add_page_break()

    # 正文渲染
    chapters = store.list_chapters(tree)
    renderer = _Renderer(doc, cfg, dark, colors, sizes, ps=ps)
    total_chars = 0
    for ch in chapters:
        cid = ch["id"]
        title = ch.get("title") or cid
        body = store.read_chapter_body(tech, ch)
        total_chars += len(body)
        if not dark:
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
        renderer.render_md(body, colors["tableFill"])

    # 页眉页脚（pageMode 三态）
    page_mode = _page_mode(hf)
    if not dark:
        if page_mode in ("with-page", "page-only"):
            footer = sec.footer
            fp = footer.paragraphs[0]
            fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
            _page_field(fp, size=Pt(9))
        if page_mode == "with-page":
            hp = sec.header.paragraphs[0]
            r = hp.add_run("%s　|　%s" % (enterprise, "投标技术标"))
            _set_font(r, None, size=Pt(9), east="宋体")
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
