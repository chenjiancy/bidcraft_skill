# -*- coding: utf-8 -*-
"""M5 v5：格式配置应用器（企业模板废弃后的格式来源）。

V5 设计（用户 2026-10-10 定稿）：
  项目模板内容 = 招标原文投标文件格式**深拷贝**（一字不改、一个内容不丢）；
  格式 = 通用格式配置 format_config.json（与内容无关，一套配置适用所有项目）；
  图片 = 图框占位（大小符合 image_spec 尺寸规定、位置按图片插入位置规律、
         数量按素材清单动态生成）；
  独占一面 = format_config.json「独占一面」清单（文件级/内容级），收敛按
  「独占面收敛规则」顺序执行（先删空行→再调行距→表格行高→单元格内边距→删分页符；
  禁止改字号/页边距）。

本模块只做确定性格式应用（字体/字号/行距/缩进/对齐/表格/页面/独占一面），
无业务判断；文字内容由 gen_blocks 深拷贝保证，图片占位由 ph_preview 图框保证。
"""
import re
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

from .gen_common import HAVE_DOCX, GenError

__all__ = ["load_format_config", "apply_format", "ensure_own_page",
           "classify_para", "add_page_number"]

_DEFAULT_CONFIG = Path(__file__).resolve().parent / "format_config.json"


# ---------------------------------------------------------------- 配置加载
def load_format_config(path=None):
    """加载通用格式配置（默认 scripts/m5_project/format_config.json）。
    支持 --format-config 指定覆盖；读取失败 → GenError（配置是 V5 格式唯一来源）。"""
    cfg_path = Path(path) if path else _DEFAULT_CONFIG
    if not cfg_path.is_file():
        raise GenError("通用格式配置不存在：%s（V5 格式唯一来源，不可缺失）" % cfg_path)
    import json
    try:
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception as ex:
        raise GenError("通用格式配置解析失败：%s（%s）" % (cfg_path, ex))
    return cfg


# ---------------------------------------------------------------- 段落分类
_CN_NUM = "一二三四五六七八九十百"
_RE_CHAPTER = re.compile(r"^第[%s]+章" % _CN_NUM)
_RE_CN_NUM = re.compile(r"^[%s]+、" % _CN_NUM)
_RE_TABLE_NO = re.compile(r"^表\d+[ 　]*\S")
_RE_SUB_NO = re.compile(r"^（[%s]+）" % _CN_NUM)
_RE_NUM_NO = re.compile(r"^（\d+）")
_RE_PAREN = re.compile(r"^（[^（）]{1,14}）$")
_RE_PUNCT = re.compile(r"[。；，：、]")


def classify_para(text, fname=""):
    """段落格式分类（确定性规则，可解释）：
    封面 / 章标题 / 一级标题 / 小节标题 / 标注段 / 落款 / 正文 / 空行。
    规则依据 format_config.json「文件类型」结构 + 真实标书段落特征。"""
    t = (text or "").strip()
    if not t:
        return "空行"
    if fname == "封面.docx":
        return "封面"
    if _RE_CHAPTER.match(t) or _RE_CN_NUM.match(t):
        return "章标题"
    if _RE_TABLE_NO.match(t):            # 表1 组织机构 / 表8 拟投入监理人员简历表
        return "一级标题"
    if _RE_SUB_NO.match(t) or _RE_NUM_NO.match(t) or _RE_PAREN.match(t):
        return "小节标题"
    if t.startswith("附："):
        return "标注段"
    # 落款（含签章/主体/日期特征）优先于小节标题（如「法定代表人或其委托代理人（签字或盖章）」）
    if re.search(r"(签字|盖章|投标人|供应商|法定代表|委托代理人|招标人|日期|年\s*月\s*日)", t):
        return "落款"
    if len(t) <= 34 and not _RE_PUNCT.search(t):
        return "小节标题"                 # 短标题无标点（企业资质证书/组 织 机 构/承诺书等）
    return "正文"


# ---------------------------------------------------------------- run/字体
def _set_run_font(run, zh_font, size_pt, bold=None):
    """设置 run 中文字体（w:eastAsia）+ 西文字体 + 字号 + 加粗。"""
    run.font.name = "Times New Roman" if zh_font in ("仿宋", "宋体") else zh_font
    run.font.size = Pt(size_pt)
    if bold is not None:
        run.font.bold = bold
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.insert(0, rfonts)
    rfonts.set(qn("w:ascii"), "Times New Roman")
    rfonts.set(qn("w:hAnsi"), "Times New Roman")
    rfonts.set(qn("w:eastAsia"), zh_font)


def _apply_para_fmt(p, align=None, line_pt=None, indent_chars=0):
    """段落格式：对齐 / 固定行距 / 首行缩进（字符）。"""
    pf = p.paragraph_format
    if align is not None:
        pf.alignment = align
    if line_pt is not None:
        pf.line_spacing_rule = WD_LINE_SPACING.EXACTLY
        pf.line_spacing = Pt(line_pt)
    if indent_chars:
        pf.first_line_indent = Pt(12 * indent_chars)


