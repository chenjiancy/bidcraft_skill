# -*- coding: utf-8 -*-
"""docx_tools.audit_extract：审计用提取与检查（核心五件套之二）。

覆盖：段落（含表格上下文/条件格式/修订状态）、表格（含合并与网格列）、
分节、绘图对象、结构 hash、OOXML 属性顺序检查。
能力逻辑借鉴豆包 word 技能 audit.py（平台无关重写，非整文件复制）。
"""
from __future__ import annotations

import re
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
    parse_borders,
    parse_shading,
    paragraph_text,
    qn,
    sha256_bytes,
    wqn,
    wtag,
)
from .audit import parse_cnf_style, parse_ppr, parse_rpr, issue
from .reader_sections_styles import add_effective_story_references, extract_sections_record

TOC_FIELD_RE = re.compile(r"^\s*TOC(?=\s|\\|$)", re.IGNORECASE)
HAN_CODEPOINT_RANGES = (
    (0x3400, 0x4DBF), (0x4E00, 0x9FFF), (0xF900, 0xFAFF),
    (0x20000, 0x2A6DF), (0x2A700, 0x2B73F), (0x2B740, 0x2B81F),
    (0x2B820, 0x2CEAF), (0x2CEB0, 0x2EBEF), (0x2F800, 0x2FA1F),
    (0x30000, 0x323AF),
)


# ---------------------------------------------------------------------------
# TOC / 修订辅助
# ---------------------------------------------------------------------------
def toc_result_text_nodes(root: etree._Element) -> set[etree._Element]:
    """TOC 域结果区内的 w:t 节点（占位/缓存目录，不算最终正文）。"""
    text_nodes: set[etree._Element] = set()
    for paragraph in root.xpath(".//w:p", namespaces=NS):
        fld_chars = paragraph.xpath(".//w:fldChar", namespaces=NS)
        if not fld_chars:
            continue
        instructions = " ".join(paragraph.xpath(".//w:instrText/text()", namespaces=NS))
        if not TOC_FIELD_RE.search(instructions):
            continue
        started = False
        for fld_char in fld_chars:
            kind = fld_char.get(wqn("fldCharType"))
            if kind == "begin":
                started = True
            elif kind == "separate":
                started = True
            elif kind == "end":
                started = False
                break
            if started:
                text_nodes.update(
                    fld_char.xpath("following::w:t[1] | ../following-sibling::*//w:t[1]", namespaces=NS)
                )
    return text_nodes


def run_word_count_text(run: etree._Element) -> dict[str, int]:
    """run 文本字数（汉字字符 + 非汉字单词），供记录参考。"""
    text = "".join(run.xpath("./w:t/text()", namespaces=NS))
    han = sum(1 for ch in text if _is_han(ch))
    rest = re.sub(r"\s+", " ", re.sub(r"[^\w\s\u4e00-\u9fff]", "", text)).strip()
    words = len(rest.split()) if rest else 0
    return {"han_characters": han, "words": words}


def _is_han(character: str) -> bool:
    codepoint = ord(character)
    return any(start <= codepoint <= end for start, end in HAN_CODEPOINT_RANGES)


def paragraph_revision_text_state(paragraph: etree._Element) -> str | None:
    if paragraph.findall(".//w:delText", namespaces=NS):
        return "deleted"
    if paragraph.xpath(".//w:moveFrom | .//w:moveTo | ancestor::w:moveFrom | ancestor::w:moveTo", namespaces=NS):
        return "moved"
    return None


