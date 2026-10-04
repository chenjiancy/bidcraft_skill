# -*- coding: utf-8 -*-
"""
bidcraft · M4 招标文件解析 —— PDF 结构化提取（④ 建议落地）

背景：此前 PDF 招标文件依赖 agent 人工读 + 手动传 --text-file；本模块让
`tender-extract --file <xxx.pdf>` 自动完成：
  - 文本块级提取（按版面块重建行，天然处理多栏——不同栏是不同的文本块）；
  - 行内双栏拆分（同一行跨度跨双栏时，按 x 坐标最大空隙切成左/右栏，先左后右）；
  - 表格感知：page.find_tables() 把带框表格抽成 Markdown 表格，避免表格文字混进正文；
  - 表内去重：与表格 bbox 大面积重叠的文本块不再重复输出；
  - 每页输出「【第 N 页】」标记，供 agent 回看锚点（页码可追溯）。

输出：
  extract_pdf(path) -> (text, blocks)
    text:   完整可读原文（页面标记 + 正文行 + Markdown 表格）
    blocks: 结构感知切片 [{page, kind: para|table, text, bbox}]（为后续 RAG
            多路召回/格式契约解析做结构切片，⑤ 混合检索可直接复用）

依赖：PyMuPDF（pymupdf，fitz API）。未安装时自动降级：抛出 LibraryError，
并提示改用 --text-file（agent 提取文本）回退——保持既有契约不变。
"""

import importlib.util

try:
    import pymupdf as _fitz
except ImportError:
    try:
        import fitz as _fitz
    except ImportError:
        _fitz = None

HAVE_FITZ = _fitz is not None
FITZ_INSTALL_HINT = (
    "未安装 PyMuPDF（PDF 结构化提取依赖它）。请 pip install pymupdf 后重试，"
    "或改用 --text-file 传 agent 已提取的正文文本（既有回退路径）。"
)


def _library_error(msg):
    from _shared import core
    return core.LibraryError(msg)


# --------------------------------------------------------------------------
# 表格 → Markdown
# --------------------------------------------------------------------------
def _cell_text(v):
    """单元格文本规整：None→空、去首尾空白、换行→空格、竖线→全角（防破坏表结构）。"""
    if v is None:
        return ""
    t = str(v).replace("\r", " ").replace("\n", " ").strip()
    return t.replace("|", "｜")


def _rows_to_markdown(rows):
    """list[list[str]] → Markdown 表格（首行作表头 + 分隔行）。"""
    rows = [list(r) for r in rows if any(_cell_text(c) for c in r)]
    if not rows:
        return ""
    ncol = max(len(r) for r in rows)
    norm = [r + [""] * (ncol - len(r)) for r in rows]
    head = "| " + " | ".join(_cell_text(c) for c in norm[0]) + " |"
    sep = "| " + " | ".join(["---"] * ncol) + " |"
    body = ["| " + " | ".join(_cell_text(c) for c in r) + " |" for r in norm[1:]]
    return "\n".join([head, sep] + body)


# --------------------------------------------------------------------------
# 多栏处理（行内 x 坐标空隙 → 左右栏）
# --------------------------------------------------------------------------
def _split_line_columns(line, mid_x):
    """按中界把一行 spans 切成左/右两段（返回 (left_text, right_text)）。"""
    spans = sorted(line["spans"], key=lambda s: (s["bbox"][0], s["bbox"][1]))
    left = "".join(s["text"] for s in spans if s["bbox"][0] < mid_x)
    right = "".join(s["text"] for s in spans if s["bbox"][0] >= mid_x)
    return left, right


def _block_lines(block):
    """文本块 → 行列表；检测行内双栏空隙（gap > 20% 块宽）时先左栏后右栏。"""
    lines = sorted(block["lines"], key=lambda l: (l["bbox"][1], l["bbox"][0]))
    if not lines:
        return []
    all_x = [s["bbox"][0] for l in lines for s in l["spans"]]
    lo, hi = min(all_x), max(all_x)
    width = (hi - lo) or 1.0
    # x0 聚簇（2pt 容差）→ 找最大空隙
    clusters = sorted({round(x / 2.0) * 2 for x in all_x})
    best_gap, mid = 0.0, None
    for i in range(len(clusters) - 1):
        gap = clusters[i + 1] - clusters[i]
        if gap > best_gap:
            best_gap, mid = gap, (clusters[i] + clusters[i + 1]) / 2.0
    if mid is not None and best_gap > max(0.2 * width, 24.0):
        lefts, rights = [], []
        for l in lines:
            lt, rt = _split_line_columns(l, mid)
            if lt.strip():
                lefts.append(lt)
            if rt.strip():
                rights.append(rt)
        return lefts + rights
    out = []
    for l in lines:
        spans = sorted(l["spans"], key=lambda s: (s["bbox"][0], s["bbox"][1]))
        out.append("".join(s["text"] for s in spans))
    return out


