# -*- coding: utf-8 -*-
"""docx_tools.reader：docx 结构深读记录提取（维度 0-7 核心集 + 样式继承）。

移植说明：能力逻辑借鉴豆包 word 技能 scripts/read.py（平台无关重写，非整文件复制）。
覆盖：正文段落/run/表格（含嵌套与合并）/媒体对象/页眉页脚/分节/样式定义。
不覆盖：维度 8（编号）、9（特殊节点/批注/宏）、altChunk 物化（标书场景无需求，
见规则对齐清单偏离项①）。
"""
from __future__ import annotations

from typing import Any

from lxml import etree

from .common import (
    NS,
    R,
    V,
    W,
    attrs,
    attr_value,
    int_value,
    on_off_value,
    paragraph_text,
    parse_borders,
    parse_shading,
    qn,
    read_margins,
    run_text_value,
    sha256_bytes,
    wqn,
    wtag,
)

MEDIA_KINDS = {
    ".png": "image", ".jpg": "image", ".jpeg": "image", ".gif": "image",
    ".bmp": "image", ".tiff": "image", ".emf": "image", ".wmf": "image",
    ".svg": "image",
}


# ---------------------------------------------------------------------------
# 段落 / run 属性
# ---------------------------------------------------------------------------
def paragraph_properties(ppr) -> dict[str, Any]:
    if ppr is None:
        return {}
    out: dict[str, Any] = {}
    style = attr_value(ppr.find(wtag("pStyle"), namespaces=NS))
    if style is not None:
        out["style_id"] = style
    align = attr_value(ppr.find(wtag("jc"), namespaces=NS))
    if align is not None:
        out["alignment"] = align
    outline = int_value(ppr.find(wtag("outlineLvl"), namespaces=NS))
    if outline is not None:
        out["outline_level"] = outline
    num_pr = ppr.find(wtag("numPr"), namespaces=NS)
    if num_pr is not None:
        num_id = int_value(num_pr.find(wtag("numId"), namespaces=NS))
        ilvl = int_value(num_pr.find(wtag("ilvl"), namespaces=NS))
        if num_id is not None or ilvl is not None:
            numbering: dict[str, Any] = {}
            if num_id is not None:
                numbering["num_id"] = num_id
            if ilvl is not None:
                numbering["ilvl"] = ilvl
            out["numbering"] = numbering
    ind = ppr.find(wtag("ind"), namespaces=NS)
    if ind is not None:
        indent: dict[str, Any] = {}
        for name in ("left", "right", "start", "end", "firstLine", "hanging"):
            value = int_value(ind, name)
            if value is not None:
                indent[name] = value
        if indent:
            out["indent"] = indent
    spacing_el = ppr.find(wtag("spacing"), namespaces=NS)
    if spacing_el is not None:
        spacing: dict[str, Any] = {}
        for name in ("before", "after", "line", "beforeLines", "afterLines"):
            value = int_value(spacing_el, name)
            if value is not None:
                spacing[name] = value
        line_rule = attr_value(spacing_el, "lineRule")
        if line_rule is not None:
            spacing["lineRule"] = line_rule
        if spacing:
            out["spacing"] = spacing
    for key, tag in (
        ("keep_with_next", "keepNext"),
        ("keep_lines", "keepLines"),
        ("page_break_before", "pageBreakBefore"),
        ("widow_control", "widowControl"),
    ):
        el = ppr.find(wtag(tag), namespaces=NS)
        if el is not None:
            out[key] = True if on_off_value(el) is None else on_off_value(el)
    borders = ppr.find(wtag("pBdr"), namespaces=NS)
    if borders is not None:
        out["borders"] = parse_borders(borders)
    shading = parse_shading(ppr.find(wtag("shd"), namespaces=NS))
    if shading:
        out["shading"] = shading
    tabs_el = ppr.find(wtag("tabs"), namespaces=NS)
    if tabs_el is not None:
        tabs = []
        for tab in tabs_el.findall(wtag("tab"), namespaces=NS):
            tab_record: dict[str, Any] = {}
            for name in ("val", "pos", "leader"):
                value = tab.get(wqn(name))
                if value is not None:
                    tab_record[name] = value
            if tab_record:
                tabs.append(tab_record)
        if tabs:
            out["tabs"] = tabs
    return out