# ---------------------------------------------------------------------------
# 段落提取（含表格上下文）
# ---------------------------------------------------------------------------
def extract_paragraphs(part: str, root: etree._Element) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    tree = root.getroottree()
    toc_text_nodes = toc_result_text_nodes(root)
    table_contexts: dict[str, dict[str, Any]] = {}
    for table_index, table in enumerate(root.xpath(".//w:tbl", namespaces=NS), 1):
        table_path = tree.getpath(table)
        rows = table.findall(wtag("tr"), namespaces=NS)
        grid_column_count = len(table.findall(wtag("tblGrid") + "/" + wtag("gridCol"), namespaces=NS))
        if not grid_column_count:
            grid_column_count = max(
                (
                    sum(
                        int_value(cell.find(wtag("tcPr") + "/" + wtag("gridSpan"), namespaces=NS)) or 1
                        for cell in row.findall(wtag("tc"), namespaces=NS)
                    )
                    for row in rows
                ),
                default=0,
            )
        row_contexts: dict[str, dict[str, Any]] = {}
        row_cell_counts: list[int] = []
        table_has_horizontal_merge = False
        table_has_vertical_merge = False
        for row_index, row in enumerate(rows, 1):
            cells = row.findall(wtag("tc"), namespaces=NS)
            row_cell_counts.append(len(cells))
            column_start = 1
            cell_contexts: dict[str, dict[str, int]] = {}
            for cell_index, cell in enumerate(cells, 1):
                span = int_value(cell.find(wtag("tcPr") + "/" + wtag("gridSpan"), namespaces=NS)) or 1
                if span > 1 or cell.find(wtag("tcPr") + "/" + wtag("hMerge"), namespaces=NS) is not None:
                    table_has_horizontal_merge = True
                if cell.find(wtag("tcPr") + "/" + wtag("vMerge"), namespaces=NS) is not None:
                    table_has_vertical_merge = True
                cell_contexts[tree.getpath(cell)] = {
                    "cell_index": cell_index,
                    "cell_count": len(cells),
                    "grid_column_start": column_start,
                    "grid_column_end": column_start + span - 1,
                    "grid_span": span,
                    "cnf_style": parse_cnf_style(
                        cell.find(wtag("tcPr") + "/" + wtag("cnfStyle"), namespaces=NS)
                    ),
                }
                column_start += span
            row_contexts[tree.getpath(row)] = {
                "row_index": row_index,
                "row_count": len(rows),
                "cnf_style": parse_cnf_style(
                    row.find(wtag("trPr") + "/" + wtag("cnfStyle"), namespaces=NS)
                ),
                "cells": cell_contexts,
            }
        uniform_rows = len(set(row_cell_counts)) == 1 and bool(row_cell_counts)
        column_count = grid_column_count or (row_cell_counts[0] if uniform_rows else 0)
        meets_min_dimensions = len(rows) >= 2 and column_count >= 2
        is_regular_table = (
            meets_min_dimensions
            and uniform_rows
            and not table_has_horizontal_merge
            and not table_has_vertical_merge
        )
        table_contexts[table_path] = {
            "table_index": table_index,
            "table_xpath": table_path,
            "style_id": attr_value(table.find(wtag("tblPr") + "/" + wtag("tblStyle"), namespaces=NS)),
            "grid_column_count": grid_column_count,
            "is_regular_table": is_regular_table,
            "meets_min_dimensions": meets_min_dimensions,
            "has_horizontal_merge": table_has_horizontal_merge,
            "has_vertical_merge": table_has_vertical_merge,
            "uniform_row_cell_count": uniform_rows,
            "rows": row_contexts,
        }
    for index, paragraph in enumerate(root.xpath(".//w:p", namespaces=NS), 1):
        ppr = paragraph.find(wtag("pPr"), namespaces=NS)
        style = attr_value(ppr.find(wtag("pStyle"), namespaces=NS)) if ppr is not None else None
        num_pr = ppr.find(wtag("numPr"), namespaces=NS) if ppr is not None else None
        num_id = int_value(num_pr.find(wtag("numId"), namespaces=NS)) if num_pr is not None else None
        num_level = int_value(num_pr.find(wtag("ilvl"), namespaces=NS)) if num_pr is not None else None
        runs: list[dict[str, Any]] = []
        for run_index, run in enumerate(paragraph.xpath(".//w:r", namespaces=NS), 1):
            run_text = "".join(run.xpath("./w:t/text()", namespaces=NS))
            toc_text_ranges: list[list[int]] = []
            text_offset = 0
            for text_node in run.findall(wtag("t"), namespaces=NS):
                text_end = text_offset + len(text_node.text or "")
                if text_node in toc_text_nodes and text_end > text_offset:
                    if toc_text_ranges and toc_text_ranges[-1][1] == text_offset:
                        toc_text_ranges[-1][1] = text_end
                    else:
                        toc_text_ranges.append([text_offset, text_end])
                text_offset = text_end
            owner_paragraphs = run.xpath("ancestor::w:p[1]", namespaces=NS)
            run_sdt_tags = run.xpath("ancestor::w:sdt[1]/w:sdtPr/w:tag/@w:val", namespaces=NS)
            run_record: dict[str, Any] = {
                "index": run_index,
                "text": run_text,
                "word_count_text": run_word_count_text(run),
                "word_count_visible": not bool(
                    run.xpath("ancestor::w:del | ancestor::w:moveFrom", namespaces=NS)
                ),
                "rPr": parse_rpr(run.find(wtag("rPr"), namespaces=NS)),
                "xpath": tree.getpath(run),
                "owner_paragraph_xpath": (
                    tree.getpath(owner_paragraphs[0]) if owner_paragraphs else None
                ),
                "sdt_tag": run_sdt_tags[0] if run_sdt_tags else None,
            }
            if toc_text_ranges:
                run_record["toc_text_ranges"] = toc_text_ranges
            runs.append(run_record)
        sdt_tags = paragraph.xpath("ancestor::w:sdt[1]/w:sdtPr/w:tag/@w:val", namespaces=NS)
        bookmarks = paragraph.xpath(".//w:bookmarkStart/@w:name", namespaces=NS)
        text = paragraph_text(paragraph)
        revision_text_state = paragraph_revision_text_state(paragraph)
        table_context: dict[str, Any] | None = None
        table_ancestors = paragraph.xpath("ancestor::w:tbl[1]", namespaces=NS)
        row_ancestors = paragraph.xpath("ancestor::w:tr[1]", namespaces=NS)
        cell_ancestors = paragraph.xpath("ancestor::w:tc[1]", namespaces=NS)
        if table_ancestors and row_ancestors and cell_ancestors:
            table_path = tree.getpath(table_ancestors[0])
            row_path = tree.getpath(row_ancestors[0])
            cell_path = tree.getpath(cell_ancestors[0])
            stored_table = table_contexts.get(table_path, {})
            stored_row = stored_table.get("rows", {}).get(row_path, {})
            stored_cell = stored_row.get("cells", {}).get(cell_path, {})
            table_context = {
                key: value for key, value in stored_table.items() if key != "rows"
            }
            table_context.update(
                {
                    key: value
                    for key, value in stored_row.items()
                    if key not in ("cells", "cnf_style")
                }
            )
            table_context.update(
                {
                    key: value for key, value in stored_cell.items() if key != "cnf_style"
                }
            )
            merged_cnf: dict[str, bool] = {}
            merged_cnf.update(stored_row.get("cnf_style") or {})
            merged_cnf.update(stored_cell.get("cnf_style") or {})
            if ppr is not None:
                merged_cnf.update(parse_cnf_style(ppr.find(wtag("cnfStyle"), namespaces=NS)))
            table_context["cnf_style"] = merged_cnf
        modeled_structure = {
            "breaks": [
                {
                    "type": item.get(wqn("type")) or "textWrapping",
                    "clear": item.get(wqn("clear")),
                }
                for item in paragraph.findall(".//w:br", namespaces=NS)
            ],
            "tab_count": len(paragraph.findall(".//w:tab", namespaces=NS)),
            "hyperlink_count": len(paragraph.findall(".//w:hyperlink", namespaces=NS)),
            "drawing_count": len(paragraph.findall(".//w:drawing", namespaces=NS)),
            "field_endpoints": [
                item.get(wqn("fldCharType"))
                for item in paragraph.findall(".//w:fldChar", namespaces=NS)
            ],
            "footnote_reference_count": len(paragraph.findall(".//w:footnoteReference", namespaces=NS)),
            "endnote_reference_count": len(paragraph.findall(".//w:endnoteReference", namespaces=NS)),
            "comment_reference_count": len(paragraph.findall(".//w:commentReference", namespaces=NS)),
        }
        records.append(
            {
                "part": part,
                "index": index,
                "location": "%s#p%d" % (part, index),
                "xpath": tree.getpath(paragraph),
                "para_id": paragraph.get(qn(W14, "paraId")),
                "text": text,
                "text_sha256": sha256_bytes(text.encode("utf-8")),
                "revision_text_state": revision_text_state,
                "paragraph_mark_inserted": (
                    paragraph.find(wtag("pPr") + "/" + wtag("rPr") + "/" + wtag("ins"), namespaces=NS)
                    is not None
                ),
                "revision_replacement": bool(paragraph.findall(".//w:delText", namespaces=NS)),
                "revision_moved": bool(
                    paragraph.xpath(
                        ".//w:moveFrom | .//w:moveTo | ancestor::w:moveFrom | ancestor::w:moveTo",
                        namespaces=NS,
                    )
                ),
                "style_id": style,
                "num_id": num_id,
                "num_level": num_level,
                "pPr": parse_ppr(ppr),
                "runs": runs,
                "modeled_structure": modeled_structure,
                "bookmarks": bookmarks,
                "sdt_tag": sdt_tags[0] if sdt_tags else None,
                "in_table": bool(paragraph.xpath("ancestor::w:tc", namespaces=NS)),
                "in_textbox": bool(paragraph.xpath("ancestor::w:txbxContent", namespaces=NS)),
                "table_context": table_context,
            }
        )
    return records


