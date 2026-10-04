# -*- coding: utf-8 -*-
"""扫描 span 内所有块：drawing / r:embed / object / pict / 形状 等复杂元素。"""
import sys
from pathlib import Path

sys.path.insert(0, r"E:\bidcraft_skill\scripts")
from m5_project import generator as gen  # noqa: E402
from lxml import etree  # noqa: E402

DEMO = Path(r"E:\bidcraft_skill\dev\preview_demo")
SRC = gen._default_source_docx(Path(r"E:\监理标书制作\和县建设工程监理有限公司\项目级\马鞍山和县化工园尾水水质提升工程（EPC总承包）监理"))
blocks, src_doc = gen._extract_blocks(SRC)

NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
      "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
      "pic": "http://schemas.openxmlformats.org/drawingml/2006/picture",
      "v": "urn:schemas-microsoft-com:vml",
      "wps": "http://schemas.microsoft.com/office/word/2010/wordprocessingShape",
      "wpg": "http://schemas.microsoft.com/office/word/2010/wordprocessingGroup",
      "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
      "o": "urn:schemas-microsoft-com:office:office",
      "m": "http://schemas.openxmlformats.org/officeDocument/2006/math",
      "wne": "http://schemas.microsoft.com/office/word/2006/wordml"}

out = []
src_rels = []
with __import__("zipfile").ZipFile(SRC) as z:
    import re
    rels_xml = z.read("word/_rels/document.xml.rels").decode("utf-8")
    for m in re.finditer(r'Id="([^"]+)"[^>]*Target="([^"]+)"', rels_xml):
        src_rels.append((m.group(1), m.group(2)))

R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
xp_embeds = etree.XPath(".//*[@r:embed or @r:id or @r:link]", namespaces=NS)
xp_drawings = etree.XPath(".//w:drawing", namespaces=NS)
xp_objects = etree.XPath(".//w:object | .//v:shape | .//wps:sp | .//wps:wsp | .//wpg:grpSp | .//m:oMath", namespaces=NS)

for i in range(865, 947):
    node = blocks[i]["node"]
    t = blocks[i]["type"]
    # 该块包含的 r:embed / r:id 引用（用 etree.XPath 编译，规避 BaseOxmlElement 限制）
    embeds = xp_embeds(node)
    drawings = xp_drawings(node)
    objects = xp_objects(node)
    if embeds or drawings or objects:
        info = []
        for e in embeds[:4]:
            rid = e.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed") or \
                  e.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id") or \
                  e.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}link")
            exists = rid in [r[0] for r in src_rels]
            info.append("r:%s(源rels%s)" % (rid, "有" if exists else "无"))
        out.append("block %d (%s): drawings=%d objects=%d embeds=%s"
                   % (i, t, len(drawings), len(objects), "|".join(info) or "-"))

(DEMO / "bisect2" / "complex_blocks.txt").write_text("\n".join(out) or "无复杂元素", encoding="utf-8")
print(out or ["无复杂元素"])
