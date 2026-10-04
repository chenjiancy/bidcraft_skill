# -*- coding: utf-8 -*-
"""⑨ docxtpl 对比评估 · 构建实验模板（模拟「招标原文范本 + 循环行简历表」场景）。

生成两份模板：
  tpl_self.docx      —— 自研路线：原文即模板，含【xxx】占位；跨 run 拆分【项目名称】；
                        表格 1 行范本（渲染时复制为 N 行）。
  tpl_docxtpl.docx   —— docxtpl 路线：同一原文结构，注入 Jinja 标签
                        {{ project_name }} / {%tr %} 循环（模板作者改造一步）。

用 python-docx 构造（不依赖 docxtpl 渲染器，仅用它跑渲染）。
"""
from pathlib import Path
from docx import Document
from docx.shared import Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

OUT = Path(__file__).resolve().parent


def _run(para, text, bold=False, font="宋体", size=12):
    r = para.add_run(text)
    r.bold = bold
    r.font.name = font
    r.font.size = Pt(size)
    r._element.rPr.rFonts.set(qn("w:eastAsia"), font)
    return r


def _set_cell_borders(tbl):
    tblPr = tbl._tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement("w:%s" % edge)
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), "6")
        borders.append(el)
    tblPr.append(borders)


def build_original(path):
    """原文范本：标题 + 跨 run 占位段 + 表头 + 1 行范本行 + 尾部固定段。"""
    doc = Document()
    h = doc.add_paragraph()
    h.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _run(h, "第一章 投标文件格式", bold=True, font="黑体", size=16)

    p = doc.add_paragraph()
    # 跨 run 拆分：【项目名称】拆成两段 run（真实 Word 常见），测试跨 run 替换
    _run(p, "项目名称：")
    r1 = p.add_run("【项目名")
    r1.font.name = "宋体"
    r1.font.size = Pt(12)
    r2 = p.add_run("称】")
    r2.font.name = "宋体"
    r2.font.size = Pt(12)

    tbl = doc.add_table(rows=2, cols=3)
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    _set_cell_borders(tbl)
    heads = ("姓名", "出生年月", "备注")
    for c, t in enumerate(heads):
        _run(tbl.rows[0].cells[c].paragraphs[0], t, bold=True)
    # 范本行（1 行 → 渲染复制 3 行）
    _run(tbl.rows[1].cells[0].paragraphs[0], "【姓名】")
    _run(tbl.rows[1].cells[1].paragraphs[0], "【出生年月】")
    _run(tbl.rows[1].cells[2].paragraphs[0], "【备注】")

    tail = doc.add_paragraph()
    _run(tail, "（盖章）")
    doc.save(str(path))
    return str(path)


def inject_jinja(src, dst):
    """把原文范本改造成 docxtpl 模板（模拟模板作者手工注入标签）。

    docxtpl 0.20.2 行循环真实语义（实测源码 patch_xml：`{%y %}` 所在
    <w:y> 整段被剥掉、仅提取标签）：
      {%tr for %} 独占一行（不渲染）→ 循环体行（变量，复制 N 次）→
      {%tr endfor %} 独占一行（不渲染）。
    """
    import copy
    doc = Document(src)
    for p in doc.paragraphs:
        full = "".join(r.text for r in p.runs)
        if "【项目名称】" in full:
            p.runs[1].text = ""
            p.runs[2].text = "{{ project_name }}"
    tbl = doc.tables[0]
    # 1) 范本行（变量行）：首格第一段放 {%tr for %} 标签（该行即循环起始标记行，
    #    标签独占此行，行内其余留空）
    tmpl_row = tbl.rows[1]
    for ci, key in enumerate(("姓名", "出生年月", "备注")):
        _set_cell_var(tmpl_row.cells[ci], "{{ row.%s }}" % key)
    # 2) 在范本行前插入独立的 {%tr for %} 标签行（整行剥掉，仅提取标签）
    for_tr = copy.deepcopy(tmpl_row._tr)
    tmpl_row._tr.addprevious(for_tr)
    _fill_row_tags(tbl, for_tr, "{%tr for row in rows %}")
    # 3) 表尾追加 {%tr endfor %} 标签行（deepcopy 确保 w:t 结构存在）
    end_tr = copy.deepcopy(tmpl_row._tr)
    tmpl_row._tr.addnext(end_tr)
    _fill_row_tags(tbl, end_tr, "{%tr endfor %}")
    doc.save(str(dst))
    return str(dst)


def _fill_row_tags(tbl, tr_el, tag_text):
    """把 tr XML 内所有 w:t 清空，仅第一个 w:t 写 tag_text。"""
    from docx.oxml.ns import qn
    ts = tr_el.findall(".//" + qn("w:t"))
    for i, t in enumerate(ts):
        t.text = tag_text if i == 0 else ""


def _set_cell_var(cell, text):
    p = cell.paragraphs[0]
    for r in list(p.runs):
        r.text = ""
    p.add_run(text)


if __name__ == "__main__":
    s = build_original(OUT / "tpl_self.docx")
    d = inject_jinja(s, OUT / "tpl_docxtpl.docx")
    print("templates:", s, d)