def run_properties(rpr) -> dict[str, Any]:
    if rpr is None:
        return {}
    out: dict[str, Any] = {}
    style = attr_value(rpr.find(wtag("rStyle"), namespaces=NS))
    if style is not None:
        out["style_id"] = style
    bold = rpr.find(wtag("b"), namespaces=NS)
    if bold is not None:
        out["bold"] = True if on_off_value(bold) is None else on_off_value(bold)
    italic = rpr.find(wtag("i"), namespaces=NS)
    if italic is not None:
        out["italic"] = True if on_off_value(italic) is None else on_off_value(italic)
    caps = rpr.find(wtag("caps"), namespaces=NS)
    if caps is not None:
        out["caps"] = True if on_off_value(caps) is None else on_off_value(caps)
    small_caps = rpr.find(wtag("smallCaps"), namespaces=NS)
    if small_caps is not None:
        out["small_caps"] = True if on_off_value(small_caps) is None else on_off_value(small_caps)
    strike = rpr.find(wtag("strike"), namespaces=NS)
    if strike is not None:
        out["strike"] = True if on_off_value(strike) is None else on_off_value(strike)
    dstrike = rpr.find(wtag("dstrike"), namespaces=NS)
    if dstrike is not None:
        out["double_strike"] = True if on_off_value(dstrike) is None else on_off_value(dstrike)
    underline = rpr.find(wtag("u"), namespaces=NS)
    if underline is not None:
        out["underline"] = attr_value(underline) or "single"
    color = rpr.find(wtag("color"), namespaces=NS)
    if color is not None:
        out["color"] = color.get(wqn("val"))
    highlight = rpr.find(wtag("highlight"), namespaces=NS)
    if highlight is not None:
        out["highlight"] = attr_value(highlight)
    sz = int_value(rpr.find(wtag("sz"), namespaces=NS))
    if sz is not None:
        out["size_half_points"] = sz
    vert_align = attr_value(rpr.find(wtag("vertAlign"), namespaces=NS))
    if vert_align is not None:
        out["vertical_align"] = vert_align
    r_fonts = rpr.find(wtag("rFonts"), namespaces=NS)
    if r_fonts is not None:
        fonts: dict[str, Any] = {}
        for name in ("ascii", "eastAsia", "hAnsi", "cs"):
            value = r_fonts.get(wqn(name))
            if value is not None:
                fonts[name] = value
        if fonts:
            out["fonts"] = fonts
    lang = rpr.find(wtag("lang"), namespaces=NS)
    if lang is not None:
        lang_record: dict[str, Any] = {}
        for name in ("val", "eastAsia", "bidi"):
            value = lang.get(wqn(name))
            if value is not None:
                lang_record[name] = value
        if lang_record:
            out["lang"] = lang_record
    spacing = rpr.find(wtag("spacing"), namespaces=NS)
    if spacing is not None:
        value = int_value(spacing, "val")
        if value is not None:
            out["character_spacing"] = value
    position = int_value(rpr.find(wtag("position"), namespaces=NS))
    if position is not None:
        out["position_twips"] = position
    return out


# ---------------------------------------------------------------------------
# 绘图锚点（dim 6 ANCHOR / run.drawings）
# ---------------------------------------------------------------------------
def drawing_records(container) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for drawing in container.xpath(".//w:drawing", namespaces=NS):
        record: dict[str, Any] = {"drawing": True}
        for attr_name, tag in (("embed", "blip"), ("link", "blip")):
            for blip in drawing.xpath(".//a:blip", namespaces=NS):
                rid = blip.get(qn(R, attr_name))
                if rid:
                    record[attr_name] = rid
                    break
        for el in drawing.xpath(".//wp:inline | .//wp:anchor", namespaces=NS):
            rid = el.get(qn(R, "id"))
            if rid:
                record["r:id"] = rid
            extent = el.find("wp:extent", namespaces=NS)
            if extent is not None:
                cx, cy = extent.get("cx"), extent.get("cy")
                if cx is not None or cy is not None:
                    record["extent"] = {
                        key: value
                        for key, value in (("cx", cx), ("cy", cy))
                        if value is not None
                    }
        doc_pr = drawing.find(".//wp:docPr", namespaces=NS)
        if doc_pr is not None:
            doc_pr_record: dict[str, Any] = {}
            for name in ("id", "name", "descr"):
                value = doc_pr.get(name)
                if value is not None:
                    doc_pr_record[name] = value
            if doc_pr_record:
                record["docPr"] = doc_pr_record
        records.append(record)
    # VML w:pict（老版 Word/WPS 图元）：图锚点走 v:imagedata/@r:id，
    # 与 a:blip 并列，作为 drawing 记录（golden 实测：48MB 标书 68 张图全为 pict）
    for pict in container.xpath(".//w:pict", namespaces=NS):
        record: dict[str, Any] = {"drawing": True, "vml_pict": True}
        for imagedata in pict.xpath(".//v:imagedata", namespaces=NS):
            rid = imagedata.get(qn(R, "id"))
            if rid:
                record["embed"] = rid
                break
        shape = pict.find(".//v:shape", namespaces=NS)
        if shape is not None:
            shape_id = shape.get(qn(V, "id"))
            if shape_id:
                record["vml_id"] = shape_id
        records.append(record)
    return records