# ---------------------------------------------------------------------------
# 表格 / 分节 / 绘图提取
# ---------------------------------------------------------------------------
def extract_tables(part: str, root: etree._Element) -> list[dict[str, Any]]:
    """只保留当前检查消费的表格元数据（精简）。"""
    return [
        {
            "part": part,
            "location": "%s#table%d" % (part, index),
            "style_id": attr_value(table.find(wtag("tblPr") + "/" + wtag("tblStyle"), namespaces=NS)),
            "grid_width_tokens": [
                column.get(wqn("w")) for column in table.findall(
                    wtag("tblGrid") + "/" + wtag("gridCol"), NS
                )
            ],
        }
        for index, table in enumerate(root.xpath(".//w:tbl", namespaces=NS), 1)
    ]


def extract_sections_for_audit(
    document: etree._Element | None, part: str = "word/document.xml"
) -> list[dict[str, Any]]:
    if document is None:
        return []
    sections = extract_sections_record(document.find(wtag("body"), namespaces=NS), part)
    add_effective_story_references(sections)
    return sections


def extract_drawings(part: str, root: etree._Element) -> list[dict[str, Any]]:
    """绘图身份 + 非法尺寸 token（不强制转换）。"""
    records: list[dict[str, Any]] = []
    for kind, xpath in (("inline", ".//wp:inline"), ("anchor", ".//wp:anchor")):
        for index, drawing in enumerate(root.xpath(xpath, namespaces=NS), 1):
            extent = drawing.find("wp:extent", namespaces=NS)
            invalid_extent: dict[str, Any] = {}
            for axis in ("cx", "cy"):
                raw = extent.get(axis) if extent is not None else None
                token = _integer_token(raw)
                if raw is not None and (token is None or int(token) < 0):
                    invalid_extent[axis] = raw
            doc_pr = drawing.find("wp:docPr", namespaces=NS)
            raw_id = doc_pr.get("id") if doc_pr is not None else None
            token = _integer_token(raw_id)
            identifier = int(token) if token is not None else raw_id
            records.append(
                {
                    "part": part,
                    "location": "%s#%s%d" % (part, kind, index),
                    "doc_pr_id": identifier,
                    "doc_pr_name": doc_pr.get("name") if doc_pr is not None else None,
                    "invalid_extent": invalid_extent,
                }
            )
    return records


