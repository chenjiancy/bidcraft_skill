# -*- coding: utf-8 -*-
"""docx_tools.reader_cli：docx-read 子命令：维度 0-7 结构化文本输出 + CLI。

能力逻辑借鉴豆包 word 技能 read.py（平台无关重写，非整文件复制）。
输出约定：dim 0 Markdown；dim 1-7 块式结构化文本；--json 输出机读记录。
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

from lxml import etree
from zipfile import ZipFile

from .common import (
    NS,
    parse_xml,
    resolve_alternate_content,
    wtag,
)
from .reader import story_paragraphs_runs, story_tables
from .reader_sections_styles import (
    add_effective_story_references,
    extract_sections_record,
    extract_styles_record,
)
from .reader_stories import (
    build_headers_footers,
    build_objects,
    content_type_map,
)


def _story_parts_roots(zf: ZipFile) -> dict[str, etree._Element]:
    roots: dict[str, etree._Element] = {}
    for item in zf.infolist():
        name = item.filename
        if not name.startswith("word/") or not name.endswith(".xml"):
            continue
        if name in ("word/document.xml",) or (
            name.startswith("word/header") or name.startswith("word/footer")
        ):
            roots[name] = resolve_alternate_content(parse_xml(zf.read(name), name))
    return roots


def build_data(docx_path: Path, source) -> dict[str, Any]:
    """docx → 记录字典（段落/run/表格/分节/样式/对象/页眉页脚）。"""
    with ZipFile(docx_path) as zf:
        roots = _story_parts_roots(zf)
        document = roots.get("word/document.xml")
        paragraphs: list[dict[str, Any]] = []
        runs: list[dict[str, Any]] = []
        tables: list[dict[str, Any]] = []
        if document is not None:
            body = document.find(wtag("body"), namespaces=NS)
            if body is not None:
                paragraphs, runs = story_paragraphs_runs(document, str(source), 0)
                tables = story_tables(document, str(source), 0)
        sections = (
            extract_sections_record(document.find(wtag("body"), namespaces=NS), str(source))
            if document is not None
            else []
        )
        add_effective_story_references(sections)
        _attach_section_story_text(sections, zf, roots)
        styles_root = None
        try:
            styles_root = parse_xml(zf.read("word/styles.xml"), "word/styles.xml")
        except (KeyError, ValueError):
            styles_root = None
        styles = extract_styles_record(styles_root)
        content_types = content_type_map(zf)
        objects = build_objects(zf, content_types)
        headers_footers = build_headers_footers(roots)
    return {
        "source": str(source),
        "paragraphs": paragraphs,
        "runs": runs,
        "tables": tables,
        "sections": sections,
        "styles": styles,
        "objects": objects,
        "headers_footers": headers_footers,
    }


def build_sections_data(docx_path: Path, source) -> dict[str, Any]:
    """仅分节数据（dim 1）。"""
    with ZipFile(docx_path) as zf:
        roots = _story_parts_roots(zf)
        document = roots.get("word/document.xml")
        sections = (
            extract_sections_record(document.find(wtag("body"), namespaces=NS), str(source))
            if document is not None
            else []
        )
        add_effective_story_references(sections)
        _attach_section_story_text(sections, zf, roots)
    return {"source": str(source), "sections": sections}


def _attach_section_story_text(sections, zf, roots) -> None:
    """按 header/footer 引用把对应部件文本挂到分节记录（供 dim 1 展示）。"""
    rels: dict[str, str] = {}
    try:
        rels_root = parse_xml(zf.read("word/_rels/document.xml.rels"), "rels")
        for rel in rels_root:
            rels[rel.get("Id")] = rel.get("Target", "")
    except (KeyError, ValueError):
        pass
    for section in sections:
        for family in ("header", "footer"):
            texts: list[str] = []
            for reference in section.get("%s_references" % family, []):
                target = rels.get(str(reference.get("rId")))
                if not target:
                    continue
                part = "word/" + target.lstrip("/")
                root = roots.get(part)
                if root is not None:
                    texts.append("".join(root.xpath(".//w:t/text()", namespaces=NS)))
            if texts:
                section["%s_text" % family] = texts


# ---------------------------------------------------------------------------
# 输出格式
# ---------------------------------------------------------------------------
def block_header(title: str, values: list[tuple[str, Any]]) -> str:
    from .common import inline_value

    lines = ["[%s]" % title]
    for key, value in values:
        if value is None or value == "" or value == [] or value == {}:
            continue
        lines.append("  %s: %s" % (key, inline_value(value)))
    return "\n".join(lines)


def markdown_heading_level(paragraph: dict[str, Any]) -> int | None:
    style_id = str(paragraph.get("style_id") or "")
    lowered = style_id.lower()
    for level in range(1, 7):
        if lowered in ("heading %d" % level, "标题 %d" % level, "heading%d" % level):
            return level
    outline = paragraph.get("outline_level")
    if isinstance(outline, int) and 0 <= outline <= 8:
        return outline + 1
    return None


def _markdown_table(table: dict[str, Any]) -> str:
    rows = table.get("rows", [])
    if not rows:
        return ""
    grid = table.get("grid") or []
    lines = []
    first = rows[0]
    for row in rows:
        cells = row.get("cells", [])
        line = "|" + "|".join(
            (cell.get("text") or "").replace("\n", " ").replace("|", "\\|")
            for cell in cells
        ) + "|"
        lines.append(line)
        if row is first:
            lines.append("|" + "|".join(["---"] * len(cells)) + "|")
    return "\n".join(lines)


def markdown_output(data: dict[str, Any]) -> str:
    """维度 0：正文 Markdown（标题层级 + 表格）。"""
    ordered: list[dict[str, Any]] = []
    for item in data.get("paragraphs", []):
        ordered.append(item)
    for item in data.get("tables", []):
        ordered.append(item)
    return "\n\n".join(_markdown_block(item) for item in ordered) + "\n"


def _markdown_block(item: dict[str, Any]) -> str:
    from .common import paragraph_text

    if item.get("record_type") == "table":
        return _markdown_table(item)
    level = markdown_heading_level(item)
    text = item.get("text") or ""
    if level is not None:
        return "%s %s" % ("#" * level, text.strip())
    if item.get("text_box"):
        return "> %s" % text
    return text


def context_records(data: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"record_type": "context", "source": data["source"]}]


def records_for_dimension(data: dict[str, Any], dimension: int) -> list[dict[str, Any]]:
    context = context_records(data)
    if dimension == 1:
        return context + data["sections"]
    if dimension == 2:
        return context + data["paragraphs"]
    if dimension == 3:
        return context + data["runs"]
    if dimension == 4:
        return context + data["styles"]["styles"]
    if dimension == 5:
        return context + data["tables"]
    if dimension == 6:
        anchors = [
            item for item in data["runs"] if item.get("drawings")
        ]
        return context + data["objects"] + anchors
    if dimension == 7:
        return context + data["headers_footers"]
    return context


def sections_text_output(records: list[dict[str, Any]]) -> str:
    manifest = records[0]
    sections = [
        item for item in records if item.get("record_type") == "section"
    ]
    lines = [
        "# Dimension 1: sections",
        "source: %s" % manifest["source"],
        "syntax: [SECTION<n>] blocks cover every w:sectPr (body final and nested).",
        "omitted: record_type; raw section XML.",
        "normalized: border and margin XML use compact prefix:tag(attribute,child) notation.",
        "",
    ]
    if not sections:
        lines.append("records: none")
    for section in sections:
        lines.append(
            block_header(
                "SECTION%d" % section["section_index"],
                [
                    ("loc", section.get("location")),
                    ("page", section.get("page")),
                    ("start_type", section.get("start_type")),
                    ("different_first_page", section.get("different_first_page")),
                    ("columns", section.get("columns")),
                    ("page_numbering", section.get("page_numbering")),
                    ("vertical_alignment", section.get("vertical_alignment")),
                    ("text_direction", section.get("text_direction")),
                    ("document_grid", section.get("document_grid")),
                    ("line_numbering", section.get("line_numbering")),
                    ("page_borders", section.get("page_borders")),
                    ("header_references", section.get("header_references")),
                    ("footer_references", section.get("footer_references")),
                ],
            )
        )
        if section.get("header_text"):
            lines.append("header_text=%s" % section["header_text"])
        if section.get("footer_text"):
            lines.append("footer_text=%s" % section["footer_text"])
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def paragraphs_text_output(records: list[dict[str, Any]]) -> str:
    manifest = records[0]
    paragraphs = [
        item for item in records if item.get("record_type") == "paragraph"
    ]
    lines = [
        "# Dimension 2: paragraphs",
        "source: %s" % manifest["source"],
        "syntax: [P<n>] blocks cover every paragraph in document order (tables and textboxes included).",
        "omitted: record_type; run formatting and raw paragraph XML, which belong to dimension 3.",
        "normalized: border and shading XML use compact prefix:tag(attribute,child) notation.",
        "",
    ]
    if not paragraphs:
        lines.append("records: none")
    for paragraph in paragraphs:
        special = [
            {key: node[key] for key in ("tag", "relationship", "count", "types") if node.get(key) is not None}
            for node in paragraph.get("special_nodes", [])
        ]
        lines.append(
            block_header(
                "P%d" % paragraph["paragraph_index"],
                [
                    ("loc", paragraph.get("location")),
                    ("table", paragraph.get("table_index")),
                    ("row", paragraph.get("row_index")),
                    ("cell", paragraph.get("cell_index")),
                    ("style", paragraph.get("style_id")),
                    ("align", paragraph.get("alignment")),
                    ("indent", paragraph.get("indent")),
                    ("spacing", paragraph.get("spacing")),
                    ("keep_next", paragraph.get("keep_with_next")),
                    ("keep_lines", paragraph.get("keep_lines")),
                    ("page_break", paragraph.get("page_break_before")),
                    ("widow", paragraph.get("widow_control")),
                    ("borders", paragraph.get("borders")),
                    ("shading", paragraph.get("shading")),
                    ("tabs", paragraph.get("tabs")),
                    ("numbering", paragraph.get("numbering")),
                    ("text_box", paragraph.get("text_box")),
                    ("special", special),
                ],
            )
        )
        lines.append(paragraph.get("text") or "<empty/>")
    return "\n".join(lines).rstrip() + "\n"


def runs_text_output(records: list[dict[str, Any]]) -> str:
    manifest = records[0]
    runs = [item for item in records if item.get("record_type") == "run"]
    lines = [
        "# Dimension 3: runs",
        "source: %s" % manifest["source"],
        "syntax: [R<n>] blocks cover every run in document order; [DRAWING<n>] inside a run block is a drawing anchor.",
        "omitted: record_type; raw Run XML.",
        "normalized: drawing OOXML uses compact prefix:tag(attribute,child) notation.",
        "",
    ]
    if not runs:
        lines.append("records: none")
    for run in runs:
        lines.append(
            block_header(
                "R%d" % run["run_index"],
                [
                    ("loc", run.get("location")),
                    ("table", run.get("table_index")),
                    ("row", run.get("row_index")),
                    ("cell", run.get("cell_index")),
                    ("style", run.get("style_id")),
                    ("bold", run.get("bold")),
                    ("italic", run.get("italic")),
                    ("underline", run.get("underline")),
                    ("strike", run.get("strike")),
                    ("double_strike", run.get("double_strike")),
                    ("caps", run.get("caps")),
                    ("small_caps", run.get("small_caps")),
                    ("color", run.get("color")),
                    ("highlight", run.get("highlight")),
                    ("size", run.get("size_half_points")),
                    ("vertical_align", run.get("vertical_align")),
                    ("fonts", run.get("fonts")),
                    ("lang", run.get("lang")),
                    ("hyperlink", run.get("hyperlink")),
                    ("field_codes", run.get("field_codes")),
                ],
            )
        )
        for drawing_index, drawing in enumerate(run.get("drawings", []), 1):
            lines.append(
                block_header("DRAWING%d" % drawing_index, list(drawing.items()))
            )
        lines.append(run.get("text") or "<empty/>")
    return "\n".join(lines).rstrip() + "\n"


def styles_text_output(records: list[dict[str, Any]]) -> str:
    manifest = records[0]
    styles = [item for item in records if item.get("record_type") != "context"]
    lines = [
        "# Dimension 4: styles",
        "source: %s" % manifest["source"],
        "syntax: [STYLE<n>] blocks cover styles.xml definitions; docDefaults shown first.",
        "omitted: record_type; raw styles XML.",
        "normalized: properties use compact prefix:tag(attribute,child) notation.",
        "",
    ]
    for style_index, style in enumerate(styles, 1):
        lines.append(
            block_header(
                "STYLE%d" % style_index,
                [
                    ("id", style.get("style_id")),
                    ("type", style.get("type")),
                    ("name", style.get("name")),
                    ("based_on", style.get("based_on")),
                    ("next", style.get("next")),
                    ("default", style.get("default")),
                    ("hidden", style.get("hidden")),
                    ("ui_priority", style.get("ui_priority")),
                    ("link", style.get("link")),
                    ("aliases", style.get("aliases")),
                    ("rPr", style.get("rPr")),
                    ("pPr", style.get("pPr")),
                    ("tblPr", style.get("tblPr")),
                    ("conditional_table_properties", style.get("conditional_table_properties")),
                ],
            )
        )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def tables_text_output(records: list[dict[str, Any]]) -> str:
    manifest = records[0]
    tables = [item for item in records if item.get("record_type") == "table"]
    lines = [
        "# Dimension 5: tables",
        "source: %s" % manifest["source"],
        "syntax: [T<n>] starts a table; [R<n>] a row; [C<n>] a cell; nested tables carry parent/level.",
        "omitted: record_type; raw table XML.",
        "normalized: border and shading XML use compact prefix:tag(attribute,child) notation.",
        "",
    ]
    if not tables:
        lines.append("records: none")
    for table in tables:
        lines.append(
            block_header(
                "T%d" % table["table_index"],
                [
                    ("parent", table.get("parent_table_index")),
                    ("level", table.get("nesting_level")),
                    ("loc", table.get("location")),
                    ("style", table.get("table_style")),
                    ("width", table.get("width")),
                    ("width_type", table.get("width_type")),
                    ("alignment", table.get("alignment")),
                    ("borders", table.get("borders")),
                    ("shading", table.get("shading")),
                    ("cell_margin", table.get("cell_margins")),
                    ("grid", table.get("grid")),
                ],
            )
        )
        for row in table.get("rows", []):
            lines.append(
                block_header(
                    "R%d" % row["row_index"],
                    [
                        ("height", row.get("height")),
                        ("height_rule", row.get("height_rule")),
                        ("header", row.get("repeat_header")),
                        ("cant_split", row.get("cant_split")),
                        ("grid_before", row.get("grid_before")),
                        ("grid_after", row.get("grid_after")),
                    ],
                )
            )
            for cell in row.get("cells", []):
                properties = cell.get("properties", {})
                lines.append(
                    block_header(
                        "C%d" % cell["cell_index"],
                        [
                            ("width", properties.get("width")),
                            ("colspan", properties.get("grid_span")),
                            ("hmerge", properties.get("horizontal_merge")),
                            ("vmerge", properties.get("vertical_merge")),
                            ("borders", properties.get("borders")),
                            ("shading", properties.get("shading")),
                            ("cell_margin", properties.get("cell_margins")),
                            ("valign", properties.get("vertical_align")),
                            ("paragraphs", cell.get("paragraph_count")),
                        ],
                    )
                )
                lines.append(cell.get("text") or "<empty/>")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def objects_text_output(records: list[dict[str, Any]]) -> str:
    manifest = records[0]
    objects = [item for item in records if item.get("record_type") == "object"]
    anchors = [item for item in records if item.get("record_type") == "run"]
    lines = [
        "# Dimension 6: media and embedded objects",
        "source: %s" % manifest["source"],
        "syntax: [OBJECT<n>] identifies a package object, [REL<n>] a reference, and [ANCHOR<n>] its source Run.",
        "omitted: record_type; Run formatting and raw Run XML, which belong to dimension 4.",
        "normalized: drawing OOXML uses compact prefix:tag(attribute,child) notation.",
        "",
    ]
    if not objects and not anchors:
        lines.append("records: none")
    for index, item in enumerate(objects, 1):
        lines.append(
            block_header(
                "OBJECT%d" % index,
                [
                    ("part", item.get("part")),
                    ("kind", item.get("kind")),
                    ("type", item.get("content_type")),
                    ("size", item.get("size")),
                    ("sha256", item.get("sha256")),
                ],
            )
        )
        for relation_index, relationship in enumerate(item.get("relationships", []), 1):
            lines.append(
                block_header(
                    "REL%d" % relation_index,
                    [
                        ("source", relationship.get("source_part")),
                        ("id", relationship.get("relationship_id")),
                        ("type", relationship.get("type")),
                        ("mode", relationship.get("target_mode")),
                    ],
                )
            )
        lines.append("")
    for index, run in enumerate(anchors, 1):
        lines.append(
            block_header(
                "ANCHOR%d" % index,
                [
                    ("part", run.get("source_path")),
                    ("paragraph", run.get("paragraph_index")),
                    ("run", run.get("run_index")),
                    ("table", run.get("table_index")),
                    ("row", run.get("row_index")),
                    ("cell", run.get("cell_index")),
                    ("loc", run.get("location")),
                ],
            )
        )
        for drawing_index, drawing in enumerate(run.get("drawings", []), 1):
            lines.append(
                block_header("DRAWING%d" % drawing_index, list(drawing.items()))
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def headers_footers_text_output(records: list[dict[str, Any]]) -> str:
    manifest = records[0]
    stories = [
        item for item in records
        if item.get("record_type") in {"header", "footer"}
    ]
    lines = [
        "# Dimension 7: headers and footers",
        "source: %s" % manifest["source"],
        "syntax: [HEADER<n>] or [FOOTER<n>] starts a story; nested [P], [T], [R], [C], and [DRAWING] blocks retain source indexes.",
        "omitted: record_type; raw story, paragraph, table, and drawing XML.",
        "normalized: border and margin XML use compact prefix:tag(attribute,child) notation.",
        "",
    ]
    if not stories:
        lines.append("records: none")
    for story_index, story in enumerate(stories, 1):
        lines.append(
            block_header(
                "%s%d" % (story["record_type"].upper(), story_index),
                [
                    ("part", story.get("part")),
                    ("paragraphs", len(story.get("paragraphs", []))),
                    ("tables", len(story.get("tables", []))),
                    ("drawings", len(story.get("drawings", []))),
                ],
            )
        )
        if story.get("text"):
            lines.append(story["text"])
        if story.get("fields"):
            lines.append("fields=%s" % story["fields"])
        for paragraph in story.get("paragraphs", []):
            lines.append(
                block_header(
                    "P%d" % paragraph["paragraph_index"],
                    [
                        ("loc", paragraph.get("location")),
                        ("style", paragraph.get("style_id")),
                        ("align", paragraph.get("alignment")),
                        ("indent", paragraph.get("indent")),
                        ("spacing", paragraph.get("spacing")),
                    ],
                )
            )
            lines.append(paragraph.get("text") or "<empty/>")
        for table in story.get("tables", []):
            lines.append(
                block_header(
                    "T%d" % table["table_index"],
                    [
                        ("loc", table.get("location")),
                        ("style", table.get("table_style")),
                        ("grid", table.get("grid")),
                    ],
                )
            )
            for row in table.get("rows", []):
                lines.append(
                    block_header("R%d" % row["row_index"], [])
                )
                for cell in row.get("cells", []):
                    properties = cell.get("properties", {})
                    lines.append(
                        block_header(
                            "C%d" % cell["cell_index"],
                            [
                                ("colspan", properties.get("grid_span")),
                                ("hmerge", properties.get("horizontal_merge")),
                                ("vmerge", properties.get("vertical_merge")),
                                ("paragraphs", cell.get("paragraph_count")),
                            ],
                        )
                    )
                    lines.append(cell.get("text") or "<empty/>")
        for drawing_index, drawing in enumerate(story.get("drawings", []), 1):
            lines.append(
                block_header("DRAWING%d" % drawing_index, list(drawing.items()))
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


FORMATTERS = {
    1: sections_text_output,
    2: paragraphs_text_output,
    3: runs_text_output,
    4: styles_text_output,
    5: tables_text_output,
    6: objects_text_output,
    7: headers_footers_text_output,
}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _resolve_docx(source: Path, tmpdir: Path) -> Path:
    """.doc → 临时 .docx（Windows Word COM）；无 Word 环境报错不降级。"""
    if source.suffix.lower() != ".doc":
        return source
    from .. import com_util

    if not getattr(com_util, "HAVE_COM", False):
        raise RuntimeError(
            "当前环境无 Windows Word COM，无法把 .doc 转换为 .docx；请改用 .docx 输入"
        )
    docx_path = tmpdir / (source.stem + ".docx")
    with com_util.WordCOM(visible=False) as word:
        word.convert_to_docx(str(source), str(docx_path))
    return docx_path


def register_parser(subparsers) -> None:
    parser = subparsers.add_parser(
        "docx-read",
        help="docx 结构深读：维度 0-7（正文/分节/段落/run/样式/表格/对象/页眉页脚）",
    )
    parser.add_argument("--file", required=True, help="docx 文件路径（.doc 经 Word COM 转换）")
    parser.add_argument(
        "--dim", type=int, required=True, choices=range(8),
        help="维度 0-7（0=Markdown 正文，1=分节，2=段落，3=run，4=样式，5=表格，6=对象，7=页眉页脚）",
    )
    parser.add_argument("--out", help="可选：把输出写入该文件（UTF-8；--json 时为 JSON）")
    parser.set_defaults(func=_run_docx_read)


def _run_docx_read(args) -> int:
    source = Path(args.file)
    if not source.is_file():
        print("[INPUT ERROR] file does not exist: %s" % source)
        return 2
    if source.suffix.lower() not in {".doc", ".docx"}:
        print("[INPUT ERROR] filename must be a .doc or .docx file: %s" % source)
        return 2
    json_mode = bool(getattr(args, "json", False))
    try:
        with tempfile.TemporaryDirectory() as tmp_name:
            docx_path = _resolve_docx(source, Path(tmp_name))
            data = (
                build_sections_data(docx_path, source)
                if args.dim == 1
                else build_data(docx_path, source)
            )
            if json_mode:
                output = json.dumps(
                    _json_payload(data, args.dim),
                    ensure_ascii=False, indent=2, sort_keys=True,
                )
            elif args.dim == 0:
                output = markdown_output(data)
            else:
                records = records_for_dimension(data, args.dim)
                output = FORMATTERS[args.dim](records)
    except Exception as exc:
        print("[INPUT ERROR] %s" % exc)
        return 2
    if args.out:
        out_path = Path(args.out).expanduser()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output, encoding="utf-8")
    _stdout(output)
    return 0


def _json_payload(data: dict[str, Any], dim: int) -> dict[str, Any]:
    """按维度裁剪机读记录。"""
    payload: dict[str, Any] = {"dimension": dim}
    if dim == 1:
        payload["sections"] = data["sections"]
    elif dim == 0:
        payload["paragraphs"] = data["paragraphs"]
        payload["tables"] = data["tables"]
    elif dim == 2:
        payload["paragraphs"] = data["paragraphs"]
    elif dim == 3:
        payload["runs"] = data["runs"]
    elif dim == 4:
        payload["styles"] = data["styles"]
    elif dim == 5:
        payload["tables"] = data["tables"]
    elif dim == 6:
        payload["objects"] = data["objects"]
        payload["anchors"] = [
            item for item in data["runs"] if item.get("drawings")
        ]
    elif dim == 7:
        payload["headers_footers"] = data["headers_footers"]
    return payload


def _stdout(text: str) -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    print(text)
