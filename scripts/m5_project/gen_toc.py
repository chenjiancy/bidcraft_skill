# -*- coding: utf-8 -*-
"""M5 L3：目录/TOC 域支持模块（2026-10-18）。

用户拍板（2026-10-18）：L3 保持分文件不合并，人工检查后指令合稿；
目录/页码采用「自动目录域（TOC 域）+ PAGE 域」。

本模块提供合稿时使用的 TOC 域能力：
  1) add_toc_field(doc, ...)  —— 在文档开头插入「目录」标题 + TOC 域段
     （Word 打开后按 F9 更新；TOC 域只索引当前文档标题样式 Heading 1-3，
      因此合稿（分文件合并为单 docx）后才有意义，分文件模式不调用）；
  2) add_heading_style(doc, level) —— 确保 Heading 1-3 样式存在（合稿前
      把各文件标题段标记为标题样式，供 TOC 域索引）。
"""
import re

from docx.oxml import OxmlElement
from docx.oxml.ns import qn

__all__ = ["add_toc_field", "add_heading_style", "TOC_INSTR"]


TOC_INSTR = 'TOC \\o "1-3" \\h \\z \\u'


def _new_run(p, text=None):
    r = OxmlElement("w:r")
    if text is not None:
        t = OxmlElement("w:t")
        t.text = text
        r.append(t)
    p.append(r)
    return r


def add_toc_field(doc, title="目  录", placeholder="（打开文档后按 F9 更新目录）"):
    """在文档开头插入「目录」标题段 + TOC 域段。

    TOC 域指令 TOC \\o "1-3" \\h \\z \\u：索引 Heading 1-3 标题、带超链接、
    使用大纲级别、更新页数。段首置 dirty=true，Word 打开时提示更新域。
    返回 {"标题": bool, "域": bool}。
    """
    body = doc.element.body
    # 标题段（仿宋 22 居中，风格与 format_config 章节标题一致）
    p_title = OxmlElement("w:p")
    ppr = OxmlElement("w:pPr")
    jc = OxmlElement("w:jc")
    jc.set(qn("w:val"), "center")
    ppr.append(jc)
    p_title.append(ppr)
    _new_run(p_title, title)
    body.insert(0, p_title)

    # TOC 域段：begin → instrText → separate → 占位文本 → end
    p_toc = OxmlElement("w:p")
    r_begin = OxmlElement("w:r")
    fc_begin = OxmlElement("w:fldChar")
    fc_begin.set(qn("w:fldCharType"), "begin")
    fc_begin.set(qn("w:dirty"), "true")
    r_begin.append(fc_begin)
    p_toc.append(r_begin)

    r_instr = OxmlElement("w:r")
    it = OxmlElement("w:instrText")
    it.set(qn("xml:space"), "preserve")
    it.text = " " + TOC_INSTR + " "
    r_instr.append(it)
    p_toc.append(r_instr)

    r_sep = OxmlElement("w:r")
    fc_sep = OxmlElement("w:fldChar")
    fc_sep.set(qn("w:fldCharType"), "separate")
    r_sep.append(fc_sep)
    p_toc.append(r_sep)

    _new_run(p_toc, placeholder)

    r_end = OxmlElement("w:r")
    fc_end = OxmlElement("w:fldChar")
    fc_end.set(qn("w:fldCharType"), "end")
    r_end.append(fc_end)
    p_toc.append(r_end)

    # 标题段后插入 TOC 段
    p_title.addnext(p_toc)
    return {"标题": True, "域": True}


def add_heading_style(doc, level):
    """确保 Heading {level} 样式存在（合稿前把各文件标题段设置为标题样式，
    TOC 域按 Heading 1-3 索引）。level ∈ {1,2,3}。返回是否已存在。"""
    from docx.enum.style import WD_STYLE_TYPE
    styles = doc.styles
    name = "Heading %d" % level
    if name in styles:
        return True
    st = styles.add_style(name, WD_STYLE_TYPE.PARAGRAPH)
    # 大纲级别（TOC 索引依赖 outlineLvl）
    el = st.element.get_or_add_pPr()
    ol = OxmlElement("w:outlineLvl")
    ol.set(qn("w:val"), str(level - 1))
    el.append(ol)
    return False