def _clear_para_runs(p):
    """段落内所有 run 清空格式（继承后将统一应用）。"""
    for r in p.runs:
        r.font.name = None
        r.font.size = None
        r.font.bold = None
        rpr = r._element.find(qn("w:rPr"))
        if rpr is not None:
            rfonts = rpr.find(qn("w:rFonts"))
            if rfonts is not None:
                rfonts.set(qn("w:eastAsia"), None)


# ---------------------------------------------------------------- 格式应用
_FONT_BY_FILE = {
    # format_config.json 字体体系：正文/标题/封面/表格 全仿宋（用户确认，无黑体）
}


def apply_format(doc, fname, config):
    """对项目模板 docx 应用通用格式配置（V5 格式唯一来源）。

    1) 页面：A4 竖向、边距（上2.54 下2.54 左2.5 右2.5）；页脚页码居中（封面无页码）；
    2) 段落：按 classify_para 分类应用字体/字号/行距/缩进/对齐（全仿宋体系）；
    3) 表格：表头行 仿宋12 加粗 + 底纹 D9D9D9；正文行 仿宋12；边框单线 0.5pt。
    返回 {"段落": n, "表格": m, "页码": 1/0, "页面": 1} 统计。
    """
    if not HAVE_DOCX:
        raise GenError("格式应用依赖 python-docx")
    page = config.get("页面", {})
    fonts = config.get("字体", {})
    body_zh = (fonts.get("正文", {}).get("中文字体") or "仿宋")
    body_sz = int((fonts.get("正文", {}).get("字号") or 12))
    line_pt = _line_pt_of(config)             # 固定28磅（收敛时调用方逐档下调）
    indent = 2                                # 首行缩进 2 字符

    n_para = 0
    # ---- 段落 ----
    for p in doc.paragraphs:
        t = p.text.strip()
        cls = classify_para(t, fname)
        if cls == "空行":
            continue
        _clear_para_runs(p)
        if cls == "封面":
            _apply_cover(p, config)
        elif cls == "章标题":
            _apply_para(p, body_zh, 22, "居中", line_pt, 0)
        elif cls == "一级标题":
            _apply_para(p, body_zh, 16, "左对齐", line_pt, 0)
        elif cls == "小节标题":
            _apply_para(p, body_zh, 14, "左对齐", line_pt, 0)
        elif cls == "标注段":
            _apply_para(p, body_zh, 12, "左对齐", line_pt, 0)
        elif cls == "落款":
            _apply_para(p, body_zh, 12, "右对齐", line_pt, 0)
        else:
            _apply_para(p, body_zh, body_sz, "两端对齐", line_pt, indent)
        n_para += 1

    # ---- 表格 ----
    n_tbl = 0
    for tbl in doc.tables:
        _apply_table(tbl, config)
        n_tbl += 1

    # ---- 页面 ----
    n_page = _apply_page(doc, config, cover=(fname == "封面.docx"))
    return {"段落": n_para, "表格": n_tbl, "页面": n_page}


def _line_pt_of(config):
    """正文行距（固定磅）：格式配置「行距」解析为磅值，默认 28。"""
    ls = (config.get("字体", {}).get("正文", {}) or {}).get("行距", "固定28磅")
    m = re.search(r"(\d+(?:\.\d+)?)", ls)
    return float(m.group(1)) if m else 28.0


def _apply_para(p, zh, size, align, line_pt, indent):
    align_map = {"居中": WD_ALIGN_PARAGRAPH.CENTER, "左对齐": WD_ALIGN_PARAGRAPH.LEFT,
                 "右对齐": WD_ALIGN_PARAGRAPH.RIGHT, "两端对齐": WD_ALIGN_PARAGRAPH.JUSTIFY}
    for r in p.runs or [p.add_run(p.text)]:
        _set_run_font(r, zh, size)
    _apply_para_fmt(p, align=align_map.get(align), line_pt=line_pt,
                    indent_chars=indent if indent else 0)


def _apply_cover(p, config):
    """封面：全部居中仿宋。项目名称 22 / 文件类型 26 / 其余（落款）14。
    分类：含「投标文件/响应文件/报价文件」→ 26；非空长文本 → 22；其余 → 14。"""
    t = p.text.strip()
    if re.search(r"投标文件|响应文件|报价文件", t):
        _apply_para(p, "仿宋", 26, "居中", None, 0)
    elif len(t) >= 10:
        _apply_para(p, "仿宋", 22, "居中", None, 0)
    else:
        _apply_para(p, "仿宋", 14, "居中", None, 0)