# --------------------------------------------------------------------------
# 表格 bbox（用于正文去重）
# --------------------------------------------------------------------------
def _bbox_overlap_ratio(a, b):
    """两矩形交集面积 / a 面积（a: 文本块 bbox，b: 表格 bbox）。"""
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    ox = min(ax1, bx1) - max(ax0, bx0)
    oy = min(ay1, by1) - max(ay0, by0)
    if ox <= 0 or oy <= 0:
        return 0.0
    area_a = max((ax1 - ax0) * (ay1 - ay0), 1e-6)
    return (ox * oy) / area_a


# --------------------------------------------------------------------------
# 主入口
# --------------------------------------------------------------------------
def _extract_page(page, pno):
    """单页 → (文本片段, blocks 切片, 表格 markdown 列表)。"""
    tabs_md, tab_boxes, tab_y0x0 = [], [], []
    if hasattr(page, "find_tables"):
        try:
            for tab in page.find_tables():
                rows = tab.extract()
                md = _rows_to_markdown(rows)
                if md:
                    tabs_md.append(md)
                    try:
                        b = tuple(tab.bbox)
                        tab_boxes.append(b)
                        tab_y0x0.append((b[1], b[0]))
                    except Exception:
                        tab_y0x0.append((0.0, 0.0))
        except Exception:
            tab_boxes, tabs_md, tab_y0x0 = [], [], []  # 表格识别失败 → 降级为纯文本

    entries = []   # (y0, x0, kind, text)
    blocks_out = []
    try:
        d = page.get_text("dict")
    except Exception:
        return ["【第 %d 页】" % pno], [], []
    for b in d.get("blocks", []):
        if b.get("type", 0) != 0:
            continue
        bb = tuple(b.get("bbox", (0, 0, 0, 0)))
        if any(_bbox_overlap_ratio(bb, tb) > 0.5 for tb in tab_boxes):
            continue  # 表格内文本由表格入口输出，正文不重复
        ls = _block_lines(b)
        text = "\n".join(ls)
        if not text.strip():
            continue
        blocks_out.append({"page": pno, "kind": "para", "text": text,
                           "bbox": list(bb)})
        entries.append((bb[1], bb[0], "para", text))
    for i, md in enumerate(tabs_md):
        blocks_out.append({"page": pno, "kind": "table", "text": md,
                           "bbox": list(tab_boxes[i]) if i < len(tab_boxes) else []})
        entries.append((tab_y0x0[i][0], tab_y0x0[i][1], "table", md))

    entries.sort(key=lambda e: (e[0], e[1]))
    parts = ["【第 %d 页】" % pno]
    for _, _, kind, text in entries:
        if kind == "table":
            parts.extend(["", text, ""])
        else:
            parts.append(text)
    return parts, blocks_out, tabs_md


def extract_pdf(path):
    """PDF → (原文文本, 结构切片 blocks)。失败抛 LibraryError（含未装 PyMuPDF）。"""
    if not HAVE_FITZ:
        raise _library_error(FITZ_INSTALL_HINT)
    try:
        doc = _fitz.open(path)
    except Exception as e:
        raise _library_error(
            "无法解析 PDF：%s（文件可能损坏或非 PDF；或改用 --text-file 传 agent 提取文本）" % e)
    try:
        parts, blocks = [], []
        for pno, page in enumerate(doc, 1):
            page_parts, page_blocks, _ = _extract_page(page, pno)
            parts.extend(page_parts)
            blocks.extend(page_blocks)
        text = "\n".join(parts).rstrip()
    finally:
        doc.close()
    if not blocks:
        raise _library_error("PDF 未提取到任何文本（可能为纯扫描件无文字层；请改用 --text-file 传 OCR 文本）")
    return text, blocks


def extract_pdf_text(path):
    """仅取文本（tender.extract_text_file 用）。"""
    text, _ = extract_pdf(path)
    return text
