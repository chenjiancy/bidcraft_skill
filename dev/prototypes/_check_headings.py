# -*- coding: utf-8 -*-
"""查 s04 标题编号与 s25/s26 TOC 域。"""
import re
import zipfile

OUT = r"E:\bidcraft_skill\dev\reports\dimension-samples"


def dump(name):
    z = zipfile.ZipFile(r"%s\%s.docx" % (OUT, name))
    xml = z.read("word/document.xml").decode("utf-8", "ignore")
    ts = re.findall(r"<w:t[^>]*>([^<]*)</w:t>", xml)
    instr = "".join(re.findall(r"<w:instrText[^>]*>([^<]*)</w:instrText>", xml))
    return ts, instr


for name in ("s04_标题_通辽暗标式", "s25_目录_无页码", "s26_目录_两级紧凑"):
    ts, instr = dump(name)
    print("== %s" % name)
    print("   TOC: %r" % instr)
    heads = [t for t in ts if t.startswith(("第", "一、", "二、", "三、", "1、", "1.", "2、", "2.")) or re.match(r"^1\.\d", t)]
    print("   标题样本:", heads[:14])
