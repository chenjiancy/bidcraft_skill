# -*- coding: utf-8 -*-
"""校验维度样张 TOC 域参数与题注文本。"""
import re
import sys
import zipfile

sys.path.insert(0, r"E:\bidcraft_skill\dev\prototypes")
OUT = r"E:\bidcraft_skill\dev\reports\dimension-samples"


def texts(name):
    z = zipfile.ZipFile(r"%s\%s.docx" % (OUT, name))
    xml = z.read("word/document.xml").decode("utf-8", "ignore")
    ts = re.findall(r"<w:t[^>]*>([^<]*)</w:t>", xml)
    instr = "".join(re.findall(r"<w:instrText[^>]*>([^<]*)</w:instrText>", xml))
    return ts, instr


checks = [
    ("s00_默认基线", ["表1-1", "图1-1"]),
    ("s07_题注_全文连续", ["表1", "图1"]),
    ("s08_题注_附录字母", ["附表1", "附图1"]),
    ("s21_图比_高图比50", None),
    ("s22_图比_低图比10", None),
    ("s23_图规则_仅照片", ["图1 施工现场全景", "图2 质量控制验收程序流程图"]),
    ("s24_图规则_仅图表", ["图1 施工现场全景"]),
    ("s01_字体_现代商务", None),
    ("s02_字体_全仿宋公文", None),
    ("s04_标题_通辽暗标式", ["1. 工程概况", "1.1 项目理解"]),
]
for name, keys in checks:
    ts, instr = texts(name)
    joined = " ".join(ts)
    print("== %s" % name)
    if "TOC" in instr:
        print("   TOC: %s" % instr)
    if keys is not None:
        for k in keys:
            print("   %s -> %s" % (k, k in joined))
    if name in ("s23_图规则_仅照片", "s24_图规则_仅图表", "s21_图比_高图比50", "s22_图比_低图比10"):
        figs = [t for t in ts if t.startswith(("图", "附图")) or "施工现场" in t]
        print("   图题:", figs)
