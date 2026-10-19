# -*- coding: utf-8 -*-
"""docx_tools.reader_stories：页眉页脚（dim 7）与媒体对象（dim 6）提取。

能力逻辑借鉴豆包 word 技能 read.py（平台无关重写，非整文件复制）。
"""
from __future__ import annotations

import posixpath
from typing import Any

from lxml import etree
from zipfile import ZipFile

from .common import (
    NS,
    R,
    W,
    qn,
    sha256_bytes,
    wqn,
    wtag,
)
from .reader import drawing_records, paragraph_record, table_record, run_record


# ---------------------------------------------------------------------------
# 页眉页脚故事部件
# ---------------------------------------------------------------------------
def story_records(root, part: str, story_type: str) -> dict[str, Any]:
    """单个 header/footer 部件的段落/表格/绘图记录。"""
    paragraphs: list[dict[str, Any]] = []
    tables: list[dict[str, Any]] = []
    drawings: list[dict[str, Any]] = []
    runs: list[dict[str, Any]] = []
    paragraph_index = 0
    for paragraph in root.xpath(".//w:p", namespaces=NS):
        paragraph_index += 1
        paragraphs.append(
            paragraph_record(paragraph, part, 0, paragraph_index)
        )
        for run_index, run in enumerate(
            paragraph.xpath(".//w:r", namespaces=NS), 1
        ):
            runs.append(
                run_record(
                    run, part, paragraph_index, run_index, 0
                )
            )
            for drawing in drawing_records(run):
                drawings.append(drawing)
    for table_index, table in enumerate(root.xpath(".//w:tbl", namespaces=NS), 1):
        tables.append(table_record(table, part, 0, table_index))
    fields = [
        fld_type
        for fld in root.xpath(".//w:fldChar", namespaces=NS)
        for fld_type in [fld.get(wqn("fldCharType"))]
        if fld_type
    ]
    record: dict[str, Any] = {
        "record_type": story_type,
        "part": part,
        "paragraphs": paragraphs,
        "tables": tables,
        "runs": runs,
        "drawings": drawings,
        "text": "".join(root.xpath(".//w:t/text()", namespaces=NS)),
    }
    if fields:
        record["fields"] = fields
    return record


def build_headers_footers(roots: dict[str, etree._Element]) -> list[dict[str, Any]]:
    """遍历 word/headerN.xml 与 word/footerN.xml 部件。"""
    records: list[dict[str, Any]] = []
    for part in sorted(roots):
        if not part.startswith("word/header") and not part.startswith("word/footer"):
            continue
        if not part.endswith(".xml"):
            continue
        story_type = "header" if part.startswith("word/header") else "footer"
        records.append(story_records(roots[part], part, story_type))
    return records


# ---------------------------------------------------------------------------
# 媒体与嵌入对象（dim 6）
# ---------------------------------------------------------------------------
def content_type_map(zf: ZipFile) -> dict[str, str]:
    """[Content_Types].xml → {part_name: content_type}（Override 优先，Default 兜底）。"""
    mapping: dict[str, str] = {}
    default_by_ext: dict[str, str] = {}
    try:
        root = etree.fromstring(zf.read("[Content_Types].xml"))
    except Exception:
        return mapping
    for default in root.findall("{http://schemas.openxmlformats.org/package/2006/content-types}Default"):
        ext = default.get("Extension")
        if ext:
            default_by_ext["." + ext.lower()] = default.get("ContentType", "")
    for override in root.findall("{http://schemas.openxmlformats.org/package/2006/content-types}Override"):
        part = override.get("PartName", "")
        if part.startswith("/"):
            part = part[1:]
        mapping[part] = override.get("ContentType", "")
    for part, content_type in mapping.items():
        if not content_type:
            mapping[part] = ""
    for ext, content_type in default_by_ext.items():
        if content_type:
            mapping.setdefault(ext, content_type)
    return mapping


def _object_kind(part: str) -> str:
    if part.startswith("word/media/"):
        return "media"
    if part.startswith("word/embeddings/"):
        return "embedded"
    if part.startswith("word/charts/"):
        return "chart"
    if part.startswith("word/diagrams/"):
        return "diagram"
    if part.startswith("word/activeX/"):
        return "activex"
    return "other"


def _relationships_for(zf: ZipFile, source_part: str) -> list[dict[str, Any]]:
    """读取部件对应 *.rels（word/_rels/document.xml.rels 等）。"""
    rels_name = "word/_rels/%s.rels" % posixpath.basename(source_part)
    try:
        data = zf.read(rels_name)
    except KeyError:
        return []
    relationships: list[dict[str, Any]] = []
    try:
        root = etree.fromstring(data)
    except Exception:
        return relationships
    for rel in root.findall("{http://schemas.openxmlformats.org/package/2006/relationships}Relationship"):
        relationships.append(
            {
                "source_part": source_part,
                "relationship_id": rel.get("Id"),
                "type": rel.get("Type", "").split("/")[-1],
                "target_mode": rel.get("TargetMode"),
                "target": rel.get("Target"),
            }
        )
    return relationships


def build_objects(
    zf: ZipFile, content_types: dict[str, str]
) -> list[dict[str, Any]]:
    """包内媒体/嵌入对象清单（part/kind/content_type/size/sha256/关系）。"""
    records: list[dict[str, Any]] = []
    object_roots = ("word/media/", "word/embeddings/", "word/charts/", "word/diagrams/", "word/activeX/")
    names = [
        item.filename for item in zf.infolist() if not item.is_dir()
    ]
    for name in sorted(names):
        if not name.startswith(object_roots):
            continue
        data = zf.read(name)
        content_type = content_types.get(name) or ""
        records.append(
            {
                "record_type": "object",
                "part": name,
                "kind": _object_kind(name),
                "content_type": content_type,
                "size": len(data),
                "sha256": sha256_bytes(data),
                "relationships": _relationships_for(zf, name),
            }
        )
    return records
