# -*- coding: utf-8 -*-
"""⑦ generator 拆包 · 文本/占位符处理（docx 段落级）。

全部委托 _shared.docx_util（跨 run 安全）；规则表常量在 gen_common。
"""
import copy
import re

from _shared import docx_util as _docx_util
from .gen_common import (GLOBAL_PH, ROW_RULES, SME_SAMPLE, TAG_NOISE)  # noqa: F401

__all__ = [
    "set_cell_text", "_replace_text_in_runs", "_set_para_text", "_para_text",
    "_clean_tag", "_apply_global_ph", "_strip_shading_and_highlight",
    "_remove_stray_star", "_apply_file_font", "_apply_row_rules",
    "_apply_para_label_rules", "_apply_date_ph", "_fix_cover_title",
    "_split_authorize_info", "_apply_f13_sme",
]


def set_cell_text(cell, text):
    """清空单元格并写入文本（保留首个 run 的 rPr 与段落 pPr）。委托 _shared.docx_util。"""
    return _docx_util.set_cell_text(cell, text)


def _replace_text_in_runs(p, old, new):
    """段落文本级替换（保留首 run rPr 与段落 pPr；占位词跨 run 也能命中）。委托公共工具。"""
    return _docx_util.replace_in_para(p, old, new) > 0


def _set_para_text(p, text):
    """段落整段写文本（保留首 run rPr 与段落 pPr）。委托公共工具。"""
    return _docx_util.set_para_text(p, text)


def _para_text(node):
    return _docx_util.para_text(node)


def _clean_tag(tag):
    t = tag
    for ch in TAG_NOISE:
        t = t.replace(ch, "")
    return t.strip()


def _apply_global_ph(doc):
    n = 0
    for p in doc.paragraphs:
        for old, new in GLOBAL_PH:
            if _replace_text_in_runs(p, old, new):
                n += 1
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                t = cell.text
                for old, new in GLOBAL_PH:
                    if old in t:
                        set_cell_text(cell, t.replace(old, new))
                        n += 1
    return n


def _strip_shading_and_highlight(doc):
    """去除文字底纹：段落级（pPr/w:shd）与 run 级（rPr/w:shd + rPr/w:highlight）。
    表格/单元格底纹（tcPr/tblPr）属表格样式，保留。
    注意：iter() 遍历中直接删除会跳过未访问节点 → 先收集、后删除。"""
    from .gen_common import qn
    targets = []
    for node in doc.element.body.iter():
        if node.tag in (qn("w:pPr"), qn("w:rPr")):
            for child in list(node):
                if child.tag in (qn("w:shd"), qn("w:highlight")):
                    targets.append(child)
    for child in targets:
        child.getparent().remove(child)
    return len(targets)


def _remove_stray_star(doc):
    """范本 v1.1：删除孤立「*」段落（招标文件格式残留，用户范本已删；如承诺函末尾）。"""
    n = 0
    for p in doc.paragraphs:
        if "".join(r.text for r in p.runs).strip() == "*":
            p._p.getparent().remove(p._p)
            n += 1
    return n


def _apply_file_font(doc, font):
    """统一文件字体（与模板库基础模板一致）：遍历 run 与段落标记（pPr/rPr）
    设置 rFonts ascii/hAnsi/eastAsia。先收集、后修改（避免 iter 修改问题）。"""
    from .gen_common import qn
    n = 0
    targets = []

    def collect(rpr):
        rf = rpr.find(qn("w:rFonts"))
        if rf is None:
            rf = rpr.makeelement(qn("w:rFonts"), {})
            rpr.insert(0, rf)
        rf.set(qn("w:ascii"), font)
        rf.set(qn("w:hAnsi"), font)
        rf.set(qn("w:eastAsia"), font)
        return 1

    for r in doc.element.body.iter(qn("w:r")):
        rPr = r.find(qn("w:rPr"))
        if rPr is None:
            rPr = r.makeelement(qn("w:rPr"), {})
            r.insert(0, rPr)
        n += collect(rPr)
    for ppr in doc.element.body.iter(qn("w:pPr")):
        rpr = ppr.find(qn("w:rPr"))
        if rpr is not None:
            n += collect(rpr)
    return n


def _apply_row_rules(doc, ctx_map):
    n = 0
    for table in doc.tables:
        ctx = ctx_map.get(table._tbl, "")
        rules = None
        for kw, rr in ROW_RULES.items():
            if kw in ctx:
                rules = rr
                break
        if not rules:
            continue
        for row in table.rows:
            cells = row.cells
            if not cells:
                continue
            # 标签 = 第一个非纯数字的非空格（兼容 序号|项目|内容 型表）
            tag = next((c.text.strip() for c in cells
                        if c.text.strip() and not c.text.strip().isdigit()), "")
            subs = rules.get(tag)
            if not subs:
                continue
            for c in cells[1:]:
                newtext = c.text
                changed = False
                for pattern, repl in subs:
                    if re.search(pattern, newtext):
                        newtext = re.sub(pattern, repl, newtext)
                        changed = True
                if changed:
                    set_cell_text(c, newtext)
                    n += 1
    return n


