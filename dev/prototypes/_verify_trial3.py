# -*- coding: utf-8 -*-
"""核验 4 份试水样张 docx 结构（表格数/列数），确认范式差异落地。"""
from pathlib import Path

from docx import Document

ROOT = Path(r"E:\bidcraft_skill")
EXPECT = {
    "single-column": (2, "md 表 2 个（列表为段落）"),
    "tabular": (8, "2 md 表 + 6 双列数据行表"),
    "card": (8, "2 md 表 + 6 单列卡片表"),
    "image-left": (5, "3 图 × 1×2 左图右文表 + 2 md 表"),
}
for pid, (exp_n, desc) in EXPECT.items():
    docx = ROOT / ("技术标样张_%s.docx" % pid)
    doc = Document(str(docx))
    tables = doc.tables
    cols = sorted({len(t.columns) for t in tables})
    n = len(tables)
    status = "OK " if n == exp_n else "FAIL"
    print("%s %s tables=%d cols=%s expect=%s (%s)" % (status, pid, n, cols, exp_n, desc))
