# -*- coding: utf-8 -*-
"""⑦ generator 拆包 · 图片占位（【图片：xxx】带边框占位段 + 灰底预览框）。

预览框（方案A：模板直接可见位置/尺寸/内容）→ ph_preview 模块。
"""
from . import ph_preview as phprev   # 图片占位预览框

__all__ = [
    "_make_image_ph_para", "_set_picture_marker", "_make_ph_preview_para",
    "_insert_ph_preview_after", "_insert_image_ph_after_table",
    "_insert_image_ph_after_para",
]


def _make_image_ph_para(text, font):
    """构造【图片：xxx】占位段（模板库同款样式：左/下/右边框 + F2F2F2 底纹 + 加粗 28号）。"""
    from .gen_common import qn
    from docx.oxml import OxmlElement
    p = OxmlElement("w:p")
    pPr = OxmlElement("w:pPr")
    pBdr = OxmlElement("w:pBdr")
    for edge in ("w:left", "w:bottom", "w:right"):
        el = OxmlElement(edge)
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), "6")
        el.set(qn("w:space"), "4")
        el.set(qn("w:color"), "808080")
        pBdr.append(el)
    pPr.append(pBdr)
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:fill"), "F2F2F2")
    pPr.append(shd)
    p.append(pPr)
    r = OxmlElement("w:r")
    rPr = OxmlElement("w:rPr")
    rf = OxmlElement("w:rFonts")
    rf.set(qn("w:ascii"), font)
    rf.set(qn("w:hAnsi"), font)
    rf.set(qn("w:eastAsia"), font)
    rPr.append(rf)
    for tag in ("w:b", "w:bCs"):
        rPr.append(OxmlElement(tag))
    col = OxmlElement("w:color")
    col.set(qn("w:val"), "000000")
    rPr.append(col)
    for tag, val in (("w:sz", "28"), ("w:szCs", "28")):
        el = OxmlElement(tag)
        el.set(qn("w:val"), val)
        rPr.append(el)
    r.append(rPr)
    t = OxmlElement("w:t")
    t.text = text
    t.set(qn("xml:space"), "preserve")
    r.append(t)
    p.append(r)
    return p


def _set_picture_marker(run, marker):
    """给段落内图片打标记：wp:docPr@descr = marker（填充引擎按此定位/删除预览框）。"""
    for el in run._r.iter():
        if el.tag.endswith("}docPr"):
            el.set("descr", marker)
            return True
    return False


def _make_ph_preview_para(doc, ph_text):
    """构造图片占位预览框段：灰底占位图（尺寸=image_spec 目标口径），docPr 打标 IMG_PH:xxx。"""
    from docx.shared import Cm
    png = phprev.make_placeholder_png(ph_text)
    w_cm, h_cm = phprev.box_size_for(ph_text)
    p = doc.add_paragraph()
    p.alignment = 1                                     # CENTER
    run = p.add_run()
    run.add_picture(png, width=Cm(w_cm), height=Cm(h_cm))
    _set_picture_marker(run, phprev.PH_PREVIEW_PREFIX + ph_text)
    return p


def _insert_ph_preview_after(doc, anchor_el, ph_text):
    """把预览框段移动到锚点元素（占位文字段）之后；返回是否成功。"""
    try:
        p = _make_ph_preview_para(doc, ph_text)
        anchor_el.addnext(p._p)
        return True
    except Exception:
        return False


def _insert_image_ph_after_table(doc, ctx_map, rules, font):
    """在指定表格（按表前文关键词，去空格匹配）之后插入图片占位段 + 预览框。
    返回 (占位段数, 预览框数)。"""
    n = n_prev = 0
    for table in doc.tables:
        ctx = ctx_map.get(table._tbl, "").replace(" ", "").replace("\u3000", "")
        for kw, phs in rules:
            if kw in ctx:
                for text in phs:
                    el = _make_image_ph_para(text, font)
                    table._tbl.addnext(el)
                    n += 1
                    if _insert_ph_preview_after(doc, el, text):
                        n_prev += 1
    return n, n_prev


def _insert_image_ph_after_para(doc, rules, font):
    """在锚点段落（含关键词）之后插入图片占位段 + 预览框。
    返回 (占位段数, 预览框数)。"""
    n = n_prev = 0
    for p in doc.paragraphs:
        full = p.text
        for kw, phs in rules:
            if kw in full:
                for text in phs:
                    el = _make_image_ph_para(text, font)
                    p._p.addnext(el)
                    n += 1
                    if _insert_ph_preview_after(doc, el, text):
                        n_prev += 1
    return n, n_prev
