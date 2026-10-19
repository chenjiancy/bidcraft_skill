# -*- coding: utf-8 -*-
"""临时调试3：直接调用 verify_docx_vs_source 对资格证明表，打印行级匹配细节。"""
import sys, os
sys.path.insert(0, r"E:\bidcraft_skill\scripts")
from m5_project.gen_blocks import _extract_blocks
from m5_project.gen_common import skip_chapter_head
from m5_project import verify_text as vt
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

r = vt.verify_docx_vs_source(OUT, blocks, lo, hi, fname="资格证明及辅助资料表.docx",
                             project_name="", doc=doc)
print("结论:", r["结论"], "问题数:", len(r["问题"]))
for p in r["问题"][:15]:
    print(" -", p["位置"], "|", p["说明"])

# 行级细节：逐表格打印匹配失败的原文行
src_seq, src_tables = vt._iter_source_text(blocks, lo, hi, doc, "资格证明及辅助资料表.docx", "")
tpl = __import__("docx").Document(OUT)
tpl_tables = []
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
        tpl_tables.append(rows)
print("表格数 原文=%d 模板=%d" % (len(src_tables), len(tpl_tables)))
for ti, trows in enumerate(tpl_tables[:12]):
    srows = src_tables[ti] if ti < len(src_tables) else None
    if srows is None:
        print("表格#%d: 模板多出（无原文对应）" % ti)
        continue
    if len(srows) != len(trows):
        print("表格#%d: 行数不同 原文=%d 模板=%d" % (ti, len(srows), len(trows)))
    used = set()
    bad = []
    for si, srow in enumerate(srows):
        m = None
        for tii, trow in enumerate(trows):
            if tii in used: continue
            if vt._row_match_score(srow, trow):
                m = tii; break
        if m is None:
            bad.append(si)
        else:
            used.add(m)
    if bad:
        print("表格#%d 缺失行: %s" % (ti, bad))
        for si in bad[:3]:
            print("   原文行%d %r" % (si, srows[si]))
            print("   norm: %r" % ([vt.norm_ph(c) for c in srows[si]]))