def _apply_para_label_rules(doc, rules):
    """段落标签填充（参照模板库）：『标签：空格』行在空格区填【键】。"""
    n = 0
    for p in doc.paragraphs:
        full = "".join(r.text for r in p.runs)
        newtext = full
        for pattern, repl in rules:
            if re.search(pattern, newtext):
                newtext = re.sub(pattern, repl, newtext)
        if newtext != full:
            _set_para_text(p, newtext)
            n += 1
    return n


def _apply_date_ph(doc, enabled):
    """落款日期行『年 月 日』→ 整段替换【日期】（参照模板库）。"""
    if not enabled:
        return 0
    pat = re.compile(r"^\s*(?:20\d{2}\s*)?年\s+月\s+日\s*$")
    n = 0
    for p in doc.paragraphs:
        full = "".join(r.text for r in p.runs)
        if pat.match(full):
            _set_para_text(p, "【日期】")
            n += 1
    return n


def _fix_cover_title(doc):
    """封面标题（范本 v1.1）：招标文件首行「监理（项目名称）」→ 两行【项目名称】+【项目编号】。
    调用时机在 _apply_global_ph 之后（此时首行已是「监理【项目名称】」）。"""
    n = 0
    paras = doc.paragraphs
    for i, p in enumerate(paras):
        full = "".join(r.text for r in p.runs).strip()
        if "监理" in full and "【项目名称】" in full:
            _set_para_text(p, "【项目名称】")
            new_p = copy.deepcopy(p._p)
            p._p.addnext(new_p)
            # 新增段紧跟原段之后（原段在 body 中位置不变）→ 重新取列表，i+1 即新段
            _set_para_text(doc.paragraphs[i + 1], "【项目编号】")
            n += 1
            break
    return n


def _split_authorize_info(doc):
    """授权委托书（范本 v1.1）：正文「授权代理人：___性别：___」「年龄：___职务：___」两行
    各自拆为独立行并填占位（授权代理人：【授权代理人姓名】/性别：【性别】/年龄：【年龄】/职务：【职务】）。
    落款「授权代理人：（签字或盖章）」仅含单个标签，不受影响。"""
    from .gen_common import qn
    n = 0
    labels = [("授权代理人：", "【授权代理人姓名】"),
              ("性别：", "【性别】"),
              ("年龄：", "【年龄】"),
              ("职务：", "【职务】")]
    paras = doc.paragraphs
    for p in paras:
        full = "".join(r.text for r in p.runs)
        present = [lab for lab, _ in labels if lab in full]
        if len(present) < 2:
            continue
        # 行内存在 ≥2 个标签 → 按标签顺序拆为独立行（取标签后到下一标签前的片段）
        segs = []
        for j, (lab, ph) in enumerate(labels):
            if lab not in full:
                continue
            start = full.find(lab) + len(lab)
            end = len(full)
            for lab2, _ in labels[j + 1:]:
                pos = full.find(lab2, start)
                if pos >= 0:
                    end = min(end, pos)
            segs.append((lab, ph))
        # 首段复用原段，其余 addnext（复制 pPr 保持格式）；addnext 会改变后续段位置，
        # 且 body 可能含 bookmark 等非段落元素，故用 w:p 元素计数实时定位新段
        anchor = p._p
        for i, (lab, ph) in enumerate(segs):
            if i == 0:
                _set_para_text(p, "%s%s" % (lab, ph))
            else:
                new_p = copy.deepcopy(anchor)
                anchor.addnext(new_p)
                anchor = new_p
                i0 = 0
                for el in doc.element.body.iterchildren():
                    if el is p._p:
                        break
                    if el.tag == qn("w:p"):
                        i0 += 1
                _set_para_text(doc.paragraphs[i0 + i], "%s%s" % (lab, ph))
        n += 1
    return n


def _apply_f13_sme(doc, project_name):
    """中小企业声明函（范本 v1.1）：原文具体项目名 → 【项目名称】；【项目编号】；
    从业人员/营业收入/资产总额/企业类型 → SME_SAMPLE 默认示例值（模板库范本保留值）。
    原文为固定招标条款，其余一字不改。"""
    if not project_name:
        return 0
    n = 0
    for p in doc.paragraphs:
        full = "".join(r.text for r in p.runs)
        newtext = full
        if project_name in newtext:
            newtext = newtext.replace(project_name, "【项目名称】")
        for old, new in (
            (r"（项目编号：\s*）", "（项目编号：【项目编号】）"),
            (r"从业人员\s*人", "从业人员 %s 人" % SME_SAMPLE["从业人员"]),
            (r"营业收入为\s*万元", "营业收入为 %s 万元" % SME_SAMPLE["营业收入"]),
            (r"资产总额为\s*万元", "资产总额为 %s 万元" % SME_SAMPLE["资产总额"]),
            (r"属于（中型企业、小型企业、微型企业）", "属于%s" % SME_SAMPLE["企业类型"]),
        ):
            if re.search(old, newtext):
                newtext = re.sub(old, new, newtext)
        if newtext != full:
            _set_para_text(p, newtext)
            n += 1
    return n
