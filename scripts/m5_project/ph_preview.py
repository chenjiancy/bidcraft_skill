# -*- coding: utf-8 -*-
"""
M5 图片占位预览框（v2.0，2026-10-04 用户确认升级）。

目标：让 Word 模板直接可见「图片将来放哪、多大、放什么」——
生成器在每个【图片：xxx】占位段后插入一张真实尺寸的占位图
（尺寸与 image_spec 目标口径一致），框内：
  - 有素材（assets 非空）：直接绘制**将填充的真实素材缩略图**（等比 contain，
    多张上下排列），底部标注「填充素材：<文件名…>（N张）｜高Xcm×宽Ycm」；
  - 无素材（assets 空/全失败）：灰底 + 「【待补素材】<占位文案>」+ 尺寸，
    人工一看便知缺什么。
填充引擎生成商务标时定位该框（docPr@descr 标记 IMG_PH:<占位文案>）
并删除，再按同口径插入真实图。

只做确定性绘图，无业务判断；PIL 为运行依赖（image_spec.fit_size 已用）。
assets 形如 [(素材绝对路径, 口径key, 是否换页), ...]，与 fill_combo._build_combo
返回的 items 同构（生成器解析素材清单后传入）。
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


def _fit_thumb(w, h, max_w, max_h):
    """等比 contain：返回 (w, h) 不超出 max_w/max_h。"""
    scale = min(max_w / w, max_h / h)
    return int(w * scale), int(h * scale)


def _draw_asset_thumbs(img, draw, assets, pad, label_h):
    """在框内上方区域绘制素材缩略图；返回 (成功数, 失败数)。"""
    from PIL import Image
    W, H = img.size
    avail_w = W - 2 * pad
    avail_h = H - label_h - 2 * pad
    if avail_w < 20 or avail_h < 20:
        return 0, len(assets)
    # 第一遍：按 avail 上限等比算每张尺寸
    thumbs, failed = [], 0
    for apath, _skey, _np in assets:
        try:
            with Image.open(apath) as im:
                iw, ih = im.size
            if iw <= 0 or ih <= 0:
                raise ValueError("bad size")
            w, h = _fit_thumb(iw, ih, avail_w, avail_h)
            thumbs.append((apath, max(1, w), max(1, h)))
        except Exception:
            failed += 1
    if not thumbs:
        return 0, failed
    gap = max(2, int(avail_h * 0.03))
    total_h = sum(h for _, _, h in thumbs) + gap * (len(thumbs) - 1)
    if total_h > avail_h:                       # 总高超限 → 整体等比再缩
        k = avail_h / total_h
        thumbs = [(p, max(1, int(w * k)), max(1, int(h * k))) for p, w, h in thumbs]
    y = pad
    draw_ok = 0
    for apath, w, h in thumbs:
        try:
            with Image.open(apath) as im:
                im = im.convert("RGB")
                _RS = getattr(Image, "Resampling", Image)
                im = im.resize((w, h), _RS.LANCZOS)
            img.paste(im, (pad, y))
            draw_ok += 1
        except Exception:
            failed += 1
        y += h + gap
    return draw_ok, failed


def _draw_label(draw, img, label, pad, label_h):
    """框底部绘制标注条（白底深字，超宽自动换行）。"""
    from PIL import ImageFont
    W, H = img.size
    draw.rectangle([0, H - label_h, W - 1, H - 1], fill="#ffffff")
    fpath = _font_path()
    if not fpath:
        return
    try:
        size = max(11, min(30, int(label_h / 2.6)))
        font = ImageFont.truetype(fpath, size)
        max_w = W - 2 * pad
        lines = _wrap_text(draw, label, font, max_w)
        if len(lines) > 2:                      # 超两行 → 截断
            lines = lines[:2]
            lines[-1] = lines[-1][:int(max_w / (size * 0.5))] + "…"
        lh = int(size * 1.3)
        y = H - label_h + max(2, (label_h - lh * len(lines)) // 2)
        for ln in lines:
            tw = draw.textlength(ln, font=font)
            draw.text((max(2, (W - tw) / 2), y), ln, fill="#222222", font=font)
            y += lh
    except Exception:
        pass


def make_placeholder_png(ph_text, assets=None, out_path=None, dpi=150):
    """生成占位 PNG（尺寸=image_spec 目标口径）。

    assets=None → 灰底 + 【待补素材】+ 尺寸（人工可见缺什么）；
    assets 非空 → 真实素材缩略图 + 底部标注「填充素材：<文件名>（N张）｜高Xcm×宽Ycm」。
    返回写入的 PNG 路径；out_path 缺省时写系统临时目录（按文案 hash 命名）。
    """
    from PIL import Image, ImageDraw
    w_cm, h_cm = box_size_for(ph_text)
    W = max(40, int(round(w_cm * dpi / 2.54)))
    H = max(40, int(round(h_cm * dpi / 2.54)))
    img = Image.new("RGB", (W, H), "#f2f2f2")
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, W - 1, H - 1], outline="#808080", width=max(2, W // 300))

    pad = max(6, W // 60)
    if assets:
        label_h = max(26, int(H * 0.16))
        draw_ok, failed = _draw_asset_thumbs(img, draw, assets, pad, label_h)
        names = [Path(a[0]).name for a in assets]
        if draw_ok:
            label = "填充素材：" + "、".join(names)
            if len(label) > 90:
                label = label[:90] + "…"
            label += "（%d张）｜高%gcm×宽%gcm" % (draw_ok, h_cm, w_cm)
        else:
            label = "【待补素材】%s｜高%gcm×宽%gcm" % (ph_text, h_cm, w_cm)
        if failed:
            label += "｜%d张读取失败" % failed
        _draw_label(draw, img, label, pad, label_h)
    else:
        fpath = _font_path()
        if fpath:
            try:
                lines = ["【待补素材】%s" % ph_text,
                         "尺寸：高%gcm × 宽%gcm（框内等比插入真实图）" % (h_cm, w_cm)]
                approx = len(lines)
                size = max(11, min(40, int(H * 0.9 / (approx * 1.4))))
                from PIL import ImageFont
                font = ImageFont.truetype(fpath, size)
                max_w = W * 0.9
                full = ["【待补素材】"] + _wrap_text(draw, ph_text, font, max_w) + \
                       ["尺寸：高%gcm × 宽%gcm（框内等比插入真实图）" % (h_cm, w_cm)]
                lh = int(size * 1.35)
                y = max(6, (H - lh * len(full)) // 2)
                for ln in full:
                    tw = draw.textlength(ln, font=font)
                    draw.text(((W - tw) / 2, y), ln, fill="#333333", font=font)
                    y += lh
            except Exception:
                pass                       # 画字失败不阻断（仅留灰框）

    if out_path is None:
        h = hashlib.sha1((ph_text + "|" + str(assets or [])).encode("utf-8")).hexdigest()[:12]
        out_path = os.path.join(tempfile.gettempdir(), "bidcraft_ph_%s.png" % h)
    img.save(out_path)
    return str(out_path)