# ---------------------------------------------------------------------------
# 段落 / run 记录
# ---------------------------------------------------------------------------
def paragraph_record(
    paragraph,
    source_path: str,
    section_index: int,
    paragraph_index: int,
    table_index: int | None = None,
    row_index: int | None = None,
    cell_index: int | None = None,
    in_textbox: bool = False,
) -> dict[str, Any]:
    text = paragraph_text(paragraph)
    record: dict[str, Any] = {
        "record_type": "paragraph",
        "source_path": source_path,
        "location": "%s#p%d" % (source_path, paragraph_index),
        "section_index": section_index,
        "paragraph_index": paragraph_index,
        "text": text,
        "text_sha256": sha256_bytes(text.encode("utf-8")),
    }
    if table_index is not None:
        record["table_index"] = table_index
    if row_index is not None:
        record["row_index"] = row_index
    if cell_index is not None:
        record["cell_index"] = cell_index
    record.update(paragraph_properties(paragraph.find(wtag("pPr"), namespaces=NS)))
    if in_textbox:
        record["text_box"] = True
    special = paragraph_special_nodes(paragraph)
    if special:
        record["special_nodes"] = special
    return record


def paragraph_special_nodes(paragraph) -> list[dict[str, Any]]:
    special: list[dict[str, Any]] = []
    for hyperlink in paragraph.xpath(".//w:hyperlink", namespaces=NS):
        rid = hyperlink.get(qn(R, "id"))
        node: dict[str, Any] = {"tag": "hyperlink"}
        if rid:
            node["relationship"] = rid
        special.append(node)
    drawings = paragraph.xpath(".//w:drawing", namespaces=NS)
    if drawings:
        special.append({"tag": "drawing", "count": len(drawings)})
    fld_types = paragraph.xpath(".//w:fldChar/@w:fldCharType", namespaces=NS)
    if fld_types:
        special.append({"tag": "fldChar", "types": list(fld_types)})
    if paragraph.xpath(".//w:commentReference", namespaces=NS):
        special.append({"tag": "commentReference"})
    if paragraph.xpath(".//w:footnoteReference", namespaces=NS):
        special.append({"tag": "footnoteReference"})
    if paragraph.xpath(".//w:endnoteReference", namespaces=NS):
        special.append({"tag": "endnoteReference"})
    return special


def run_record(
    run,
    source_path: str,
    paragraph_index: int,
    run_index: int,
    section_index: int,
    table_index: int | None = None,
    row_index: int | None = None,
    cell_index: int | None = None,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "record_type": "run",
        "source_path": source_path,
        "location": "%s#p%d/r%d" % (source_path, paragraph_index, run_index),
        "section_index": section_index,
        "paragraph_index": paragraph_index,
        "run_index": run_index,
        "text": run_text_value(run),
    }
    if table_index is not None:
        record["table_index"] = table_index
    if row_index is not None:
        record["row_index"] = row_index
    if cell_index is not None:
        record["cell_index"] = cell_index
    record.update(run_properties(run.find(wtag("rPr"), namespaces=NS)))
    drawings = drawing_records(run)
    if drawings:
        record["drawings"] = drawings
    hyperlink = run.xpath("ancestor::w:hyperlink[1]", namespaces=NS)
    if hyperlink:
        rid = hyperlink[0].get(qn(R, "id"))
        if rid:
            record["hyperlink"] = rid
    field_types = run.xpath(".//w:fldChar/@w:fldCharType", namespaces=NS)
    if field_types:
        record["field_codes"] = list(field_types)
    return record


# ---------------------------------------------------------------------------
# 表格记录（含嵌套与合并）
# ---------------------------------------------------------------------------
def _parse_cell_margins(tc_pr) -> dict[str, int]:
    return read_margins(tc_pr, "w:tcMar")