def _integer_token(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not re.fullmatch(r"[+-]?[0-9]+", text):
        return None
    try:
        return str(int(text))
    except ValueError:
        return None


def drawing_id_findings(drawings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """wp:docPr/@id 无符号 32 位整数且全局唯一；extent 非负整数。"""
    findings: list[dict[str, Any]] = []
    by_id: dict[Any, list[dict[str, Any]]] = {}
    for drawing in drawings:
        if drawing.get("invalid_extent"):
            findings.append(
                issue(
                    "error",
                    "E_DRAWING_EXTENT_INVALID",
                    str(drawing.get("location")),
                    "drawing extent must use non-negative integer coordinates",
                    actual=drawing["invalid_extent"],
                )
            )
        identifier = drawing.get("doc_pr_id")
        if not isinstance(identifier, int) or not 0 <= identifier <= (1 << 32) - 1:
            findings.append(
                issue(
                    "error",
                    "E_OOXML_DOCPR_ID_INVALID",
                    str(drawing.get("location")),
                    "wp:docPr/@id must be an unsigned 32-bit integer",
                    actual=identifier,
                )
            )
            continue
        by_id.setdefault(identifier, []).append(drawing)
    for identifier, group in by_id.items():
        if len(group) > 1:
            findings.append(
                issue(
                    "error",
                    "E_OOXML_DOCPR_ID_INVALID",
                    "; ".join(str(item.get("location")) for item in group),
                    "wp:docPr/@id must be unique across every Word story part",
                    expected=1,
                    actual=len(group),
                    evidence={"doc_pr_id": identifier},
                )
            )
    return findings


# ---------------------------------------------------------------------------
# 结构 hash 与 OOXML 属性顺序
# ---------------------------------------------------------------------------
def structural_hash(
    element: etree._Element, clear_text: bool = False, clear_format: bool = False
) -> str:
    clone = etree.fromstring(etree.tostring(element))
    if clear_text:
        for text_node in clone.xpath(".//w:t", namespaces=NS):
            text_node.text = ""
    if clear_format:
        for properties in clone.xpath(".//w:pPr | .//w:rPr", namespaces=NS):
            parent = properties.getparent()
            if parent is not None:
                parent.remove(properties)
    for node in clone.iter():
        for name in list(node.attrib):
            local = etree.QName(name).localname
            namespace = etree.QName(name).namespace
            if (namespace == W and local.startswith("rsid")) or (
                namespace == W14 and local in {"paraId", "textId"}
            ):
                del node.attrib[name]
            elif namespace == R:
                node.attrib[name] = "RELATIONSHIP_%s" % local
    for proof_error in clone.xpath(".//w:proofErr", namespaces=NS):
        parent = proof_error.getparent()
        if parent is not None:
            parent.remove(proof_error)
    for rsids in clone.xpath(".//w:rsids", namespaces=NS):
        parent = rsids.getparent()
        if parent is not None:
            parent.remove(rsids)
    return canonical_xml_hash(clone)


OOXML_PROPERTY_ORDER: dict[str, tuple[str, tuple[str, ...]]] = {
    "tblPr": (
        "E_OOXML_TBLPR_ORDER",
        (
            "tblStyle", "tblpPr", "tblOverlap", "bidiVisual", "tblStyleRowBandSize",
            "tblStyleColBandSize", "tblW", "jc", "tblCellSpacing", "tblInd",
            "tblBorders", "shd", "tblLayout", "tblCellMar", "tblLook", "tblCaption",
            "tblDescription", "tblPrChange",
        ),
    ),
    "tcPr": (
        "E_OOXML_TCPR_ORDER",
        (
            "cnfStyle", "tcW", "gridSpan", "hMerge", "vMerge", "tcBorders", "shd",
            "noWrap", "tcMar", "textDirection", "tcFitText", "vAlign", "hideMark",
            "headers", "cellIns", "cellDel", "cellMerge", "tcPrChange",
        ),
    ),
}
OOXML_PROPERTY_ORDER_REPAIR_HINT = (
    "按 OOXML 模式顺序重建属性容器（不要盲目追加）；用 schema 感知 API 或把每个节点插到 "
    "第一个应在它之后的兄弟前，重新生成 DOCX 后完整重审。"
)


def ooxml_property_order_findings(
    part: str, root: etree._Element
) -> list[dict[str, Any]]:
    """表属性容器 w:tblPr / w:tcPr 的模式顺序反转检查。

    只比较已识别的 WordprocessingML 子元素；扩展命名空间与未知 w: 子元素不参与，
    避免对未建模的 schema 位置作无依据的断言。w:trPr 是有界 xsd:choice，无强制顺序，
    故不检查。
    """
    findings: list[dict[str, Any]] = []
    tree = root.getroottree()
    table_indexes: dict[str, int] = {}
    row_indexes: dict[str, int] = {}
    cell_indexes: dict[str, int] = {}
    for table_index, table in enumerate(root.xpath(".//w:tbl", namespaces=NS), 1):
        table_path = tree.getpath(table)
        table_indexes[table_path] = table_index
        rows = []
        for row in table.xpath(".//w:tr", namespaces=NS):
            ancestors = row.xpath("ancestor::w:tbl[1]", namespaces=NS)
            if ancestors and tree.getpath(ancestors[0]) == table_path:
                rows.append(row)
        for row_index, row in enumerate(rows, 1):
            row_path = tree.getpath(row)
            row_indexes[row_path] = row_index
            cells = []
            for cell in row.xpath(".//w:tc", namespaces=NS):
                ancestors = cell.xpath("ancestor::w:tr[1]", namespaces=NS)
                if ancestors and tree.getpath(ancestors[0]) == row_path:
                    cells.append(cell)
            for cell_index, cell in enumerate(cells, 1):
                cell_indexes[tree.getpath(cell)] = cell_index
    containers = root.xpath(".//w:tblPr | .//w:tcPr", namespaces=NS)
    for container in containers:
        container_name = etree.QName(container).localname
        code, allowed_order = OOXML_PROPERTY_ORDER[container_name]
        rank = {name: index for index, name in enumerate(allowed_order)}
        actual_local: list[str] = []
        for child in container:
            if not isinstance(child.tag, str):
                continue
            child_name = etree.QName(child)
            if child_name.namespace == W and child_name.localname in rank:
                actual_local.append(child_name.localname)
        inversion: tuple[int, int] | None = None
        for later_index in range(1, len(actual_local)):
            later_rank = rank[actual_local[later_index]]
            for earlier_index in range(later_index - 1, -1, -1):
                if rank[actual_local[earlier_index]] > later_rank:
                    inversion = (earlier_index, later_index)
                    break
            if inversion is not None:
                break
        if inversion is None:
            continue
        expected_local = sorted(actual_local, key=rank.__getitem__)
        actual = ["w:%s" % name for name in actual_local]
        expected = ["w:%s" % name for name in expected_local]
        earlier_index, later_index = inversion
        container_path = tree.getpath(container)
        evidence: dict[str, Any] = {
            "part": part,
            "xpath": container_path,
            "container": "w:%s" % container_name,
            "actual": actual,
            "expected": expected,
            "first_inversion": {
                "observed_earlier": "w:%s" % actual_local[earlier_index],
                "out_of_order_node": "w:%s" % actual_local[later_index],
                "observed_positions": [earlier_index + 1, later_index + 1],
                "required_order": [
                    "w:%s" % actual_local[later_index],
                    "w:%s" % actual_local[earlier_index],
                ],
            },
        }
        table_ancestors = container.xpath("ancestor::w:tbl[1]", namespaces=NS)
        row_ancestors = container.xpath("ancestor::w:tr[1]", namespaces=NS)
        cell_ancestors = container.xpath("ancestor::w:tc[1]", namespaces=NS)
        location_parts: list[str] = []
        if table_ancestors:
            table_index = table_indexes.get(tree.getpath(table_ancestors[0]))
            if table_index is not None:
                evidence["table_index"] = table_index
                location_parts.append("table%d" % table_index)
        if row_ancestors:
            row_index = row_indexes.get(tree.getpath(row_ancestors[0]))
            if row_index is not None:
                evidence["row_index"] = row_index
                location_parts.append("row%d" % row_index)
        if cell_ancestors:
            cell_index = cell_indexes.get(tree.getpath(cell_ancestors[0]))
            if cell_index is not None:
                evidence["cell_index"] = cell_index
                location_parts.append("cell%d" % cell_index)
        if location_parts:
            location = "%s#%s/%s" % (part, "/".join(location_parts), container_name)
        else:
            location = "%s:%s" % (part, container_path)
        findings.append(
            issue(
                "error",
                code,
                location,
                "w:%s children are out of OOXML schema order" % container_name,
                expected=expected,
                actual=actual,
                repair_hint=OOXML_PROPERTY_ORDER_REPAIR_HINT,
                evidence=evidence,
                blocking=True,
            )
        )
    return findings
