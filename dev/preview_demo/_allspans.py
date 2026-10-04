# -*- coding: utf-8 -*-
"""全 span 扫描：哪些源块带 blip/drawing/object（需决定保留/移除策略）。"""
import re
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, r"E:\bidcraft_skill\scripts")
from m5_project import generator as gen  # noqa: E402
from lxml import etree  # noqa: E402

PROJ = Path(r"E:\监理标书制作\示例建设工程监理有限公司\项目级\示例示例园区尾水水质提升工程（EPC总承包）监理")
SRC = gen._default_source_docx(PROJ)
CONTRACT = gen._default_contract_path(PROJ)
blocks, _ = gen._extract_blocks(SRC)

NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
      "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
      "v": "urn:schemas-microsoft-com:vml",
      "wps": "http://schemas.microsoft.com/office/word/2010/wordprocessingShape",
      "wpg": "http://schemas.microsoft.com/office/word/2010/wordprocessingGroup"}
xp_blip = etree.XPath(".//a:blip", namespaces=NS)
xp_draw = etree.XPath(".//w:drawing", namespaces=NS)
xp_obj = etree.XPath(".//w:object | .//v:shape | .//wps:sp | .//wps:wsp | .//wpg:grpSp", namespaces=NS)

contract = gen.core.read_json(CONTRACT, None)
out = []
for f in contract.get("格式文件", []):
    s, e = f.get("块范围", [None, None])
    if s is None:
        continue
    hits = []
    for i in range(s, e + 1):
        if xp_blip(blocks[i]["node"]) or xp_draw(blocks[i]["node"]) or xp_obj(blocks[i]["node"]):
            hits.append(i)
    if hits:
        out.append("%s [%d..%d] 含图块: %s" % (f["id"], s, e, hits))
(DEMO := Path(r"E:\bidcraft_skill\dev\preview_demo")) and \
    (DEMO / "triage" / "all_spans_images.txt").write_text("\n".join(out) or "无", encoding="utf-8")
print(out or ["无"])
