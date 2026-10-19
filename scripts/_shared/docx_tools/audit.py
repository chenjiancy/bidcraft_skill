# -*- coding: utf-8 -*-
"""docx_tools.audit：docx 格式/结构审计核心（核心五件套之一）。

范围：样式继承解析、段落与 run 属性解析、OOXML 属性解析（parse_rpr/ppr/
table_properties/cnf_style）、issue 契约。配合 audit_extract（表格/分节/绘图/
结构 hash/属性顺序）与 audit_cli（包检查 + 报告）使用。
能力逻辑借鉴豆包 word 技能 audit.py（平台无关重写，非整文件复制）。
"""
from __future__ import annotations

from typing import Any

from lxml import etree

from .common import (
    NS,
    W,
    W14,
    attr_value,
    deep_merge,
    int_value,
    on_off_value,
    parse_borders,
    parse_shading,
    read_margins,
    sha256_bytes,
    wqn,
    wtag,
)

# ---------------------------------------------------------------------------
# issue 契约
# ---------------------------------------------------------------------------
def issue(
    severity: str,
    code: str,
    location: str,
    message: str,
    *,
    expected: Any = None,
    actual: Any = None,
    repair_hint: str | None = None,
    evidence: dict[str, Any] | None = None,
    blocking: bool = False,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "severity": severity,
        "code": code,
        "location": str(location),
        "message": str(message),
    }
    if expected is not None:
        record["expected"] = expected
    if actual is not None:
        record["actual"] = actual
    if repair_hint:
        record["repair_hint"] = repair_hint
    if evidence:
        record["evidence"] = evidence
    if blocking:
        record["blocking"] = True
    return record


REPAIR_HINTS: dict[str, str] = {
    "E_ZIP_CRC": "重新生成/修复 docx 压缩包（zip 校验失败），再用 Word 打开确认无损。",
    "E_ZIP_MEMBER_DUPLICATE": "删除重复的 zip 成员（同一部件名出现多次），保持包内唯一。",
    "E_PART_MISSING": "补齐缺失的 OOXML 必需部件（[Content_Types].xml / _rels/.rels / word/document.xml），用 Word 重新保存。",
    "E_XML_INVALID": "修复该部件的 XML 语法/DTD/实体引用问题，用 Word 重新保存后再审计。",
    "E_DOCUMENT_ROOT_INVALID": "word/document.xml 根节点必须是 w:document 且仅含一个 w:body，用 Word 重新保存。",
    "E_DOCX_OPEN": "文件不是有效的 OOXML 压缩包，检查扩展名与文件完整性。",
    "E_OOXML_TBLPR_ORDER": "按 OOXML 模式顺序重排 w:tblPr 子元素（见 expected 序列），用 schema 感知 API 重建后重新审计。",
    "E_OOXML_TCPR_ORDER": "按 OOXML 模式顺序重排 w:tcPr 子元素（见 expected 序列），用 schema 感知 API 重建后重新审计。",
    "E_OOXML_DOCPR_ID_INVALID": "wp:docPr/@id 必须为无符号 32 位整数且全局唯一，改用 Word 重新插入图片/对象。",
    "E_DRAWING_EXTENT_INVALID": "wp:extent/@cx、@cy 必须为非负整数，改用 Word 重新插入图片/对象。",
    "E_BASELINE_SOURCE_INVALID": "基线 docx（--source）无法用于比较：修复其包级问题后重跑。",
}


