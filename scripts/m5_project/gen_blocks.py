# -*- coding: utf-8 -*-
"""⑦ generator 拆包 · 块抽取与单文件构建（build_docx）。"""
import copy

from .gen_common import (GenError, HAVE_DOCX, Document, qn)
from .gen_images import (_insert_image_ph_after_para, _insert_image_ph_after_table)
from .gen_tables import (_duplicate_tables_by_contract, _fill_equip_from_tpl,
                         _post_process_tables)
from .gen_text import (_apply_date_ph, _apply_f13_sme, _apply_file_font,
                       _apply_global_ph, _apply_para_label_rules, _apply_row_rules,
                       _fix_cover_title, _para_text, _remove_stray_star,
                       _split_authorize_info, _strip_shading_and_highlight)

__all__ = ["_extract_blocks", "_item_id_for_block", "_sanitize_copy", "build_docx"]

_RNS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def _item_id_for_block(i, items):
    for it in items:
        r = it.get("块范围") or []
        if len(r) == 2 and r[0] <= i <= r[1]:
            return it["id"]
    return None


def _extract_blocks(src_path):
    """从招标文件 docx 提取块序列（段落/表格元素引用 + 顺序索引）。"""
    if not HAVE_DOCX:
        raise GenError("生成器依赖 python-docx")
    doc = Document(src_path)
    blocks = []
    for child in doc.element.body.iterchildren():
        tag = child.tag
        if tag == qn("w:p"):
            blocks.append({"type": "para", "node": child})
        elif tag == qn("w:tbl"):
            blocks.append({"type": "table", "node": child})
    return blocks, doc


def _sanitize_copy(node):
    """深拷贝招标文件块后清理跨包引用，防止 Word 报「文件可能已经损坏」。

    招标原文存在两类跨包引用，深拷贝进新文档后在新 rels 中无对应 part，会形成悬空引用：
    A. 章节段落 w:pPr/w:sectPr 内的 <w:footerReference r:id=...> / headerReference
       （指向源文档 footer/header part，旧模板是人工用 Word 保存时被自动修复的）；
    B. 原文示例图（a:blip r:embed=... 指向源媒体，如身份证样例/委托书样例扫描件，
       商务标图片一律来自素材库占位，原文示例图不应进入模板）。
    处理：1) 移除 headerReference/footerReference；2) 移除 w:drawing/w:object/w:pict 示例图；
          3) 其余元素剥离 r:embed / r:id / r:link 属性（如超链接退化为纯文本）。
    """
    node = copy.deepcopy(node)
    for tag in (qn("w:headerReference"), qn("w:footerReference")):
        for el in node.iter(tag):
            parent = el.getparent()
            if parent is not None:
                parent.remove(el)
    for tag in (qn("w:drawing"), qn("w:object"), qn("w:pict")):
        for el in list(node.iter(tag)):
            parent = el.getparent()
            if parent is not None:
                parent.remove(el)
    for el in node.iter():
        for attr in ("{%s}embed" % _RNS, "{%s}id" % _RNS, "{%s}link" % _RNS):
            if attr in el.attrib:
                del el.attrib[attr]
    return node


def build_docx(blocks, span, items, out_path, material, font=None, rules=None, equip_rows=None,
               assets_map=None):
    """
    从招标文件原文块 [s,e] 深拷贝构建项目模板 docx：
      1) 段落/表格逐块深拷贝（文字 100% 契约）；
      2) 契约项驱动的份数复制（附表3/附表8 动态语义②，简历表份数按监理人员配置口径）；
      3) 段落级全局占位 + 范本专属处理（封面标题/授权拆行/中小企业声明函示例值）
         + 段落标签填充 + 落款日期 + 行路由 + 列表/标签值型占位（占位键名参照模板库登记清单）；
      4) 图片占位【图片：xxx】（表格后/锚点段后，模板库同款带边框样式）；
         assets_map {占位文案: [(素材绝对路径, 口径key, 换页), ...]} → 预览框 v2
         直接绘制将填充的真实素材缩略图（素材清单白名单解析，见 gen_main.generate）；
      5) 附表9 仪器设备表：数据行替换为模板库范本数据行（企业固定设备，equip_rows）；
      6) 后处理：去除文字底纹/高亮 + 统一文件字体（与模板库基础模板一致）。
    返回 {"占位符数", "段落占位", "表格占位", "图片占位", "去底纹", "统一字体"}。
    """
    if not HAVE_DOCX:
        raise GenError("生成器依赖 python-docx，当前环境未安装")
    doc = Document()
    s, e = span
    rules = rules or {}
    ctx_map = {}                       # 表格节点 → 表格前最近非空段落文本
    tbl_meta = []                      # [(表格节点, 契约项id)] 用于份数复制
    last_para = ""
    for i in range(s, e + 1):
        blk = blocks[i]
        if blk["type"] == "para":
            t = _para_text(blk["node"]).strip()
            if t:
                last_para = t
            doc.element.body.append(_sanitize_copy(blk["node"]))
        else:
            new_node = _sanitize_copy(blk["node"])
            ctx_map[new_node] = last_para
            tbl_meta.append((new_node, _item_id_for_block(i, items)))
            doc.element.body.append(new_node)
    _duplicate_tables_by_contract(doc, tbl_meta, material, ctx_map)
    ph_para = _apply_global_ph(doc)
    if rules.get("cover_title"):
        ph_para += _fix_cover_title(doc)
    if rules.get("split_authorize"):
        ph_para += _split_authorize_info(doc)
    ph_para += _apply_para_label_rules(doc, rules.get("para_label", []))
    ph_para += _apply_date_ph(doc, rules.get("date_ph", False))
    if rules.get("sme_project"):
        ph_para += _apply_f13_sme(doc, str(material.get("project", "") or ""))
    ph_row = _apply_row_rules(doc, ctx_map)
    tbl_stats = _post_process_tables(doc, material, ctx_map)
    n_equip = _fill_equip_from_tpl(doc, ctx_map, equip_rows or []) if rules.get("equip_tpl") else 0
    n_star = _remove_stray_star(doc)
    n_shade = _strip_shading_and_highlight(doc)
    n_font = _apply_file_font(doc, font) if font else 0
    n_img, n_prev = _insert_image_ph_after_table(doc, ctx_map, rules.get("img_after_table", []), font or "宋体", assets_map)
    n_img2, n_prev2 = _insert_image_ph_after_para(doc, rules.get("img_after_para", []), font or "宋体", assets_map)
    n_img += n_img2
    n_prev += n_prev2
    # 规范化 body：w:sectPr 必须是 body 最后一个子元素。
    # python-docx 1.2.0 空 Document() 的 body 仅含 sectPr，正文 append 后会跑到内容前，
    # Word 打开会报「文件可能已经损坏」；保存前移回末尾（旧模板经 Word 修订保存时被自动修复）。
    body_el = doc.element.body
    sp_el = body_el.find(qn("w:sectPr"))
    if sp_el is not None:
        body_el.remove(sp_el)
        body_el.append(sp_el)
    doc.save(out_path)
    total = ph_para + ph_row + sum(tbl_stats.values()) + n_img
    info = {"占位符数": total, "段落占位": ph_para, "表格占位": ph_row + sum(tbl_stats.values()),
            "图片占位": n_img, "图片占位框": n_prev}
    if n_equip:
        info["附表9设备数据行"] = n_equip
    if n_shade:
        info["去底纹"] = n_shade
    if n_font:
        info["统一字体"] = font
    return info
