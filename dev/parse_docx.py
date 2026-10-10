# -*- coding: utf-8 -*-
"""解析投标文件 docx：按 body 顺序输出 段落文本/表格/图片 结构与格式摘要。"""
import sys, re, json
from pathlib import Path
from docx import Document
from docx.oxml.ns import qn

RNS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

def para_style(p):
    pf = p.paragraph_format
    sz = None; font = None; bold = None
    for r in p.runs:
        if r.font.size:
            sz = r.font.size.pt
        if r.font.name:
            font = r.font.name
        bold = r.font.bold
        if sz and font and bold is not None:
            break
    align = pf.alignment
    ls = pf.line_spacing
    return {"字体": font, "字号": sz, "加粗": bold, "对齐": str(align) if align else None,
            "行距": ls, "缩进": pf.first_line_indent}

def has_image(el):
    return len(list(el.iter(qn("w:drawing")))) + len(list(el.iter(qn("w:pict")))) > 0

def cell_text(tc):
    return "".join(t.text or "" for t in tc.iter(qn("w:t")))

def parse(docx_path, max_paras=99999):
    doc = Document(str(docx_path))
    out = []
    idx = 0
    for child in doc.element.body.iterchildren():
        if child.tag == qn("w:p"):
            from docx.text.paragraph import Paragraph
            p = Paragraph(child, doc)
            t = p.text.strip()
            imgs = has_image(child)
            sty = para_style(p)
            if t or imgs:
                out.append({"#": idx, "类型": "段", "文本": t[:60], "图片": imgs, "样式": sty})
            idx += 1
        elif child.tag == qn("w:tbl"):
            from docx.table import Table
            tbl = Table(child, doc)
            rows = []
            for r in tbl.rows[:4]:
                cells = []
                seen = set()
                for c in r.cells:
                    if id(c._tc) not in seen:
                        seen.add(id(c._tc))
                        cells.append(cell_text(c._tc)[:20])
                rows.append(cells)
            n_img = len(list(child.iter(qn("w:drawing")))) + len(list(child.iter(qn("w:pict"))))
            out.append({"#": idx, "类型": "表", "行数": len(tbl.rows), "列数": len(tbl.columns),
                        "首4行": rows, "含图": n_img})
            idx += 1
    return out

if __name__ == "__main__":
    p = sys.argv[1]
    data = parse(p)
    print("==== %s（%d 个块）====" % (Path(p).name, len(data)))
    for b in data:
        if b["类型"] == "段":
            img = "🖼" if b["图片"] else "  "
            print("%s[%03d] %-46s %s" % (img, b["#"], b["文本"][:46], b["样式"]))
        else:
            print("  [%03d] ▦表 %d行×%d列 含图%d 首行%s" % (b["#"], b["行数"], b["列数"], b["含图"], b["首4行"][0] if b["首4行"] else ""))
