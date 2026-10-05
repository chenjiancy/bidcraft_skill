# -*- coding: utf-8 -*-
"""⑦ filler 拆包 · 图片插入与图片占位填充（含预览框移除、白名单组合）。

v2.1（2026-10-04 按成品标书，两轮实测修正）：
  - 尺寸：统一等比（宽=可用宽16、高按原图；身份证固定框 8×5）；
  - 插入：图片独立成段、内联（inline）——浮动 anchor 在 Word 下连续图
    重叠/乱页/空白页不可控（实测 p46 空白、顺序错乱），独立段内联图
    视觉同为「图独立成段、不挤占正文」，但顺序/分页由文档流天然保证；
  - 分页：需分页的图用段前分页（pageBreakBefore），无独立分页段（避免空页）。
"""
from pathlib import Path

from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls, qn

from m5_project import image_spec as imgsp

from .fill_common import Cm
from .fill_combo import _build_combo, _build_whitelist
from .fill_text import _para_full_text, _set_para_text

__all__ = [
    "FILL_IMG_MAP", "_insert_image", "_insert_images_before", "_docpr_descrs",
    "_remove_ph_preview_by_marker", "_fill_image_placeholders", "_fill_cell_image",
    "_to_floating_anchor",
]


# ---------------------------------------------------------------------------
# 图片占位 → 素材库图片（相对素材库根）映射；缺图（无文件）→ 缺图清单
# 值: (路径或 None=缺, 口径键, 说明)
# ---------------------------------------------------------------------------
FILL_IMG_MAP = {
    "【图片：组织机构框图（含结构、领导成员、主要技术人员、管理人员及数量）】":
        ("企业介绍/组织机构图_20261001.png", "组织机构框图", "企业介绍"),
    "【图片：企业基本账户开户许可证扫描件】":
        ("财务/财务证照/开户许可证_长期.png", "开户许可证扫描件", "财务证照"),
    "【图片：企业法人营业执照（副本）扫描件】":
        ("资质/营业执照_副本_长期.png", "营业执照扫描件", "资质"),
    "【图片：企业资质证书扫描件】": (None, "资质证书组", "甲级+乙级多张组合，v1.1 实现"),
    "【图片：拟派监理人员注册证书、岗位证书、职称、身份证等证明材料】":
        (None, "人员证书组", "6人证书组合插入，v1.1 实现"),
    "【图片：拟投入监理人员社保证明】": (None, "社保证明", "6人社保证明待出具"),
    "【图片：三体系认证证书】": (None, "三体系认证证书", "ISO9001/14001/45001 三张"),
    "【图片：总监高级工程师职称证书】": (None, "总监高级工程师职称证书", "张三职称证书"),
    "【图片：其他监理人员职称证书】": (None, "其他监理人员职称证书", "陈友龙/吴志水/裴友谊/赵六/黄诚"),
    "【图片：先进（优秀）监理企业证书】": (None, "先进优秀监理企业证书", "荣誉（2张）"),
    "【图片：监理示范（优质）工程】": (None, "监理示范优质工程", "荣誉（2张）"),
    "【图片：法定代表人身份证正、反面扫描件】": (None, "身份证_法代授权", "法代身份证（7.5×4.5 固定框，正反面并排）"),
    "【图片：委托代理人身份证正、反面扫描件】": (None, "身份证_法代授权", "代理人身份证（7.5×4.5 固定框，正反面并排）"),
    "【图片：基本账户开户许可证（或基本账户存款信息）扫描件】":
        ("财务/财务证照/开户许可证_长期.png", "开户许可证扫描件", "财务证照；存款信息图待提供"),
}


