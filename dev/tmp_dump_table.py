# -*- coding: utf-8 -*-
"""临时调试：对比开标一览表 原文表格行 vs 模板表格行（指纹/归一后文本）。"""
import sys, os
sys.path.insert(0, r"E:\bidcraft_skill\scripts")
from m5_project.gen_blocks import _extract_blocks
from m5_project.gen_common import skip_chapter_head
from m5_project import verify_text as vt
from m5_project.gen_text import _para_text
from docx import Document
import json

SRC = r"E:\监理标书制作\和县建设工程监理有限公司\项目级\和县2026年老旧小区改造项目（EPC总承包）监理\招标解析\招标文件_和县2026年老旧小区改造项目（EPC总承包）监理.docx"
OUT = r"E:\监理标书制作\和县建设工程监理有限公司\项目级\和县2026年老旧小区改造项目（EPC总承包）监理\项目模板\开标一览表.docx"
CONTRACT = r"E:\监理标书制作\和县建设工程监理有限公司\项目级\和县2026年老旧小区改造项目（EPC总承包）监理\招标解析\内容契约\内容契约.json"

blocks, doc = _extract_blocks(SRC)
contract = json.load(open(CONTRACT, encoding="utf-8"))
by_id = {it["id"]: it for it in contract["格式文件"]}
lo, hi = by_id["F02"]["块范围"]
lo = skip_chapter_head(blocks, lo)
print("块范围:", lo, hi)

# 原文表格行
src_seq, src_tables = vt._iter_source_text(blocks, lo, hi, doc, "开标一览表.docx", "")
print("=== 原文表格 ===")
for ti, rows in enumerate(src_tables):
    print("表格#%d 行数=%d" % (ti, len(rows)))
    for ri, row in enumerate(rows):
        fp = vt._row_fingerprint(row)
        print("  行%d fp=%s" % (ri, fp))
        for ci, c in enumerate(row):
            print("    [%d] %r" % (ci, c))

# 模板表格行
tpl = Document(OUT)
print("=== 模板表格 ===")
for ti, child in enumerate(tpl.element.body.iterchildren()):
    if child.tag.endswith("}tbl"):
        from docx.table import Table
        tbl = Table(child, tpl)
        rows = []
        for row in tbl.rows:
            cells = []
            seen = set()
            for cell in row.cells:
                if id(cell._tc) not in seen:
                    seen.add(id(cell._tc))
                    cells.append(cell.text)
            rows.append(cells)
        print("表格#%d 行数=%d" % (ti, len(rows)))
        for ri, row in enumerate(rows):
            fp = vt._row_fingerprint(row)
            print("  行%d fp=%s" % (ri, fp))
            for ci, c in enumerate(row):
                print("    [%d] %r" % (ci, c))
