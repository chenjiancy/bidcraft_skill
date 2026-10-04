# -*- coding: utf-8 -*-
"""dump 块 878 与 926 的 XML，确认带 r:id 的元素类型。"""
import sys
from pathlib import Path

sys.path.insert(0, r"E:\bidcraft_skill\scripts")
from m5_project import generator as gen  # noqa: E402
from lxml import etree  # noqa: E402

DEMO = Path(r"E:\bidcraft_skill\dev\preview_demo")
SRC = gen._default_source_docx(Path(r"E:\监理标书制作\示例建设工程监理有限公司\项目级\示例示例园区尾水水质提升工程（EPC总承包）监理"))
blocks, _ = gen._extract_blocks(SRC)

NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
xp = etree.XPath(".//*[@r:embed or @r:id or @r:link]", namespaces=NS)

out = []
for i in (878, 926):
    node = blocks[i]["node"]
    for el in xp(node):
        out.append("=== block %d: %s ===" % (i, el.tag))
        out.append(etree.tostring(el, pretty_print=True).decode("utf-8")[:1500])
        out.append("")
(DEMO / "bisect2" / "rel_blocks_dump.txt").write_text("\n".join(out), encoding="utf-8")