def cell_properties(tc) -> dict[str, Any]:
    tc_pr = tc.find(wtag("tcPr"), namespaces=NS)
    if tc_pr is None:
        return {}
    out: dict[str, Any] = {}
    width_el = tc_pr.find(wtag("tcW"), namespaces=NS)
    if width_el is not None:
        width_type = attr_value(width_el)
        width_value = int_value(width_el, "w")
        if width_type is not None:
            out["width_type"] = width_type
        if width_value is not None:
            out["width"] = width_value
    span = int_value(tc_pr.find(wtag("gridSpan"), namespaces=NS))
    if span is not None:
        out["grid_span"] = span
    if tc_pr.find(wtag("hMerge"), namespaces=NS) is not None:
        out["horizontal_merge"] = True
    v_merge = tc_pr.find(wtag("vMerge"), namespaces=NS)
    if v_merge is not None:
        out["vertical_merge"] = attr_value(v_merge) or "continue"
    v_align = attr_value(tc_pr.find(wtag("vAlign"), namespaces=NS))
    if v_align is not None:
        out["vertical_align"] = v_align
    borders = tc_pr.find(wtag("tcBorders"), namespaces=NS)
    if borders is not None:
        out["borders"] = parse_borders(borders)
    shading = parse_shading(tc_pr.find(wtag("shd"), namespaces=NS))
    if shading:
        out["shading"] = shading
    margins = _parse_cell_margins(tc_pr)
    if margins:
        out["cell_margins"] = margins
    return out


def table_record(
    table,
    source_path: str,
    section_index: int,
    table_index: int,
    parent_table_index: int | None = None,
    nesting_level: int = 1,
) -> dict[str, Any]:
    tbl_pr = table.find(wtag("tblPr"), namespaces=NS)
    grid = [
        column.get(wqn("w"))
        for column in table.findall(wtag("tblGrid") + "/" + wtag("gridCol"), namespaces=NS)
    ]
    rows: list[dict[str, Any]] = []
    for row_index, tr in enumerate(table.findall(wtag("tr"), namespaces=NS), 1):
        tr_pr = tr.find(wtag("trPr"), namespaces=NS)
        cells: list[dict[str, Any]] = []
        for cell_index, tc in enumerate(tr.findall(wtag("tc"), namespaces=NS), 1):
            cells.append(
                {
                    "cell_index": cell_index,
                    "text": paragraph_text(tc),
                    "paragraph_count": len(tc.findall(wtag("p"), namespaces=NS)),
                    "properties": cell_properties(tc),
                }
            )
        row: dict[str, Any] = {"row_index": row_index, "cells": cells}
        if tr_pr is not None:
            height = tr_pr.find(wtag("trHeight"), namespaces=NS)
            if height is not None:
                height_value = int_value(height, "val")
                height_rule = attr_value(height, "hRule")
                if height_value is not None:
                    row["height"] = height_value
                if height_rule is not None:
                    row["height_rule"] = height_rule
            if tr_pr.find(wtag("tblHeader"), namespaces=NS) is not None:
                row["repeat_header"] = True
            if tr_pr.find(wtag("cantSplit"), namespaces=NS) is not None:
                row["cant_split"] = True
            grid_before = int_value(tr_pr.find(wtag("gridBefore"), namespaces=NS))
            if grid_before is not None:
                row["grid_before"] = grid_before
            grid_after = int_value(tr_pr.find(wtag("gridAfter"), namespaces=NS))
            if grid_after is not None:
                row["grid_after"] = grid_after
        rows.append(row)
    record: dict[str, Any] = {
        "record_type": "table",
        "source_path": source_path,
        "location": "%s#table%d" % (source_path, table_index),
        "section_index": section_index,
        "table_index": table_index,
        "nesting_level": nesting_level,
        "rows": rows,
    }
    if parent_table_index is not None:
        record["parent_table_index"] = parent_table_index
    if tbl_pr is not None:
        style = attr_value(tbl_pr.find(wtag("tblStyle"), namespaces=NS))
        if style is not None:
            record["table_style"] = style
        width_el = tbl_pr.find(wtag("tblW"), namespaces=NS)
        if width_el is not None:
            width_type = attr_value(width_el)
            width_value = int_value(width_el, "w")
            if width_type is not None:
                record["width_type"] = width_type
            if width_value is not None:
                record["width"] = width_value
        alignment = attr_value(tbl_pr.find(wtag("jc"), namespaces=NS))
        if alignment is not None:
            record["alignment"] = alignment
        borders = tbl_pr.find(wtag("tblBorders"), namespaces=NS)
        if borders is not None:
            record["borders"] = parse_borders(borders)
        shading = parse_shading(tbl_pr.find(wtag("shd"), namespaces=NS))
        if shading:
            record["shading"] = shading
        margins = read_margins(tbl_pr, "w:tblCellMar")
        if margins:
            record["cell_margins"] = margins
    if grid:
        record["grid"] = grid
    return record


