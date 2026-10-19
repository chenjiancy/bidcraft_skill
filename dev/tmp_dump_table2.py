# -*- coding: utf-8 -*-
"""临时调试2：对比资格证明及辅助资料表 原文/模板表格行（取前 2 个表格）。"""
import sys, os
sys.path.insert(0, r"E:\bidcraft_skill\scripts")
from m5_project.gen_blocks import _extract_blocks
from m5_project.gen_common import skip_chapter_head
from m5_project import verify_text as vt
from docx import Document
import json

SRC = r"E:\监理标书制作\和县建设工程监理有限公司\项目级\和县2026年老旧小区改造项目（EPC总承包）监理\招标解析\招标文件_和县2026年老旧小区改造项目（EPC总承包）监理.docx"
OUT = r"E:\监理标书制作\和县建设工程监理有限公司\项目级\和县2026年老旧小区改造项目（EPC总承包）监理\项目模板\资格证明及辅助资料表.docx"
CONTRACT = r"E:\监理标书制作\和县建设工程监理有限公司\项目级\和县2026年老旧小区改造项目（EPC总承包）监理\招标解析\内容契约\内容契约.json"

blocks, doc = _extract_blocks(SRC)
contract = json.load(open(CONTRACT, encoding="utf-8"))
by_id = {it["id"]: it for it in contract["格式文件"]}
ids = ["F06a","F06b","F06c","F06d","F06e","F06f","F06g","F06h","F06i","F06j","F06k"]
valid = [by_id[i] for i in ids if i in by_id and by_id[i].get("块范围")]
lo = min(it["块范围"][0] for it in valid)
hi = max(it["块范围"][-1] for it in valid)
lo = skip_chapter_head(blocks, lo)
print("块范围:", lo, hi)

src_seq, src_tables = vt._iter_source_text(blocks, lo, hi, doc, "资格证明及辅助资料表.docx", "")
print("原文表格数:", len(src_tables))
for ti, rows in enumerate(src_tables[:2]):
    print("=== 原文表格#%d 行数=%d ===" % (ti, len(rows)))
    for ri, row in enumerate(rows[:6]):
        print("  行%d %r" % (ri, row))

tpl = Document(OUT)
tbls = []
for child in tpl.element.body.iterchildren():
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
        tbls.append(rows)
print("模板表格数:", len(tbls))
for ti, rows in enumerate(tbls[:2]):
    print("=== 模板表格#%d 行数=%d ===" % (ti, len(rows)))
    for ri, row in enumerate(rows[:6]):
        print("  行%d %r" % (ri, row))

# 表格索引对应关系检查
print("=== 对应校验（模板表格 ti → 原文表格 si）===")
used = set()
for ti, trows in enumerate(tbls[:3]):
    for si, srows in enumerate(src_tables):
        if si in used: continue
        ok = True
        # 前3行位置匹配
        for srow, trow in zip(srows[:3], trows[:3]):
            if not vt._row_match_score(srow, trow):
                ok = False; break
        if ok:
            print("模板表格#%d ↔ 原文表格#%d (used)" % (ti, si))
            used.add(si)
            break
