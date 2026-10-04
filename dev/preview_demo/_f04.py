# -*- coding: utf-8 -*-
"""定位 法定代表人身份证明.docx 里 r:embed=rId9 的元素上下文。"""
import re
import zipfile
from pathlib import Path

DEMO = Path(r"E:\bidcraft_skill\dev\preview_demo")
p = DEMO / "项目模板" / "法定代表人身份证明.docx"
with zipfile.ZipFile(p) as z:
    xml = z.read("word/document.xml").decode("utf-8")

# 找 r:embed 出现的上下文
out = []
for m in re.finditer(r'r:embed="rId\d+"', xml):
    s = max(0, m.start() - 400)
    frag = xml[s:m.end() + 300]
    out.append("...%s..." % frag.replace("\n", " "))
    out.append("")

# 也找所有 r:embed / r:id 引用
out.append("所有 r:embed:", )
for m in re.finditer(r'r:(embed|id|link)="(rId\d+)"', xml):
    out.append("  %s=%s" % (m.group(1), m.group(2)))

# 该文件 span 784..804 的源块里是否有 embed
import sys
sys.path.insert(0, r"E:\bidcraft_skill\scripts")
from m5_project import generator as gen  # noqa: E402
SRC = gen._default_source_docx(Path(r"E:\监理标书制作\示例建设工程监理有限公司\项目级\示例示例园区尾水水质提升工程（EPC总承包）监理"))
blocks, _ = gen._extract_blocks(SRC)
from lxml import etree  # noqa: E402
NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
xp = etree.XPath(".//*[@r:embed or @r:id or @r:link]", namespaces=NS)
out.append("源块 784..804 含关系引用:")
for i in range(784, 805):
    hits = xp(blocks[i]["node"])
    if hits:
        for el in hits:
            out.append("  block %d: %s" % (i, el.tag.split("}")[-1]))

(DEMO / "triage" / "f04_embed.txt").write_text("\n".join(out), encoding="utf-8")
