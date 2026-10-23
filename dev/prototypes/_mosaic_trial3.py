# -*- coding: utf-8 -*-
"""3 试水范式样张拼图（正文页索引 2、3）：tabular / card / image-left / single-column 基准。"""
from pathlib import Path

import fitz
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(r"E:\bidcraft_skill")
ITEMS = [
    ("single-column", "单栏流式（基准）"),
    ("tabular", "表格化布局"),
    ("card", "卡片式布局"),
    ("image-left", "左图右文（fixture 无图→降级）"),
]
CELL_W, GAP, COLS = 430, 20, 2
fonts = []
for name in ("C:/Windows/Fonts/msyhbd.ttc", "C:/Windows/Fonts/simhei.ttf"):
    try:
        fonts.append(ImageFont.truetype(name, 24))
        break
    except Exception:
        continue

cells = []
for pid, label in ITEMS:
    pdf = ROOT / ("技术标样张_%s.pdf" % pid)
    doc = fitz.open(str(pdf))
    picks = [2, 3] if doc.page_count >= 4 else [1, 2]
    pages = []
    for i in picks:
        pm = doc[i].get_pixmap(matrix=fitz.Matrix(0.62, 0.62))
        img = Image.frombytes("RGB", (pm.width, pm.height), pm.samples)
        ratio = CELL_W / img.width
        img = img.resize((CELL_W, max(1, int(img.height * ratio))), Image.LANCZOS)
        pages.append(img)
    doc.close()
    total_h = sum(p.height for p in pages) + 40 + GAP * (len(pages) - 1)
    canvas = Image.new("RGB", (CELL_W, total_h), "#F2F4F8")
    y = 0
    for p in pages:
        canvas.paste(p, (0, y)); y += p.height + GAP
    d = ImageDraw.Draw(canvas)
    d.rectangle([0, total_h - 40, CELL_W, total_h], fill="#1B2C52")
    if fonts:
        d.text((12, total_h - 33), "%s · %s" % (pid, label), font=fonts[0], fill="#FFFFFF")
    cells.append(canvas)

grid_w = COLS * CELL_W + (COLS + 1) * GAP
rows = (len(cells) + COLS - 1) // COLS
cell_h = max(c.height for c in cells)
grid_h = rows * cell_h + (rows + 1) * GAP
grid = Image.new("RGB", (grid_w, grid_h), "#DDE3EC")
for idx, cell in enumerate(cells):
    r, c = divmod(idx, COLS)
    x = GAP + c * (CELL_W + GAP)
    y = GAP + r * (cell_h + GAP)
    grid.paste(cell, (x, y))
out = ROOT / "dev" / "reports" / "layout-preview" / "试水三范式对比.jpg"
grid.save(str(out), quality=88)
print("saved %s %dx%d" % (out, grid.width, grid.height))
# 若超高切两段
if grid.height > 4000:
    h2 = grid.height // 2
    grid.crop((0, 0, grid.width, h2)).save(str(out.with_name("试水三范式对比_top.jpg")), quality=90)
    grid.crop((0, h2 - 40, grid.width, grid.height)).save(str(out.with_name("试水三范式对比_bot.jpg")), quality=90)
    print("split top/bot")
