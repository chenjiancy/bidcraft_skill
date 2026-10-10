# -*- coding: utf-8 -*-
"""递归定位投标文件目录下所有 word 文件并解析 docx 结构。"""
import sys, os, re, json
from pathlib import Path
from docx import Document
from docx.oxml.ns import qn

def find_words(root):
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        for f in filenames:
            if f.lower().endswith((".doc", ".docx")) and "~$" not in f:
                out.append(os.path.join(dirpath, f))
    return out

def para_style(p):
    pf = p.paragraph_format
    sz = font = bold = None
    for r in p.runs:
        if r.font.size: sz = r.font.size.pt
        if r.font.name: font = r.font.name
        if r.font.bold is not None: bold = r.font.bold
        if sz and font and bold is not None: break
    return {"字体": font, "字号": sz, "加粗": bold, "对齐": str(pf.alignment) if pf.alignment else None,
            "行距": pf.line_spacing, "缩进": pf.first_line_indent}

def cell_text(tc):
    return "".join(t.text or "" for t in tc.iter(qn("w:t")))

def parse(docx_path, cap=400):
    doc = Document(str(docx_path))
    out = []
    for child in doc.element.body.iterchildren():
        if len(out) >= cap: break
        if child.tag == qn("w:p"):
            from docx.text.paragraph import Paragraph
            p = Paragraph(child, doc)
            t = p.text.strip()
            imgs = len(list(child.iter(qn("w:drawing")))) + len(list(child.iter(qn("w:pict"))))
            if t or imgs:
                out.append({"类型": "段", "文本": t[:50], "图": imgs, "样式": para_style(p)})
        elif child.tag == qn("w:tbl"):
            from docx.table import Table
            tbl = Table(child, doc)
            n_img = len(list(child.iter(qn("w:drawing")))) + len(list(child.iter(qn("w:pict"))))
            head = []
            if tbl.rows:
                seen = set()
                for c in tbl.rows[0].cells:
                    if id(c._tc) not in seen:
                        seen.add(id(c._tc)); head.append(cell_text(c._tc)[:15])
            out.append({"类型": "表", "行": len(tbl.rows), "列": len(tbl.columns),
                        "图": n_img, "表头": head})
    return out

if __name__ == "__main__":
    targets = [
        (r"E:\天翼同步盘\投标文件\2026年\和县中医院医养结合一体化建设项目工程监理服务", "资质证书文件"),
        (r"E:\天翼同步盘\投标文件\2026年\和县2026年老旧小区改造项目（EPC总承包）监理采购", "和县2026"),
        (r"E:\天翼同步盘\投标文件\2025年\南京江北新区智能制造产业园和县分园产业孵化器南区项目监理", "南京江北"),
    ]
    # 只输出含"资质/证书/重要资料/法代/授权/承诺"关键词的 docx
    for root, tag in targets:
        print("\n######## %s ########" % tag)
        for f in find_words(root):
            base = os.path.basename(f)
            if not any(k in base for k in ("资质", "证书", "重要资料", "法代", "授权", "承诺", "身份证明")):
                continue
            if base.lower().endswith(".doc"):
                print("  [doc 跳过] %s" % base)
                continue
            print("\n==== %s ====" % base)
            try:
                for b in parse(f):
                    if b["类型"] == "段":
                        print("%s[%s] %-50s %s" % ("🖼" if b["图"] else "  ", b["样式"]["字号"], b["文本"][:50], b["样式"]["字体"]))
                    else:
                        print("  ▦表%d行×%d列 图%d 表头%s" % (b["行"], b["列"], b["图"], b["表头"]))
            except Exception as e:
                print("  解析失败: %s" % e)
