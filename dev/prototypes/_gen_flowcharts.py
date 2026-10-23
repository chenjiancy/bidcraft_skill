# -*- coding: utf-8 -*-
"""生成 2 张中文工程监理流程图（PIL 确定性绘制，无 AI 生图文字风险）：
  1) 监理工作总体程序流程图（7 步蛇形）
  2) 质量控制验收程序流程图（分支 + 整改回环）
输出到 共享资源/技术标风格/样张素材/，白底、工程蓝主色，供样张 fixture 引用。
"""
import os

from PIL import Image, ImageDraw, ImageFont

OUT_DIR = r"E:\bidcraft_skill\共享资源\技术标风格\样张素材"

# 颜色
C_BORDER = "#1B2C52"   # 工程蓝主色
C_FILL = "#EEF2F9"     # 浅蓝填充
C_FILL_BR = "#F7E8E8"  # 不合格分支浅红
C_FILL_OK = "#E4F2E9"  # 合格分支浅绿
C_TEXT = "#222222"
C_SUB = "#5A6B8C"


def _font(path, size):
    return ImageFont.truetype(path, size)


F_BODY = lambda s: _font(r"C:\Windows\Fonts\msyh.ttc", s)
F_TITLE = lambda s: _font(r"C:\Windows\Fonts\msyhbd.ttc", s)
F_SMALL = lambda s: _font(r"C:\Windows\Fonts\simhei.ttf", s)


def _center(draw, box, text, font, fill):
    """在 box=(x1,y1,x2,y2) 内居中绘制文本（单行/双行）。"""
    x1, y1, x2, y2 = box
    lines = text.split("\n")
    heights = []
    for ln in lines:
        bb = draw.textbbox((0, 0), ln, font=font)
        heights.append(bb[3] - bb[1])
    total_h = sum(heights) + (len(lines) - 1) * 6
    y = y1 + (y2 - y1 - total_h) / 2
    for i, ln in enumerate(lines):
        bb = draw.textbbox((0, 0), ln, font=font)
        w = bb[2] - bb[0]
        h = bb[3] - bb[1]
        draw.text((x1 + (x2 - x1 - w) / 2 - bb[0], y - bb[1]), ln, font=font, fill=fill)
        y += h + 6


def _box(draw, box, fill, outline, width=2, radius=10):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def _arrow(draw, p1, p2, color=C_BORDER, width=3, head=10):
    """直线箭头 p1->p2。"""
    draw.line([p1, p2], fill=color, width=width)
    import math
    ang = math.atan2(p2[1] - p1[1], p2[0] - p1[0])
    for s in (math.radians(150), math.radians(-150)):
        x = p2[0] + head * math.cos(ang + s)
        y = p2[1] + head * math.sin(ang + s)
        draw.line([p2, (x, y)], fill=color, width=width)


def _elbow(draw, pts, color=C_BORDER, width=3):
    for a, b in zip(pts[:-1], pts[1:]):
        _arrow(draw, a, b, color=color, width=width)


