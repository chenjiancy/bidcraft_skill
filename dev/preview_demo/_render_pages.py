# -*- coding: utf-8 -*-
"""渲染资格证明 PDF 为 PNG（预览框视觉验证）。"""
import sys
from pathlib import Path

import fitz  # noqa: E402

DEMO = Path(r"E:\bidcraft_skill\dev\preview_demo")
pdf = DEMO / "render" / "资格证明及辅助资料表.pdf"
d = fitz.open(pdf)
print("pages:", d.page_count)
out = []
for i in range(d.page_count):
    page = d.load_page(i)
    # 检查页面内是否含灰底占位图（非空大区域）
    pix = page.get_pixmap(matrix=fitz.Matrix(1.4, 1.4))
    png = DEMO / "render" / ("资格证明_p%02d.png" % (i + 1))
    pix.save(png)
    out.append("%s saved %dpx x %dpx" % (png.name, pix.width, pix.height))
    # 找图片块
    for img in page.get_images():
        xref = img[0]
        w, h = img[2], img[3]
        rects = page.get_image_rects(xref)
        for r in rects:
            out.append("  img xref=%d %dx%d px 位置(%.1f,%.1f,%.1f,%.1f)" % (xref, w, h, r.x0, r.y0, r.x1, r.y1))
d.close()
(DEMO / "render" / "_pages.txt").write_text("\n".join(out), encoding="utf-8")
print("\n".join(out))
