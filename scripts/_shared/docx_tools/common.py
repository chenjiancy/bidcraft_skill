# -*- coding: utf-8 -*-
"""docx_tools 公共设施：命名空间、XML 解析、哈希、紧凑输出裁剪。

移植说明：本包为平台无关重写，能力逻辑借鉴豆包 word 技能（read.py/audit.py），
非整文件复制（见 dev/notes/规则对齐-docx工具移植-2026-10-19.md，偏离项①）。
仅依赖 lxml + 标准库；不支持的环境在 CLI 入口明确报错，不静默降级。
"""
from __future__ import annotations

import copy
import hashlib
import re
from typing import Any

from lxml import etree

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
REL = "http://schemas.openxmlformats.org/package/2006/relationships"
W14 = "http://schemas.microsoft.com/office/word/2010/wordml"
WP = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
V = "urn:schemas-microsoft-com:vml"
O = "urn:schemas-microsoft-com:office:office"
C = "http://schemas.openxmlformats.org/drawingml/2006/chart"
DGM = "http://schemas.openxmlformats.org/drawingml/2006/diagram"
MC = "http://schemas.openxmlformats.org/markup-compatibility/2006"
PIC = "http://schemas.openxmlformats.org/drawingml/2006/picture"

# strict（ISO strict）→ transitional（Microsoft）命名空间归一
STRICT_NAMESPACE_MAP = {
    "http://purl.oclc.org/ooxml/wordprocessingml/main": W,
    "http://purl.oclc.org/ooxml/officeDocument/relationships": R,
    "http://purl.oclc.org/ooxml/drawingml/main": A,
    "http://purl.oclc.org/ooxml/drawingml/wordprocessingDrawing": WP,
    "http://purl.oclc.org/ooxml/drawingml/chart": C,
    "http://purl.oclc.org/ooxml/drawingml/diagram": DGM,
}

NS = {
    "w": W,
    "r": R,
    "rel": REL,
    "w14": W14,
    "wp": WP,
    "a": A,
    "v": V,
    "o": O,
    "c": C,
    "dgm": DGM,
    "mc": MC,
    "pic": PIC,
}

UNDERSTOOD_MC_NAMESPACES = set(STRICT_NAMESPACE_MAP) | {
    W, R, WP, A, V, O, C, DGM, W14,
    "http://schemas.microsoft.com/office/word/2010/wordprocessingShape",
    "http://schemas.microsoft.com/office/word/2010/wordprocessingGroup",
    "http://schemas.openxmlformats.org/drawingml/2006/picture",
    "http://schemas.microsoft.com/office/word/2012/wordml",
    "http://schemas.microsoft.com/office/word/2016/wordml/cid",
}

# 结构故事部件（正文 + 页眉页脚）；脚注/尾注/批注不在移植范围
STORY_PART_RE = re.compile(r"^word/(?:document|header\d+|footer\d+)\.xml$")
FIXED_STORY_RE = re.compile(r"^word/(?:header|footer)\d+\.xml$")
DELIVERABLE_TEXT_PART_RE = re.compile(
    r"^word/(?:document|header\d+|footer\d+)\.xml$"
)


def wtag(name: str) -> str:
    return "{%s}%s" % (W, name)


def qn(namespace: str, name: str) -> str:
    return "{%s}%s" % (namespace, name)


def qname(tag: Any) -> str:
    if isinstance(tag, str):
        return etree.QName(tag).localname
    return etree.QName(tag).localname


def wqn(name: str) -> str:
    """w:name 属性的限定名（与 wtag 语义区分：属性用）。"""
    return "{%s}%s" % (W, name)


def parse_xml(data: bytes, part: str = "part") -> etree._Element:
    """安全解析 OOXML 部件：禁 DTD/实体引用，strict→transitional 命名空间归一。

    失败抛 ValueError（由调用方转为受控错误），保证下游 c14n 哈希确定性。
    """
    parser = etree.XMLParser(resolve_entities=False, no_network=True)
    try:
        root = etree.fromstring(data, parser=parser)
    except etree.XMLSyntaxError as exc:
        raise ValueError("invalid XML in %s: %s" % (part, exc)) from exc
    doc_info = root.getroottree().docinfo
    if doc_info is not None and (doc_info.doctype or doc_info.internalDTD is not None):
        raise ValueError("XML in %s declares a DTD, which OOXML forbids" % part)
    if any(node.tag is etree.Entity for node in root.iter()):
        raise ValueError("XML in %s contains an entity reference" % part)
    for node in root.iter():
        if not isinstance(node.tag, str):
            continue
        for strict, transitional in STRICT_NAMESPACE_MAP.items():
            strict_prefix = "{%s}" % strict
            if node.tag.startswith(strict_prefix):
                node.tag = node.tag.replace(strict_prefix, "{%s}" % transitional, 1)
            for name in list(node.attrib):
                if name.startswith(strict_prefix):
                    node.set(
                        name.replace(strict_prefix, "{%s}" % transitional, 1),
                        node.attrib.pop(name),
                    )
    return root