def flowchart_program():
    """监理工作总体程序流程图：7 步蛇形 4+3。"""
    W, H = 1640, 540
    img = Image.new("RGB", (W, H), "#FFFFFF")
    d = ImageDraw.Draw(img)
    steps = [
        "签订监理合同", "组建项目监理机构", "编制监理规划", "监理工作交底",
        "实施三控两管一协调", "组织竣工验收", "签发工程移交证书",
    ]
    bw, bh, gap = 330, 110, 56
    x0, y1, y2 = 40, 70, 300
    # 行1 4 框
    row1 = []
    for i in range(4):
        x = x0 + i * (bw + gap)
        row1.append((x, y1, x + bw, y1 + bh))
    # 行2 3 框
    row2 = []
    for i in range(3):
        x = x0 + i * (bw + gap)
        row2.append((x, y2, x + bw, y2 + bh))
    # 序号徽标
    for idx, box in enumerate(row1 + row2, 1):
        _box(d, box, C_FILL, C_BORDER)
        cx, cy = box[0] + 34, box[1] + 26
        d.ellipse([cx - 17, cy - 17, cx + 17, cy + 17], fill=C_BORDER)
        _center(d, (cx - 17, cy - 17, cx + 17, cy + 17), str(idx), F_BODY(22), "#FFFFFF")
        txt = steps[idx - 1]
        _center(d, (box[0] + 6, box[1] + 44, box[2] - 6, box[3] - 8), txt, F_BODY(26), C_TEXT)
    # 行1 箭头
    for i in range(3):
        b1, b2 = row1[i], row1[i + 1]
        _arrow(d, (b1[2] + 4, (b1[1] + b1[3]) / 2), (b2[0] - 4, (b2[1] + b2[3]) / 2))
    # 行2 箭头
    for i in range(2):
        b1, b2 = row2[i], row2[i + 1]
        _arrow(d, (b1[2] + 4, (b1[1] + b1[3]) / 2), (b2[0] - 4, (b2[1] + b2[3]) / 2))
    # 行1 末 → 行2 首（折线）
    e = row1[3]
    s = row2[0]
    _elbow(d, [(e[2] + 4, (e[1] + e[3]) / 2), (W - 30, (e[1] + e[3]) / 2),
               (W - 30, (s[1] + s[3]) / 2), (s[2] + 4, (s[1] + s[3]) / 2)])
    return img


def flowchart_quality():
    """质量控制验收程序流程图：垂直主链 + 不合格右分支回环。"""
    W, H = 1640, 720
    img = Image.new("RGB", (W, H), "#FFFFFF")
    d = ImageDraw.Draw(img)
    bw, bh = 560, 96
    cx = 60
    boxes = [
        ("分项工程（检验批）完成", cx, 50),
        ("施工单位自检合格", cx, 190),
        ("填报报验申请资料", cx, 330),
        ("监理现场验收", cx, 470),
        ("签认合格，进入下道工序", cx, 610),
    ]
    rects = [(x, y, x + bw, y + bh) for _, x, y in boxes]
    for i, box in enumerate(rects):
        fill = C_FILL_OK if i == 4 else C_FILL
        _box(d, box, fill, C_BORDER)
        _center(d, box, boxes[i][0], F_BODY(26), C_TEXT)
    for a, b in zip(rects[:-1], rects[1:]):
        _arrow(d, ((a[0] + a[2]) / 2, a[3] + 4), ((b[0] + b[2]) / 2, b[1] - 4))
    # 不合格分支（右）
    bx, by, bbx, bby = 900, 470, 1460, 566
    _box(d, (bx, by, bbx, bby), C_FILL_BR, "#C0504D")
    _center(d, (bx, by, bbx, bby), "验收不合格：签发监理通知\n限期整改后重新报验", F_BODY(22), "#8B3A3A")
    # 框4 右缘 → 分支框
    r4 = rects[3]
    _elbow(d, [(r4[2] + 4, (r4[1] + r4[3]) / 2), (bx - 8, (r4[1] + r4[3]) / 2), (bx - 8, by + 20)])
    # 分支框 → 回环回 框3（重新报验）
    r3 = rects[2]
    _elbow(d, [(bbx, by + 40), (bbx + 60, by + 40), (bbx + 60, r3[1] + 20), (r3[2], r3[1] + 20)],
           color="#C0504D", width=3)
    # 箭头标注
    d.text((r4[2] + 16, r4[1] - 8), "不合格", font=F_SMALL(20), fill="#C0504D")
    return img


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    f1 = os.path.join(OUT_DIR, "样张_监理工作程序流程图.png")
    f2 = os.path.join(OUT_DIR, "样张_质量控制程序流程图.png")
    flowchart_program().save(f1)
    flowchart_quality().save(f2)
    print("saved", f1)
    print("saved", f2)


if __name__ == "__main__":
    main()