def _apply_table(tbl, config):
    """表格：表头行（首行）仿宋12 加粗 + 底纹 D9D9D9；其余行仿宋12；边框单线 0.5pt。"""
    fonts = config.get("字体", {})
    tbl_font = fonts.get("表格文字", {}).get("中文字体") or "仿宋"
    tbl_sz = int(fonts.get("表格文字", {}).get("字号") or 12)
    hdr_font = fonts.get("表格表头", {}).get("中文字体") or "仿宋"
    hdr_sz = int(fonts.get("表格表头", {}).get("字号") or 12)
    hdr_bold = bool(fonts.get("表格表头", {}).get("加粗", True))
    shade = fonts.get("表格表头", {}).get("底纹", "D9D9D9")
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    _set_table_borders(tbl)
    for ri, row in enumerate(tbl.rows):
        is_hdr = (ri == 0)
        for cell in row.cells:
            for p in cell.paragraphs:
                for r in p.runs:
                    _set_run_font(r, hdr_font if is_hdr else tbl_font,
                                  hdr_sz if is_hdr else tbl_sz,
                                  bold=hdr_bold if is_hdr else None)
            if is_hdr:
                _shade_cell(cell, shade)


def _set_table_borders(tbl):
    tblPr = tbl._tbl.tblPr
    old = tblPr.find(qn("w:tblBorders"))
    if old is not None:
        tblPr.remove(old)
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement("w:%s" % edge)
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), "4")           # 0.5pt
        el.set(qn("w:color"), "000000")
        borders.append(el)
    tblPr.append(borders)


def _shade_cell(cell, hex_color):
    for tc in (cell._tc,):
        tcPr = tc.get_or_add_tcPr()
        old = tcPr.find(qn("w:shd"))
        if old is not None:
            tcPr.remove(old)
        shd = OxmlElement("w:shd")
        shd.set(qn("w:val"), "clear")
        shd.set(qn("w:color"), "auto")
        shd.set(qn("w:fill"), hex_color)
        tcPr.append(shd)


# ---------------------------------------------------------------- 页面/页码
def _apply_page(doc, config, cover=False):
    """页面：A4 竖向 + 边距（上2.54 下2.54 左2.5 右2.5）；页脚页码（封面无）。"""
    page = config.get("页面", {})
    sec = doc.sections[0]
    sec.page_width = Cm(21.0)
    sec.page_height = Cm(29.7)
    mar = page.get("页边距_cm", {})
    sec.top_margin = Cm(float(mar.get("上", 2.54)))
    sec.bottom_margin = Cm(float(mar.get("下", 2.54)))
    sec.left_margin = Cm(float(mar.get("左", 2.5)))
    sec.right_margin = Cm(float(mar.get("右", 2.5)))
    if not cover:
        add_page_number(sec)
        return 1
    return 0


def add_page_number(section):
    """页脚插入居中页码域（PAGE）。"""
    footer = section.footer
    footer.is_linked_to_previous = False
    p = footer.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    fld = OxmlElement("w:fldSimple")
    fld.set(qn("w:instr"), "PAGE")
    r = OxmlElement("w:r")
    t = OxmlElement("w:t")
    t.text = "1"
    r.append(t)
    fld.append(r)
    p._p.append(fld)


# ---------------------------------------------------------------- 独占一面
def ensure_own_page(doc, fname, config):
    """独占一面：文件级（首段前插入分页符，保证合并整本时新页起）；
    内容级（资格证明及辅助资料表内 附表1/附表3/附表8 标题段前插入分页符）。
    收敛本身由 page_fit 负责（本函数只负责「新页起」）。返回插入分页符数。"""
    own = config.get("独占一面", {})
    n = 0
    # 文件级（键名带说明后缀）：**无括号说明的纯文件名**强制整文件独占一面
    # （封面/密封袋封面/开标一览表/投标函附录/法代/授权/中小企业声明函/承诺书）
    file_own = [f for f in own.get("文件级（每个文件独立成页）", []) if "（" not in f]
    if fname in file_own:
        n += _insert_page_break_first(doc)
    # 内容级：资格证明及辅助资料表 附表1 组织机构 / 附表8 简历表 / 附表3 业绩表
    if fname == "资格证明及辅助资料表.docx":
        for p in list(doc.paragraphs):
            t = p.text.strip()
            if re.match(r"^附表[138][：:]", t) or "组 织 机 构" in t or "组织机构" in t:
                n += _insert_page_break_before(doc, p)
    return n


def _insert_page_break_first(doc):
    """在文档第一个非空段落前插入分页符段（空文档时在 body 末尾追加）。"""
    body = doc.element.body
    first = None
    for child in body.iterchildren():
        if child.tag == qn("w:p"):
            first = child
            break
    br_p = _make_page_break_para(doc)
    if first is not None:
        first.addprevious(br_p)
    else:
        body.append(br_p)
    return 1


def _insert_page_break_before(doc, p):
    br_p = _make_page_break_para(doc)
    p._p.addprevious(br_p)
    return 1


def _make_page_break_para(doc):
    p = OxmlElement("w:p")
    r = OxmlElement("w:r")
    br = OxmlElement("w:br")
    br.set(qn("w:type"), "page")
    r.append(br)
    p.append(r)
    return p