def resolve_alternate_content(root: etree._Element) -> etree._Element:
    """取 mc:AlternateContent 的现代 Word 语义分支。

    Choice/Fallback 是互斥表示而非并存内容；第一个 Requires 前缀全被理解的
    Choice 胜出，否则用 Fallback。避免重复书签/绘图/字段/关系引用。
    """
    clone = etree.fromstring(etree.tostring(root))
    while True:
        alternates = clone.xpath(".//mc:AlternateContent", namespaces=NS)
        if not alternates:
            break
        for alternate in alternates:
            selected = None
            for choice in alternate.findall(qn(MC, "Choice")):
                required_prefixes = str(choice.get("Requires") or "").split()
                required_namespaces = [
                    choice.nsmap.get(prefix) for prefix in required_prefixes
                ]
                if required_prefixes and all(
                    namespace in UNDERSTOOD_MC_NAMESPACES
                    for namespace in required_namespaces
                ):
                    selected = choice
                    break
            if selected is None:
                selected = alternate.find(qn(MC, "Fallback"))
            parent = alternate.getparent()
            if parent is None:
                continue
            offset = parent.index(alternate)
            if selected is not None:
                for child in list(selected):
                    parent.insert(offset, copy.deepcopy(child))
                    offset += 1
            parent.remove(alternate)
    return clone


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical_xml_hash(root: etree._Element) -> str:
    """c14n 规范哈希；两代算法都失败时抛 ValueError（受控无效 XML）。"""
    try:
        data = etree.tostring(root, method="c14n", with_comments=True)
    except (etree.C14NError, ValueError):
        try:
            data = etree.tostring(root, method="c14n2", with_comments=True)
        except (etree.C14NError, ValueError, AttributeError) as exc:
            raise ValueError("cannot canonicalize XML: %s" % exc) from exc
    return sha256_bytes(data)


def element_hash(element: etree._Element | None) -> str | None:
    return canonical_xml_hash(element) if element is not None else None


def paragraph_text(paragraph: etree._Element) -> str:
    """段落可见文本（含嵌套 w:t，不含 w:delText 修订删除）。"""
    return "".join(paragraph.xpath(".//w:t/text()", namespaces=NS))


def run_text_value(run: etree._Element) -> str:
    return "".join(run.xpath("./w:t/text()", namespaces=NS))


def text_value(element: etree._Element | None) -> str:
    if element is None:
        return ""
    return "".join(element.itertext())


def attrs(element: etree._Element) -> dict[str, str]:
    return {qname(k): v for k, v in element.attrib.items()}


def attr_value(element: etree._Element | None, attribute: str = "val") -> str | None:
    if element is None:
        return None
    return element.get(wqn(attribute))


def integer_token(value: Any) -> str | None:
    """规范化整数身份：保留 OOXML 整数词法限制（[+-]?digits）。"""
    text = str(value).strip() if value is not None else ""
    if not re.fullmatch(r"[+-]?[0-9]+", text):
        return None
    try:
        return str(int(text))
    except ValueError:
        return None


def int_value(element: etree._Element | None, attribute: str = "val") -> int | None:
    token = integer_token(element.get(wqn(attribute))) if element is not None else None
    return int(token) if token is not None else None


UNSIGNED_MEASURE_RE = re.compile(r"[0-9]+(?:\.[0-9]+)?(?:mm|cm|in|pt|pc|pi)\Z")


def is_unsigned_measure(value: Any) -> bool:
    token = integer_token(value)
    if token is not None:
        return 0 <= int(token) <= (1 << 64) - 1
    return bool(UNSIGNED_MEASURE_RE.fullmatch(str(value or "").strip()))


def on_off_value(element: etree._Element | None) -> bool | None:
    """w:val 型开关；无 val 视为 true，0/false/off/no 视为 false。"""
    if element is None:
        return None
    raw = element.get(wqn("val"))
    if raw is None:
        return True
    return raw.strip().lower() not in {"0", "false", "off", "no"}


def on_off_attribute(element: etree._Element | None, attribute: str) -> bool | None:
    if element is None:
        return None
    raw = element.get(wqn(attribute))
    if raw is None:
        return None
    return raw.strip().lower() not in {"0", "false", "off", "no"}


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


def parse_shading(element: etree._Element | None) -> dict[str, str]:
    return word_attributes(
        element,
        ("val", "color", "fill", "themeColor", "themeTint", "themeShade"),
    )


def parse_borders(element: etree._Element | None) -> dict[str, dict[str, str]]:
    if element is None:
        return {}
    result: dict[str, dict[str, str]] = {}
    for child in element:
        if not isinstance(child.tag, str) or etree.QName(child).namespace != W:
            continue
        result[etree.QName(child).localname] = word_attributes(
            child,
            (
                "val", "sz", "space", "color", "themeColor",
                "themeTint", "themeShade", "frame", "shadow",
            ),
        )
    return result


def read_margins(root: etree._Element, path: str) -> dict[str, int]:
    out: dict[str, int] = {}
    margins = root.find(path, namespaces=NS)
    if margins is None:
        return out
    for tag in ("top", "start", "left", "bottom", "end", "right"):
        value = int_value(margins.find(wtag(tag), namespaces=NS), "w")
        if value is not None:
            out[tag] = value
    return out


def lean_value(item: dict[str, Any], excluded: set[str] | None = None) -> dict[str, Any]:
    excluded = excluded or set()
    return {
        key: value
        for key, value in item.items()
        if key not in excluded and value not in (None, "", [], {})
    }


def inline_value(value: Any) -> str:
    if isinstance(value, dict):
        return ",".join(
            "%s=%s" % (key, inline_value(item)) for key, item in sorted(value.items())
        )
    if isinstance(value, (list, tuple)):
        return ";".join(inline_value(item) for item in value)
    return str(value)


def deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    import copy

    result = copy.deepcopy(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result
