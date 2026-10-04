# -*- coding: utf-8 -*-
"""
M5 图片占位预览框（方案A v1.0，2026-10-04 用户确认）。

目标：让 Word 模板直接可见「图片将来放哪、多大、放什么」——
生成器在每个【图片：xxx】占位段后插入一张真实尺寸的灰底占位图
（尺寸与 image_spec 目标口径一致），框内写：将插入内容 + 尺寸。
填充引擎生成商务标时定位该框（docPr@descr 标记 IMG_PH:<占位文案>）
并删除，再按同口径插入真实图。

只做确定性绘图，无业务判断；PIL 为运行依赖（image_spec.fit_size 已用）。
"""
import hashlib
import os
import tempfile
from pathlib import Path

from . import image_spec as imgsp

PH_PREVIEW_PREFIX = "IMG_PH:"

# 占位预览框尺寸缺失时的兜底（cm）
_DEFAULT_BOX = (16.0, 12.0)


def box_size_for(ph_text):
    """占位预览框尺寸（cm）：优先按 image_spec 目标口径；组合占位取代表框。"""
    key = imgsp.spec_for(ph_text)
    if key and key in imgsp.IMG_SPEC:
        spec = imgsp.IMG_SPEC[key]
        w = float(spec.get("宽", 16))
        h = spec.get("高", None)
        if isinstance(h, (int, float)):
            return (w, float(h))
        return (w, 8.0)          # 自适应（组织机构框图等）→ 代表高 8cm
    return _DEFAULT_BOX          # 组合占位（资质组/人员组等）→ 代表框 12×16


def _font_path():
    """Windows 常见中文字体（楷/黑/宋）；无字体时返回 None（仅画框不写字）。"""
    for cand in (r"C:\Windows\Fonts\msyh.ttc",
                 r"C:\Windows\Fonts\msyhbd.ttc",
                 r"C:\Windows\Fonts\simhei.ttf",
                 r"C:\Windows\Fonts\simsun.ttc",
                 r"C:\Windows\Fonts\simfang.ttf"):
        if Path(cand).is_file():
            return cand
    return None


def _wrap_text(draw, text, font, max_w):
    lines, cur = [], ""
    for ch in text:
        if not cur or draw.textlength(cur + ch, font=font) <= max_w:
            cur += ch
        else:
            lines.append(cur)
            cur = ch
    if cur:
        lines.append(cur)
    return lines


def make_placeholder_png(ph_text, out_path=None, dpi=150):
    """生成灰底占位 PNG（尺寸=image_spec 目标口径，标签含占位文案+尺寸）。

    返回写入的 PNG 路径；out_path 缺省时写系统临时目录（按文案 hash 命名）。
    PIL 缺失时抛 ImportError（生成器依赖环境与 image_spec 一致）。
    """
    from PIL import Image, ImageDraw, ImageFont
    w_cm, h_cm = box_size_for(ph_text)
    W = max(40, int(round(w_cm * dpi / 2.54)))
    H = max(40, int(round(h_cm * dpi / 2.54)))
    img = Image.new("RGB", (W, H), "#f2f2f2")
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, W - 1, H - 1], outline="#808080", width=max(2, W // 300))

    fpath = _font_path()
    if fpath:
        try:
            # 估算行数后选字号，保证小框（身份证 5×8）不溢出
            approx = 1 + max(1, int(len(ph_text) * 40 / (W * 0.85))) + 2
            size = max(11, min(40, int(H * 0.92 / (approx * 1.35))))
            font = ImageFont.truetype(fpath, size)
            max_w = W * 0.88
            lines = ["此处将插入："] + _wrap_text(draw, ph_text, font, max_w) + \
                    ["尺寸：高%gcm × 宽%gcm（框内等比插入真实图）" % (h_cm, w_cm)]
            lh = int(size * 1.35)
            y = max(6, (H - lh * len(lines)) // 2)
            for ln in lines:
                tw = draw.textlength(ln, font=font)
                draw.text(((W - tw) / 2, y), ln, fill="#333333", font=font)
                y += lh
        except Exception:
            pass                       # 画字失败不阻断（仅留灰框）

    if out_path is None:
        h = hashlib.sha1(ph_text.encode("utf-8")).hexdigest()[:12]
        out_path = os.path.join(tempfile.gettempdir(), "bidcraft_ph_%s.png" % h)
    img.save(out_path)
    return str(out_path)