# 浮动图片 anchor 骨架（工具函数 _to_floating_anchor 用）：wrapNone、
# positionH(margin,left)、positionV(paragraph,posOffset)。extent/docPr/graphic
# 由 inline 复用（r:embed 不变），元素顺序符合 CT_Anchor。
_ANCHOR_TPL = (
    '<wp:anchor %s distT="0" distB="0" distL="114300" distR="114300" '
    'simplePos="0" relativeHeight="251709440" behindDoc="0" locked="0" '
    'layoutInCell="1" allowOverlap="1">'
    '<wp:simplePos x="0" y="0"/>'
    '<wp:positionH relativeFrom="margin"><wp:align>left</wp:align></wp:positionH>'
    '<wp:positionV relativeFrom="paragraph"><wp:posOffset>0</wp:posOffset></wp:positionV>'
    '<wp:effectExtent l="0" t="0" r="635" b="0"/>'
    '<wp:wrapNone/>'
    '<wp:cNvGraphicFramePr><a:graphicFrameLocks noChangeAspect="1"/></wp:cNvGraphicFramePr>'
    '</wp:anchor>' % nsdecls("wp", "a")
)


def _to_floating_anchor(drawing_el, pos_offset_emu=0):
    """把 w:drawing 内的 wp:inline 原位替换为 wp:anchor（照成品标书）。

    元素顺序按 OOXML CT_Anchor：simplePos, positionH, positionV, extent,
    effectExtent, wrapNone, docPr, cNvGraphicFramePr, graphic。
    保留同一 r:embed（不重建图片关系）；docPr 的 id/name 复用原值。
    当前主流程已不用（独立段内联图更稳），保留为工具函数。
    """
    inline = drawing_el.find(qn("wp:inline"))
    if inline is None:
        return drawing_el
    anchor = parse_xml(_ANCHOR_TPL)
    eff = anchor.find(qn("wp:effectExtent"))
    extent = inline.find(qn("wp:extent"))
    if extent is not None:
        anchor.insert(anchor.index(eff), extent)
    docpr = inline.find(qn("wp:docPr"))
    cnv = anchor.find(qn("wp:cNvGraphicFramePr"))
    if docpr is not None:
        anchor.insert(anchor.index(cnv), docpr)
    posv = anchor.find(qn("wp:positionV"))
    off = posv.find(qn("wp:posOffset"))
    if off is not None:
        off.set("val", str(int(pos_offset_emu)))
    graphic = inline.find(qn("a:graphic"))
    if graphic is not None:
        anchor.append(graphic)
    drawing_el.replace(inline, anchor)
    return drawing_el


def _insert_image(p, img_path, w_cm, h_cm, floating=True):
    """段落 p：清文本后新增 run 插入图片（宽高 Cm），图片独立成段（内联）。

    独立段内联图占文档流高度：顺序、分页、正文避让均由 Word 天然处理，
    不会出现浮动 anchor 的连续图重叠 / 空白页问题（实测 v2.0 浮动版 p46
    空白、证书顺序与页序不一致）。floating 参数保留以兼容调用方，已无行为差异。
    """
    _set_para_text(p, "")
    run = p.add_run()
    run.add_picture(str(img_path), width=Cm(w_cm), height=Cm(h_cm))
    return p


def _insert_images_before(doc, para, items):
    """在占位段前插入图片段（需分页图用「段前分页」，其余紧随）；返回插入图片数。

    图片独立成段（内联）：顺序 = items 顺序、分页 = pageBreakBefore，
    由文档流天然保证（浮动 anchor 实测有重叠/空白页/页序错乱问题）。
    """
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Cm as _Cm
    tmp = []
    for path, skey, pb in items:
        size = imgsp.fit_size(path, skey)
        if not size:
            continue
        w, h = size
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        if pb:
            p.paragraph_format.page_break_before = True
        run = p.add_run()
        run.add_picture(path, width=_Cm(w), height=_Cm(h))
        tmp.append(p)
    if not tmp:
        return 0
    for p in tmp:
        para._p.addprevious(p._p)
    return len(tmp)


