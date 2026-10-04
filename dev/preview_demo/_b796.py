# -*- coding: utf-8 -*-
"""查源块 796 的图片引用目标。"""
import re
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, r"E:\bidcraft_skill\scripts")
from m5_project import generator as gen  # noqa: E402
from lxml import etree  # noqa: E402

SRC = gen._default_source_docx(Path(r"E:\监理标书制作\示例建设工程监理有限公司\项目级\示例示例园区尾水水质提升工程（EPC总承包）监理"))
blocks, _ = gen._extract_blocks(SRC)

NS = {"r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
xp = etree.XPath(".//*[@r:embed]", namespaces=NS)

with zipfile.ZipFile(SRC) as z:
    rels = z.read("word/_rels/document.xml.rels").decode("utf-8")
    targets = dict(re.findall(r'Id="(rId\d+)"[^>]*Target="([^"]+)"', rels))

out = []
for el in xp(blocks[796]["node"]):
    rid = el.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed")
    out.append("block796 %s r:embed=%s target=%s" % (el.tag.split("}")[-1], rid, targets.get(rid, "?")))
# 该 blip 所在段落文本
txt = "".join(t.text or "" for t in blocks[796]["node"].iter(
    "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t"))
out.append("block796 段落文本: %r" % txt[:100])
(DEMO := Path(r"E:\bidcraft_skill\dev\preview_demo")) and \
    (DEMO / "triage" / "b796.txt").write_text("\n".join(out), encoding="utf-8")
print("\n".join(out))
