# -*- coding: utf-8 -*-
"""docx_tools.reader_sections_styles：分节（dim 1）与样式（dim 4）记录提取。

能力逻辑借鉴豆包 word 技能 read.py（平台无关重写）：分节含纸张/页边距/分栏/
页眉页脚引用（继承补全），样式含 docDefaults 与 based_on 链。
"""
from __future__ import annotations

from typing import Any

from lxml import etree

from .common import (
    NS,
    R,
    W,
    W14,
    attr_value,
    canonical_xml_hash,
    int_value,
    on_off_attribute,
    on_off_value,
    parse_borders,
    parse_shading,
    qn,
    read_margins,
    sha256_bytes,
    wqn,
    wtag,
)


def extract_sections_record(
    body, source_path: str
) -> list[dict[str, Any]]:
    """w:body 下全部 sectPr（含嵌套在段落内的分节符）。"""
    records: list[dict[str, Any]] = []
    for index, section in enumerate(
        body.xpath(".//w:sectPr[not(ancestor::w:sectPrChange)]", namespaces=NS), 1
    ):
        size = section.find(wtag("pgSz"), namespaces=NS)
        margins = section.find(wtag("pgMar"), namespaces=NS)
        section_type = section.find(wtag("type"), namespaces=NS)
        cols = section.find(wtag("cols"), namespaces=NS)
        page_numbering = section.find(wtag("pgNumType"), namespaces=NS)
        width = int_value(size, "w")
        height = int_value(size, "h")
        orientation = size.get(wqn("orient")) if size is not None else None
        if orientation is None and width is not None and height is not None:
            orientation = "landscape" if width > height else "portrait"
        margin_values: dict[str, int | None] = {}
        for name in ("top", "right", "bottom", "left", "header", "footer", "gutter"):
            margin_values["%s_dxa" % name] = int_value(margins, name)
        records.append(
            {
                "record_type": "section",
                "source_path": source_path,
                "location": "%s#sect%d" % (source_path, index),
                "section_index": index,
                "page": {
                    "width_dxa": width,
                    "height_dxa": height,
                    "width_token": size.get(wqn("w")) if size is not None else None,
                    "height_token": size.get(wqn("h")) if size is not None else None,
                    "orientation": orientation,
                    "margins": margin_values,
                },
                "start_type": attr_value(section_type) or "nextPage",
                "different_first_page": section.find(wtag("titlePg"), namespaces=NS) is not None,
                "columns": {
                    "count": int_value(cols, "num") if cols is not None else None,
                    "space_dxa": int_value(cols, "space") if cols is not None else None,
                    "separator": on_off_attribute(cols, "sep"),
                },
                "page_numbering": _word_attributes(
                    page_numbering, ("start", "fmt", "chapStyle", "chapSep")
                ),
                "vertical_alignment": attr_value(section.find(wtag("vAlign"), namespaces=NS)),
                "text_direction": attr_value(section.find(wtag("textDirection"), namespaces=NS)),
                "document_grid": _word_attributes(
                    section.find(wtag("docGrid"), namespaces=NS),
                    ("type", "linePitch", "charSpace"),
                ),
                "line_numbering": _word_attributes(
                    section.find(wtag("lnNumType"), namespaces=NS),
                    ("countBy", "start", "distance", "restart"),
                ),
                "page_borders": parse_borders(section.find(wtag("pgBorders"), namespaces=NS)),
                "header_references": [
                    {"type": item.get(wqn("type")), "rId": item.get(qn(R, "id"))}
                    for item in section.findall(wtag("headerReference"), namespaces=NS)
                ],
                "footer_references": [
                    {"type": item.get(wqn("type")), "rId": item.get(qn(R, "id"))}
                    for item in section.findall(wtag("footerReference"), namespaces=NS)
                ],
            }
        )
    return records


def _word_attributes(element, names: tuple[str, ...]) -> dict[str, str]:
    if element is None:
        return {}
    return {
        name: value
        for name in names
        if (value := element.get(wqn(name))) is not None
    }


def add_effective_story_references(sections: list[dict[str, Any]]) -> None:
    """按节继承补全页眉页脚引用（未显式声明节沿用前节）。"""
    inherited: dict[str, dict[str, dict[str, Any]]] = {"header": {}, "footer": {}}
    for section in sections:
        for family in ("header", "footer"):
            effective = dict(inherited[family])
            for reference in section.get("%s_references" % family, []):
                reference_type = str(reference.get("type") or "default")
                effective[reference_type] = {
                    "type": reference_type,
                    "rId": reference.get("rId"),
                }
            section["effective_%s_references" % family] = [
                effective[reference_type] for reference_type in sorted(effective)
            ]
            inherited[family] = effective


