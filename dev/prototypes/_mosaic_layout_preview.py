# -*- coding: utf-8 -*-
"""A. 10 个版面范式样张 → 2×5 对比拼图 + 每格 2 页（封面+目录或正文首页）。"""
import json
from pathlib import Path

import fitz
from PIL import Image, ImageDraw, ImageFont

OUT = Path(r"E:\bidcraft_skill\dev\reports\layout-preview")
ROOT = Path(r"E:\bidcraft_skill")
PRESETS = [
    ("single-column", "单栏流式"), ("tabular", "表格化布局"), ("two-column", "双栏分栏"),
    ("card", "卡片式布局"), ("image-left", "左图右文"), ("divider", "章节分隔页"),
    ("data-row", "数据行布局"), ("image-right", "右图左文"), ("hybrid-flow", "混合流式"),
    ("minimal-clean", "极简留白"),
]
CELL_W, CELL_H = 420, 1120  # 每格：两页竖排
GAP = 24
COLS = 2

fonts = []
for name in ("C:/Windows/Fonts/msyhbd.ttc", "C:/Windows/Fonts/simhei.ttf"):
    try:
        fonts.append(ImageFont.truetype(name, 26))
        break
    except Exception:
        continue

cells = []
for pid, label in PRESETS:
    pdf = ROOT / ("技术标样张_%s.pdf" % pid)
    doc = fitz.open(str(pdf))
    pages = []
    # 版面范式差异体现在正文页：取索引 2、3（p3 起正文；若页面不足则回退 1、2）
    picks = [2, 3] if doc.page_count >= 4 else [1, 2]
    for i in picks:
        pm = doc[i].get_pixmap(matrix=fitz.Matrix(0.62, 0.62))
        img = Image.frombytes("RGB", (pm.width, pm.height), pm.samples)
        # 保持 CELL_W 宽度（封面等页面高度可能不同，用灰底垫高）
        ratio = CELL_W / img.width
        img = img.resize((CELL_W, max(1, int(img.height * ratio))), Image.LANCZOS)
        pages.append(img)
    doc.close()
    # 两页竖排 + 底部标签
    total_h = sum(p.height for p in pages) + 44 + GAP * (len(pages) - 1)
    canvas = Image.new("RGB", (CELL_W, total_h), "#F2F4F8")
    y = 0
    for p in pages:
        canvas.paste(p, (0, y)); y += p.height + GAP
    d = ImageDraw.Draw(canvas)
    d.rectangle([0, total_h - 44, CELL_W, total_h], fill="#1B2C52")
    if fonts:
        d.text((14, total_h - 36), "%s · %s" % (pid, label), font=fonts[0], fill="#FFFFFF")
    cells.append((canvas, pid, label))

grid_w = COLS * CELL_W + (COLS + 1) * GAP
rows = (len(cells) + COLS - 1) // COLS
grid_h = rows * CELL_H + (rows + 1) * GAP
grid = Image.new("RGB", (grid_w, grid_h), "#DDE3EC")
for idx, (cell, pid, label) in enumerate(cells):
    r, c = divmod(idx, COLS)
    x = GAP + c * (CELL_W + GAP)
    y = GAP + r * (CELL_H + GAP)
    grid.paste(cell, (x, y))
grid.save(str(OUT / "十版面对比图.jpg"), quality=88)
print("saved %s  %dx%d" % (OUT / "十版面对比图.jpg", grid.width, grid.height))
# 超高切两段（>4000px 时 Read 无法加载整图）
if grid.height > 4000:
    h2 = grid.height // 2
    grid.crop((0, 0, grid.width, h2)).save(str(OUT / "十版面对比图_top.jpg"), quality=90)
    grid.crop((0, h2 - 60, grid.width, grid.height)).save(str(OUT / "十版面对比图_bot.jpg"), quality=90)
    print("split top/bot")