def _docpr_descrs(p_el):
    """段落内所有图片的 wp:docPr@descr（用于定位预览框标记 IMG_PH:xxx）。"""
    out = []
    for el in p_el.iter():
        if el.tag.endswith("}docPr"):
            out.append(el.get("descr") or "")
    return out


def _remove_ph_preview_by_marker(doc, ph_text):
    """删除图片占位段对应的预览框段（docPr@descr == IMG_PH:<占位文案>）；返回删除数。"""
    from .ph_preview import PH_PREVIEW_PREFIX
    marker = PH_PREVIEW_PREFIX + ph_text
    n = 0
    for p in list(doc.paragraphs):
        if marker in _docpr_descrs(p._p):
            p._p.getparent().remove(p._p)
            n += 1
    return n


def _trim_empty_after(body, anchor_el):
    """删除 anchor_el 之后连续的「纯空段」（无文字/无图/无分页符/无段前分页）。

    项目模板在图片占位段后常留多个排版空段（实测社保证明后 26 个），
    图片组合分页插入后这些空段会堆积成整页空白 → 组合插入后清理，
    直到下一个有内容/分页标记的段或表格为止。
    """
    nxt = anchor_el.getnext()
    while nxt is not None and nxt.tag == qn("w:p"):
        has_txt = nxt.find(".//" + qn("w:t")) is not None
        has_img = nxt.find(".//" + qn("w:drawing")) is not None
        ppr = nxt.find(qn("w:pPr"))
        has_pbb = ppr is not None and ppr.find(qn("w:pageBreakBefore")) is not None
        has_br = nxt.find(qn("w:r")) is not None and \
            nxt.find(".//" + qn("w:br")) is not None
        if has_txt or has_img or has_pbb or has_br:
            break
        nxt2 = nxt.getnext()
        body.remove(nxt)
        nxt = nxt2


def _fill_image_placeholders(doc, lib_root, proj_dir, material, missing):
    """段落级【图片：xxx】：取图插入（按口径），删除占位段；缺图删除占位 + missing。
    返回 (移除的预览框数, 清单外素材相对路径列表)（③白名单：组合构建只允许清单素材）。"""
    from .ph_preview import PH_PREVIEW_PREFIX
    persons = material.get("personnel", []) or []
    whitelist = _build_whitelist(material)
    n_prev = 0
    outside = []
    for p in list(doc.paragraphs):
        t = _para_full_text(p).strip()
        if not (t.startswith("【图片：") and t.endswith("】")):
            continue
        n_prev += _remove_ph_preview_by_marker(doc, t)
        mapped = FILL_IMG_MAP.get(t)
        if not mapped:
            missing.append((t, "无填充规则"))
            p._p.getparent().remove(p._p)
            continue
        path, rule_key, note = mapped
        if path is None:
            # 组合占位 v1.3：按素材清单白名单 + 数据驱动构建（多页素材带 P0/P1 逐页插入）
            items, mis, out = _build_combo(t, lib_root, proj_dir, material, whitelist)
            outside += out
            if items:
                _insert_images_before(doc, p, items)
            _trim_empty_after(doc.element.body, p._p)
            for m in mis:
                missing.append((t, "缺：%s" % m))
            p._p.getparent().remove(p._p)
            continue
        full = Path(lib_root) / path
        if not full.is_file():
            missing.append((t, "素材库缺文件: %s" % path))
            p._p.getparent().remove(p._p)
            continue
        size = imgsp.fit_size(str(full), rule_key)
        if not size:
            missing.append((t, "口径键缺失: %s" % rule_key))
            p._p.getparent().remove(p._p)
            continue
        _insert_image(p, str(full), size[0], size[1])
    return n_prev, outside


def _fill_cell_image(cell, img_path, w_cm, h_cm):
    """表格单元格内图片占位：首段落插图（内联，表内排版）。"""
    p = cell.paragraphs[0] if cell.paragraphs else cell.add_paragraph()
    _set_para_text(p, "")
    _insert_image(p, img_path, w_cm, h_cm, floating=False)