# ---------------------------------------------------------------------------
# 样式（dim 4）：docDefaults + style 记录
# ---------------------------------------------------------------------------
def parse_rpr_simple(rpr) -> dict[str, Any]:
    if rpr is None:
        return {}
    out: dict[str, Any] = {}
    style = attr_value(rpr.find(wtag("rStyle"), namespaces=NS))
    if style is not None:
        out["style_id"] = style
    fonts = rpr.find(wtag("rFonts"), namespaces=NS)
    if fonts is not None:
        font_record: dict[str, Any] = {}
        for name in ("ascii", "eastAsia", "hAnsi", "cs"):
            value = fonts.get(wqn(name))
            if value is not None:
                font_record[name] = value
        if font_record:
            out["fonts"] = font_record
    bold = rpr.find(wtag("b"), namespaces=NS)
    if bold is not None:
        out["bold"] = True if on_off_value(bold) is None else on_off_value(bold)
    italic = rpr.find(wtag("i"), namespaces=NS)
    if italic is not None:
        out["italic"] = True if on_off_value(italic) is None else on_off_value(italic)
    size = int_value(rpr.find(wtag("sz"), namespaces=NS))
    if size is not None:
        out["size_half_points"] = size
    sz_cs = int_value(rpr.find(wtag("szCs"), namespaces=NS))
    if sz_cs is not None:
        out["size_cs_half_points"] = sz_cs
    underline = rpr.find(wtag("u"), namespaces=NS)
    if underline is not None:
        out["underline"] = attr_value(underline) or "single"
    color = rpr.find(wtag("color"), namespaces=NS)
    if color is not None:
        out["color"] = color.get(wqn("val"))
    caps = rpr.find(wtag("caps"), namespaces=NS)
    if caps is not None:
        out["caps"] = True if on_off_value(caps) is None else on_off_value(caps)
    small_caps = rpr.find(wtag("smallCaps"), namespaces=NS)
    if small_caps is not None:
        out["small_caps"] = (
            True if on_off_value(small_caps) is None else on_off_value(small_caps)
        )
    strike = rpr.find(wtag("strike"), namespaces=NS)
    if strike is not None:
        out["strike"] = True if on_off_value(strike) is None else on_off_value(strike)
    vert_align = attr_value(rpr.find(wtag("vertAlign"), namespaces=NS))
    if vert_align is not None:
        out["vertical_align"] = vert_align
    return out


def parse_ppr_simple(ppr) -> dict[str, Any]:
    if ppr is None:
        return {}
    out: dict[str, Any] = {}
    style = attr_value(ppr.find(wtag("pStyle"), namespaces=NS))
    if style is not None:
        out["style_id"] = style
    align = attr_value(ppr.find(wtag("jc"), namespaces=NS))
    if align is not None:
        out["alignment"] = align
    num_pr = ppr.find(wtag("numPr"), namespaces=NS)
    if num_pr is not None:
        numbering: dict[str, Any] = {}
        num_id = int_value(num_pr.find(wtag("numId"), namespaces=NS))
        ilvl = int_value(num_pr.find(wtag("ilvl"), namespaces=NS))
        if num_id is not None:
            numbering["num_id"] = num_id
        if ilvl is not None:
            numbering["ilvl"] = ilvl
        if numbering:
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
        for name in ("before", "after", "line"):
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
    ):
        el = ppr.find(wtag(tag), namespaces=NS)
        if el is not None:
            out[key] = True if on_off_value(el) is None else on_off_value(el)
    return out


