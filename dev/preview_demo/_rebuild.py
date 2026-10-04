# -*- coding: utf-8 -*-
"""重建演示模板（含 sanitize 修复）→ Word 导出全部 10 份验证。"""
import shutil
import sys
from pathlib import Path

sys.path.insert(0, r"E:\bidcraft_skill\scripts")

ENT = Path(r"E:\监理标书制作\示例建设工程监理有限公司")
PROJ = "示例示例园区尾水水质提升工程（EPC总承包）监理"
DEMO = Path(r"E:\bidcraft_skill\dev\preview_demo")

# 保留诊断目录，重建 项目模板/render
for sub in ("项目模板", "render"):
    p = DEMO / sub
    shutil.rmtree(p, ignore_errors=True)
    p.mkdir(parents=True)

from m5_project import generator as gen  # noqa: E402
res = gen.generate(ENT, PROJ, out_dir=DEMO / "项目模板", register_baseline=False)
n_ph = sum(f.get("图片占位框", 0) for f in res["文件"])
print("生成文件:", len(res["文件"]), "预览框:", n_ph)

from docx import Document  # noqa: E402
bad = []
for f in (DEMO / "项目模板").glob("*.docx"):
    doc = Document(str(f))
    kids = list(doc.element.body)
    if kids[-1].tag.split("}")[-1] != "sectPr":
        bad.append(f.name + ":body尾" + kids[-1].tag.split("}")[-1])
print("body 异常:", bad or "无")

import win32com.client  # noqa: E402
word = win32com.client.Dispatch("Word.Application")
word.Visible = False
word.DisplayAlerts = 0
ok = fail = 0
try:
    for f in sorted((DEMO / "项目模板").glob("*.docx")):
        pdf = DEMO / "render" / (f.stem + ".pdf")
        try:
            d = word.Documents.Open(str(f), ReadOnly=True)
            d.ExportAsFixedFormat(str(pdf), 17)
            d.Close(False)
            ok += 1
            print("OK  ", f.name)
        except Exception as e:
            fail += 1
            print("FAIL", f.name, "->", (getattr(e, "excepinfo", None) or [""])[2])
finally:
    word.Quit()
print("Word 导出: OK=%d FAIL=%d" % (ok, fail))

# pymupdf 渲染 PNG
import fitz  # noqa: E402
for pdf in sorted((DEMO / "render").glob("*.pdf")):
    d = fitz.open(pdf)
    for i in range(d.page_count):
        pix = d.load_page(i).get_pixmap(matrix=fitz.Matrix(1.1, 1.1))
        pix.save(DEMO / "render" / ("%s_p%02d.png" % (pdf.stem, i + 1)))
    d.close()
print("PNG 渲染完成")
