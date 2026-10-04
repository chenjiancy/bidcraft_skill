# -*- coding: utf-8 -*-
"""⑦ filler 拆包 · 图片插入与图片占位填充（含预览框移除、白名单组合）。"""
from pathlib import Path

from m5_project import image_spec as imgsp

from .fill_common import Cm
from .fill_combo import _build_combo, _build_whitelist
from .fill_text import _para_full_text, _set_para_text

__all__ = [
    "FILL_IMG_MAP", "_insert_image", "_insert_images_before", "_docpr_descrs",
    "_remove_ph_preview_by_marker", "_fill_image_placeholders", "_fill_cell_image",
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
    "【图片：总监高级工程师职称证书】": (None, "总监高级工程师职称证书", "陈云职称证书"),
    "【图片：其他监理人员职称证书】": (None, "其他监理人员职称证书", "陈友龙/吴志水/裴友谊/阮旭/黄诚"),
    "【图片：先进（优秀）监理企业证书】": (None, "先进优秀监理企业证书", "荣誉（2张）"),
    "【图片：监理示范（优质）工程】": (None, "监理示范优质工程", "荣誉（2张）"),
    "【图片：法定代表人身份证正、反面扫描件】": (None, "身份证", "法代身份证待提供"),
    "【图片：委托代理人身份证正、反面扫描件】": (None, "身份证", "代理人身份证待提供"),
    "【图片：基本账户开户许可证（或基本账户存款信息）扫描件】":
        ("财务/财务证照/开户许可证_长期.png", "开户许可证扫描件", "财务证照；存款信息图待提供"),
}


def _insert_image(p, img_path, w_cm, h_cm):
    """段落 p：清文本后新增 run 插入图片（宽高 Cm）。"""
    _set_para_text(p, "")
    run = p.add_run()
    run.add_picture(str(img_path), width=Cm(w_cm), height=Cm(h_cm))


def _insert_images_before(doc, para, items):
    """在占位段前插入（分页段+居中图片段）；返回插入图片数。"""
    from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
    from docx.shared import Cm as _Cm
    tmp = []
    for path, skey, pb in items:
        size = imgsp.fit_size(path, skey)
        if not size:
            continue
        w, h = size
        if pb:
            p = doc.add_paragraph()
            p.add_run().add_break(WD_BREAK.PAGE)
            tmp.append(p)
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.add_run().add_picture(path, width=_Cm(w), height=_Cm(h))
        tmp.append(p)
    for p in reversed(tmp):
        para._p.addprevious(p._p)
    return len(items)


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
    """表格单元格内图片占位：首段落插图。"""
    p = cell.paragraphs[0] if cell.paragraphs else cell.add_paragraph()
    _set_para_text(p, "")
    _insert_image(p, img_path, w_cm, h_cm)