def extract_styles_record(root) -> dict[str, Any]:
    """解析 word/styles.xml → docDefaults + 样式定义表（含 tblStylePr 条件格式）。"""
    result: dict[str, Any] = {
        "source_part": "word/styles.xml",
        "doc_defaults": {},
        "styles": [],
        "count": 0,
    }
    if root is None:
        return result
    doc_defaults = root.find(wtag("docDefaults"), namespaces=NS)
    if doc_defaults is not None:
        defaults: dict[str, Any] = {}
        rpr_default = doc_defaults.find(wtag("rPrDefault") + "/" + wtag("rPr"), namespaces=NS)
        if rpr_default is not None:
            defaults["rPr"] = parse_rpr_simple(rpr_default)
        ppr_default = doc_defaults.find(wtag("pPrDefault") + "/" + wtag("pPr"), namespaces=NS)
        if ppr_default is not None:
            defaults["pPr"] = parse_ppr_simple(ppr_default)
        if defaults:
            result["doc_defaults"] = defaults
    styles: list[dict[str, Any]] = []
    for style in root.findall(wtag("style"), namespaces=NS):
        style_id = style.get(wqn("styleId"))
        record: dict[str, Any] = {
            "style_id": style_id,
            "type": style.get(wqn("type")),
        }
        name_el = style.find(wtag("name"), namespaces=NS)
        if name_el is not None:
            record["name"] = name_el.get(wqn("val"))
        based_on = attr_value(style.find(wtag("basedOn"), namespaces=NS))
        if based_on is not None:
            record["based_on"] = based_on
        next_el = style.find(wtag("next"), namespaces=NS)
        if next_el is not None:
            record["next"] = next_el.get(wqn("val"))
        default_val = style.get(wqn("default"))  # w:default 是 w:style 属性
        if default_val is not None:
            record["default"] = default_val
        hidden_el = style.find(wtag("hidden"), namespaces=NS)
        if hidden_el is not None:
            record["hidden"] = True
        ui_priority = int_value(style.find(wtag("uiPriority"), namespaces=NS))
        if ui_priority is not None:
            record["ui_priority"] = ui_priority
        link_el = style.find(wtag("link"), namespaces=NS)
        if link_el is not None:
            record["link"] = link_el.get(wqn("val"))
        aliases_el = style.find(wtag("aliases"), namespaces=NS)
        if aliases_el is not None:
            record["aliases"] = aliases_el.get(wqn("val"))
        rpr = parse_rpr_simple(style.find(wtag("rPr"), namespaces=NS))
        if rpr:
            record["rPr"] = rpr
        ppr = parse_ppr_simple(style.find(wtag("pPr"), namespaces=NS))
        if ppr:
            record["pPr"] = ppr
        tbl_pr = style.find(wtag("tblPr"), namespaces=NS)
        if tbl_pr is not None:
            table_record: dict[str, Any] = {}
            tbl_style = attr_value(tbl_pr.find(wtag("tblStyle"), namespaces=NS))
            if tbl_style is not None:
                table_record["style_id"] = tbl_style
            borders = tbl_pr.find(wtag("tblBorders"), namespaces=NS)
            if borders is not None:
                table_record["borders"] = parse_borders(borders)
            shading = parse_shading(tbl_pr.find(wtag("shd"), namespaces=NS))
            if shading:
                table_record["shading"] = shading
            width_el = tbl_pr.find(wtag("tblW"), namespaces=NS)
            if width_el is not None:
                width_value = int_value(width_el, "w")
                if width_value is not None:
                    table_record["width_dxa"] = width_value
            if table_record:
                record["tblPr"] = table_record
        conditional = _extract_tbl_style_pr(style)
        if conditional:
            record["conditional_table_properties"] = conditional
        styles.append(record)
    result["styles"] = styles
    result["count"] = len(styles)
    return result


def _extract_tbl_style_pr(style) -> dict[str, Any]:
    """tblStylePr 条件格式（firstRow 底纹等），供 effective_table_properties。"""
    conditional: dict[str, Any] = {}
    for tbl_style_pr in style.findall(wtag("tblStylePr"), namespaces=NS):
        key = tbl_style_pr.get(wqn("type"))
        if not key:
            continue
        value: dict[str, Any] = {}
        shading = parse_shading(
            tbl_style_pr.find(wtag("tcPr") + "/" + wtag("shd"), namespaces=NS)
        )
        if shading:
            value["cell_shading"] = shading
        borders = tbl_style_pr.find(wtag("tcPr") + "/" + wtag("tcBorders"), namespaces=NS)
        if borders is not None:
            value["cell_borders"] = parse_borders(borders)
        if value:
            conditional[key] = value
    return conditional


def effective_style(styles: list[dict[str, Any]], style_id: str | None) -> dict[str, Any]:
    """沿 based_on 链深合并出最终生效样式（docDefaults 为基座）。"""
    from .common import deep_merge

    by_id: dict[str, dict[str, Any]] = {
        str(style.get("style_id")): style for style in styles
    }
    result: dict[str, Any] = {}
    seen: set[str] = set()
    cursor = str(style_id) if style_id else None
    while cursor and cursor not in seen:
        seen.add(cursor)
        record = by_id.get(cursor)
        if record is None:
            break
        result = deep_merge(result, _style_format_fragment(record))
        cursor = str(record.get("based_on")) if record.get("based_on") else None
    return result


def _style_format_fragment(record: dict[str, Any]) -> dict[str, Any]:
    fragment: dict[str, Any] = {}
    if record.get("rPr"):
        fragment["rPr"] = record["rPr"]
    if record.get("pPr"):
        fragment["pPr"] = record["pPr"]
    if record.get("tblPr"):
        fragment["tblPr"] = record["tblPr"]
    return fragment


def effective_table_properties(styles, style_id: str | None) -> dict[str, Any]:
    """表格样式的最终生效 tblPr（含 based_on 继承）。"""
    from .common import deep_merge

    by_id: dict[str, dict[str, Any]] = {
        str(style.get("style_id")): style for style in styles
    }
    result: dict[str, Any] = {}
    seen: set[str] = set()
    cursor = str(style_id) if style_id else None
    while cursor and cursor not in seen:
        seen.add(cursor)
        record = by_id.get(cursor)
        if record is None:
            break
        if record.get("tblPr"):
            result = deep_merge(result, record["tblPr"])
        cursor = str(record.get("based_on")) if record.get("based_on") else None
    return result