def _paragraph_table_context(paragraph):
    """返回段落所在表格上下文 (table_index, row_index, cell_index, in_textbox)。"""
    tree = paragraph.getroottree()
    table_ancestors = paragraph.xpath("ancestor::w:tbl[1]", namespaces=NS)
    row_ancestors = paragraph.xpath("ancestor::w:tr[1]", namespaces=NS)
    cell_ancestors = paragraph.xpath("ancestor::w:tc[1]", namespaces=NS)
    if not (table_ancestors and row_ancestors and cell_ancestors):
        return None, None, None
    root = table_ancestors[0].getroottree().getroot()
    table_index = 0
    for index, table in enumerate(root.xpath(".//w:tbl", namespaces=NS), 1):
        if tree.getpath(table) == tree.getpath(table_ancestors[0]):
            table_index = index
            break
    return table_index, _sibling_index(row_ancestors[0], wtag("tr")), _sibling_index(
        cell_ancestors[0], wtag("tc")
    )


def _sibling_index(element, tag: str) -> int:
    parent = element.getparent()
    if parent is None:
        return 1
    return sum(
        1 for sibling in parent if sibling.tag == tag and sibling is not element
    ) + 1


def body_content(
    body, source_path: str, section_index: int, paragraph_counter: list[int]
) -> list[dict[str, Any]]:
    """按文档顺序遍历 body 内全部段落（含表格内、文本框内）。

    段落索引 = 文档序全局索引（与 read.py 语义一致）；表格内段落带
    table/row/cell 索引，文本框内段落标 text_box=True。
    """
    records: list[dict[str, Any]] = []
    for paragraph in body.xpath(".//w:p", namespaces=NS):
        paragraph_counter[0] += 1
        table_index, row_index, cell_index = _paragraph_table_context(paragraph)
        in_textbox = bool(paragraph.xpath("ancestor::w:txbxContent", namespaces=NS))
        records.append(
            paragraph_record(
                paragraph,
                source_path,
                section_index,
                paragraph_counter[0],
                table_index=table_index,
                row_index=row_index,
                cell_index=cell_index,
                in_textbox=in_textbox,
            )
        )
    return records


def story_tables(root, source_path: str, section_index: int) -> list[dict[str, Any]]:
    """全部表格记录（文档序，含嵌套层级与父表索引）。"""
    tree = root.getroottree()
    records: list[dict[str, Any]] = []
    for table_index, table in enumerate(root.xpath(".//w:tbl", namespaces=NS), 1):
        parent_ancestors = table.xpath("ancestor::w:tbl[1]", namespaces=NS)
        nesting_level = 1
        parent_table_index = None
        if parent_ancestors:
            for index, candidate in enumerate(root.xpath(".//w:tbl", namespaces=NS), 1):
                if tree.getpath(candidate) == tree.getpath(parent_ancestors[0]):
                    parent_table_index = index
                    break
            nesting_level = parent_table_index is not None and 2 or 1
        records.append(
            table_record(
                table,
                source_path,
                section_index,
                table_index,
                parent_table_index=parent_table_index,
                nesting_level=nesting_level,
            )
        )
    return records


def story_paragraphs_runs(
    root, source_path: str, section_index: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """一次性产出段落与 run 两组记录（dim 2/3 共用，保证索引一致）。"""
    paragraph_counter = [0]
    paragraphs = body_content(
        root.find(wtag("body"), namespaces=NS), source_path, section_index, paragraph_counter
    )
    runs: list[dict[str, Any]] = []
    for paragraph in paragraphs:
        paragraph_element = _locate_paragraph(root, paragraph["paragraph_index"])
        if paragraph_element is None:
            continue
        run_index = 0
        for run in paragraph_element.xpath(".//w:r", namespaces=NS):
            run_index += 1
            runs.append(
                run_record(
                    run,
                    source_path,
                    paragraph["paragraph_index"],
                    run_index,
                    section_index,
                    table_index=paragraph.get("table_index"),
                    row_index=paragraph.get("row_index"),
                    cell_index=paragraph.get("cell_index"),
                )
            )
    return paragraphs, runs


def _locate_paragraph(root, paragraph_index: int):
    """按文档序定位第 N 个段落（含表格内、文本框内）。"""
    for index, p in enumerate(root.xpath(".//w:body//w:p", namespaces=NS), 1):
        if index == paragraph_index:
            return p
    return None
