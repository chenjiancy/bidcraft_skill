# -*- coding: utf-8 -*-
"""核验 10 范式样张 docx 结构：表格数/列数、two-column 分栏节、divider 章标题、范式差异落地。"""
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn

ROOT = Path(r"E:\bidcraft_skill")
PRESETS = ["single-column", "tabular", "two-column", "card", "image-left",
           "divider", "data-row", "image-right", "hybrid-flow", "minimal-clean"]
# 表格数预期：md 表 2 个；tabular/data-row 6 个列表行表；card 6 卡片；image-left/image-right 5 图表(3 摄影+2 流程)
EXPECT = {
    "single-column": 2,
    "tabular": 8,
    "two-column": 2,
    "card": 8,
    "image-left": 7,
    "divider": 2,
    "data-row": 8,
    "image-right": 7,
    "hybrid-flow": 2,
    "minimal-clean": 2,
}

all_ok = True
for pid in PRESETS:
    docx = ROOT / ("技术标样张_%s.docx" % pid)
    doc = Document(str(docx))
    n = len(doc.tables)
    cols = sorted({len(t.columns) for t in doc.tables})
    ok = n == EXPECT[pid]
    all_ok &= ok
    notes = []
    # two-column：第二节 w:cols num=2
    if pid == "two-column":
        secs = doc.sections
        num_cols = []
        for s in secs:
            cols_el = s._sectPr.find(qn("w:cols"))
            num_cols.append(cols_el.get(qn("w:num")) if (cols_el is not None and cols_el.get(qn("w:num"))) else "1")
        notes.append("sections=%d cols=%s" % (len(secs), ",".join(num_cols)))
        ok &= (len(secs) >= 2 and num_cols[-1] == "2")
    # divider：章标题居中 + 段落底边框色条 + outlineLvl 0
    if pid == "divider":
        found = 0
        for p in doc.paragraphs:
            pPr = p._p.pPr
            if pPr is not None and pPr.find(qn("w:pBdr")) is not None and p.text.startswith("第"):
                found += 1
        notes.append("divider_titles=%d" % found)
        ok &= (found >= 3)
    status = "OK " if ok else "FAIL"
    print("%s %s tables=%d cols=%s expect=%d%s" % (status, pid, n, cols, EXPECT[pid],
                                                   (" " + "; ".join(notes)) if notes else ""))
    all_ok &= ok
print("ALL_OK" if all_ok else "HAS_FAIL")