def enrich_findings(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """补齐 repair_hint / blocking 兜底，保证下游报告字段完整。"""
    for finding in findings:
        if not finding.get("repair_hint"):
            finding["repair_hint"] = REPAIR_HINTS.get(finding.get("code", ""), "")
        if finding.get("severity") == "error" and not finding.get("blocking"):
            finding["blocking"] = True
    return findings


# ---------------------------------------------------------------------------
# OOXML 属性解析
# ---------------------------------------------------------------------------
def word_attributes(
    element: etree._Element | None, names: tuple[str, ...]
) -> dict[str, str]:
    if element is None:
        return {}
    return {
        name: value
        for name in names
        if (value := element.get(wqn(name))) is not None
    }


def parse_cnf_style(element: etree._Element | None) -> dict[str, bool]:
    """w:cnfStyle → 启用条件格式标志映射（位掩码 + 显式属性双形式）。"""
    if element is None:
        return {}
    bit_flags = [
        ("firstRow", 0), ("lastRow", 1), ("firstColumn", 2), ("lastColumn", 3),
        ("oddVBand", 4), ("evenVBand", 5), ("oddHBand", 6), ("evenHBand", 7),
        ("firstRowFirstColumn", 8), ("firstRowLastColumn", 9),
        ("lastRowFirstColumn", 10), ("lastRowLastColumn", 11),
    ]
    flags: dict[str, bool] = {}
    raw_val = element.get(wqn("val"))
    if raw_val:
        for name, position in bit_flags:
            if position < len(raw_val) and raw_val[position] == "1":
                flags[name] = True
    for name, _ in bit_flags:
        explicit = element.get(wqn(name))
        if explicit is not None:
            flags[name] = explicit.strip().lower() not in {"0", "false", "off", "no"}
    return {name: value for name, value in flags.items() if value}


def parse_table_properties(tbl_pr: etree._Element | None) -> dict[str, Any]:
    if tbl_pr is None:
        return {}
    out: dict[str, Any] = {}
    style = attr_value(tbl_pr.find(wtag("tblStyle"), namespaces=NS))
    if style is not None:
        out["style_id"] = style
    width = tbl_pr.find(wtag("tblW"), namespaces=NS)
    if width is not None:
        width_type = width.get(wqn("type"))
        width_value = int_value(width, "w")
        if width_type is not None:
            out["width_type"] = width_type
        if width_value is not None:
            out["width_dxa"] = width_value
    indent = tbl_pr.find(wtag("tblInd"), namespaces=NS)
    if indent is not None:
        indent_type = indent.get(wqn("type"))
        indent_value = int_value(indent, "w")
        if indent_type is not None:
            out["indent_type"] = indent_type
        if indent_value is not None:
            out["indent_dxa"] = indent_value
    layout_type = attr_value(tbl_pr.find(wtag("tblLayout"), namespaces=NS))
    if layout_type is not None:
        out["layout"] = layout_type
    alignment = attr_value(tbl_pr.find(wtag("jc"), namespaces=NS))
    if alignment is not None:
        out["alignment"] = alignment
    overlap = attr_value(tbl_pr.find(wtag("tblOverlap"), namespaces=NS))
    if overlap is not None:
        out["overlap"] = overlap
    bidi_visual = on_off_value(tbl_pr.find(wtag("bidiVisual"), namespaces=NS))
    if bidi_visual is not None:
        out["bidi_visual"] = bidi_visual
    row_band_size = int_value(tbl_pr.find(wtag("tblStyleRowBandSize"), namespaces=NS))
    if row_band_size is not None:
        out["row_band_size"] = row_band_size
    column_band_size = int_value(tbl_pr.find(wtag("tblStyleColBandSize"), namespaces=NS))
    if column_band_size is not None:
        out["column_band_size"] = column_band_size
    cell_spacing = tbl_pr.find(wtag("tblCellSpacing"), namespaces=NS)
    if cell_spacing is not None:
        out["cell_spacing"] = word_attributes(cell_spacing, ("w", "type"))
    margins = read_margins(tbl_pr, "w:tblCellMar")
    if margins:
        out["cell_margins_dxa"] = margins
    borders = tbl_pr.find(wtag("tblBorders"), namespaces=NS)
    if borders is not None:
        out["borders"] = parse_borders(borders)
    shading = parse_shading(tbl_pr.find(wtag("shd"), namespaces=NS))
    if shading:
        out["shading"] = shading
    table_look = word_attributes(
        tbl_pr.find(wtag("tblLook"), namespaces=NS),
        ("val", "firstRow", "lastRow", "firstColumn", "lastColumn", "noHBand", "noVBand"),
    )
    if table_look:
        out["look"] = table_look
    positioning = word_attributes(
        tbl_pr.find(wtag("tblpPr"), namespaces=NS),
        (
            "leftFromText", "rightFromText", "topFromText", "bottomFromText",
            "vertAnchor", "horzAnchor", "tblpX", "tblpY", "tblpXSpec", "tblpYSpec",
        ),
    )
    if positioning:
        out["positioning"] = positioning
    return out


def parse_rpr(rpr: etree._Element | None) -> dict[str, Any]:
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
    for key, tag in (
        ("bold", "b"), ("italic", "i"), ("caps", "caps"),
        ("small_caps", "smallCaps"), ("strike", "strike"),
        ("double_strike", "dstrike"), ("emboss", "emboss"),
        ("imprint", "imprint"), ("shadow", "shadow"),
        ("outline", "outline"), ("no_proof", "noProof"),
    ):
        element = rpr.find(wtag(tag), namespaces=NS)
        if element is not None:
            out[key] = True if on_off_value(element) is None else on_off_value(element)
    underline = rpr.find(wtag("u"), namespaces=NS)
    if underline is not None:
        out["underline"] = word_attributes(underline, ("val", "color", "themeColor"))
    color = rpr.find(wtag("color"), namespaces=NS)
    if color is not None:
        out["color"] = word_attributes(
            color, ("val", "themeColor", "themeShade", "themeTint")
        )
    highlight = attr_value(rpr.find(wtag("highlight"), namespaces=NS))
    if highlight is not None:
        out["highlight"] = highlight
    size = int_value(rpr.find(wtag("sz"), namespaces=NS))
    if size is not None:
        out["size_half_points"] = size
    size_cs = int_value(rpr.find(wtag("szCs"), namespaces=NS))
    if size_cs is not None:
        out["size_cs_half_points"] = size_cs
    vert_align = attr_value(rpr.find(wtag("vertAlign"), namespaces=NS))
    if vert_align is not None:
        out["vertical_align"] = vert_align
    lang = rpr.find(wtag("lang"), namespaces=NS)
    if lang is not None:
        lang_record: dict[str, Any] = {}
        for name in ("val", "eastAsia", "bidi"):
            value = lang.get(wqn(name))
            if value is not None:
                lang_record[name] = value
        if lang_record:
            out["lang"] = lang_record
    spacing = int_value(rpr.find(wtag("spacing"), namespaces=NS))
    if spacing is not None:
        out["character_spacing"] = spacing
    position = int_value(rpr.find(wtag("position"), namespaces=NS))
    if position is not None:
        out["position_twips"] = position
    return out


def parse_ppr(ppr: etree._Element | None) -> dict[str, Any]:
    if ppr is None:
        return {}
    out: dict[str, Any] = {}
    style = attr_value(ppr.find(wtag("pStyle"), namespaces=NS))
    if style is not None:
        out["style_id"] = style
    for key, tag in (
        ("keep_with_next", "keepNext"), ("keep_lines", "keepLines"),
        ("page_break_before", "pageBreakBefore"),
    ):
        element = ppr.find(wtag(tag), namespaces=NS)
        if element is not None:
            out[key] = True if on_off_value(element) is None else on_off_value(element)
    widow = ppr.find(wtag("widowControl"), namespaces=NS)
    if widow is not None:
        out["widow_control"] = on_off_value(widow)
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
        for name in (
            "left", "right", "start", "end", "firstLine", "hanging",
            "firstLineChars", "hangingChars",
        ):
            value = int_value(ind, name)
            if value is not None:
                indent[name] = value
        if indent:
            out["indent"] = indent
    alignment = attr_value(ppr.find(wtag("jc"), namespaces=NS))
    if alignment is not None:
        out["alignment"] = alignment
    outline = int_value(ppr.find(wtag("outlineLvl"), namespaces=NS))
    if outline is not None:
        out["outline_level"] = outline
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
    borders = ppr.find(wtag("pBdr"), namespaces=NS)
    if borders is not None:
        out["borders"] = parse_borders(borders)
    shading = parse_shading(ppr.find(wtag("shd"), namespaces=NS))
    if shading:
        out["shading"] = shading
    cnf = parse_cnf_style(ppr.find(wtag("cnfStyle"), namespaces=NS))
    if cnf:
        out["cnf_style"] = cnf
    contextual = on_off_value(ppr.find(wtag("contextualSpacing"), namespaces=NS))
    if contextual is not None:
        out["contextual_spacing"] = contextual
    return out


# ---------------------------------------------------------------------------
# 样式表提取与继承
# ---------------------------------------------------------------------------
def extract_styles(xml_roots: dict[str, etree._Element]) -> dict[str, Any]:
    root = xml_roots.get("word/styles.xml")
    styles: dict[str, dict[str, Any]] = {}
    doc_defaults: dict[str, Any] = {"rPr": {}, "pPr": {}}
    default_style_ids: dict[str, str] = {}
    if root is not None:
        doc_defaults_node = root.find(wtag("docDefaults"), namespaces=NS)
        if doc_defaults_node is not None:
            rpr_default = doc_defaults_node.find(
                wtag("rPrDefault") + "/" + wtag("rPr"), NS
            )
            if rpr_default is not None:
                doc_defaults["rPr"] = parse_rpr(rpr_default)
            ppr_default = doc_defaults_node.find(
                wtag("pPrDefault") + "/" + wtag("pPr"), NS
            )
            if ppr_default is not None:
                doc_defaults["pPr"] = parse_ppr(ppr_default)
        for style in root.findall(wtag("style"), namespaces=NS):
            style_id = style.get(wqn("styleId"))
            if not style_id:
                continue
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
            rpr = parse_rpr(style.find(wtag("rPr"), namespaces=NS))
            if rpr:
                record["rPr"] = rpr
            ppr = parse_ppr(style.find(wtag("pPr"), namespaces=NS))
            if ppr:
                record["pPr"] = ppr
            tbl_pr = parse_table_properties(style.find(wtag("tblPr"), namespaces=NS))
            if tbl_pr:
                record["tblPr"] = tbl_pr
            conditional = _conditional_table_properties(style)
            if conditional:
                record["conditional_table_properties"] = conditional
            styles[style_id] = record
            if record.get("default"):
                default_type = record.get("type")
                if default_type in ("paragraph", "character", "table", "numbering"):
                    default_style_ids.setdefault(default_type, style_id)
    return {
        "styles": styles,
        "doc_defaults": doc_defaults,
        "default_style_ids": default_style_ids,
    }


def _conditional_table_properties(style) -> dict[str, Any]:
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


def effective_style(style_manifest: dict[str, Any], style_id: str | None) -> dict[str, Any]:
    """沿 based_on 链深合并出最终生效格式（docDefaults 为基座）。"""
    records = style_manifest.get("styles", {})
    result: dict[str, Any] = {
        "rPr": deep_merge({}, style_manifest.get("doc_defaults", {}).get("rPr", {})),
        "pPr": deep_merge({}, style_manifest.get("doc_defaults", {}).get("pPr", {})),
    }
    seen: set[str] = set()
    cursor = str(style_id) if style_id else None
    while cursor and cursor not in seen:
        seen.add(cursor)
        record = records.get(cursor)
        if record is None:
            break
        if record.get("rPr"):
            result["rPr"] = deep_merge(result["rPr"], record["rPr"])
        if record.get("pPr"):
            result["pPr"] = deep_merge(result["pPr"], record["pPr"])
        if record.get("tblPr"):
            result.setdefault("tblPr", {})
            result["tblPr"] = deep_merge(result["tblPr"], record["tblPr"])
        cursor = str(record.get("based_on")) if record.get("based_on") else None
    return result


def effective_table_properties(
    style_manifest: dict[str, Any], style_id: str | None
) -> dict[str, Any]:
    """表格样式最终生效 tblPr（沿 based_on 继承，不含 docDefaults）。"""
    records = style_manifest.get("styles", {})
    result: dict[str, Any] = {}
    seen: set[str] = set()
    cursor = str(style_id) if style_id else None
    while cursor and cursor not in seen:
        seen.add(cursor)
        record = records.get(cursor)
        if record is None:
            break
        if record.get("tblPr"):
            result = deep_merge(result, record["tblPr"])
        cursor = str(record.get("based_on")) if record.get("based_on") else None
    return result
