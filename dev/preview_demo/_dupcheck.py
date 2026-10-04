# -*- coding: utf-8 -*-
"""检查块区间内重复的 w:id / 书签 / rsid 等组合级异常。"""
import copy
import re
import sys
from pathlib import Path
from collections import Counter

sys.path.insert(0, r"E:\bidcraft_skill\scripts")
from docx import Document  # noqa: E402
from docx.oxml.ns import qn  # noqa: E402

from m5_project import generator as gen  # noqa: E402
SRC = gen._default_source_docx(Path(r"E:\监理标书制作\和县建设工程监理有限公司\项目级\马鞍山和县化工园尾水水质提升工程（EPC总承包）监理"))
blocks, _ = gen._extract_blocks(SRC)

doc = Document()
for i in range(865, 947):
    doc.element.body.append(copy.deepcopy(blocks[i]["node"]))
body_el = doc.element.body
sp_el = body_el.find(qn("w:sectPr"))
if sp_el is not None:
    body_el.remove(sp_el)
    body_el.append(sp_el)

xml = doc.element.xml
lines = []
# 各类 id 属性统计
for attr in ("w:id", "w:rsidR", "w:rsidRPr", "w:rsidDel", "w:rsidP",
             "w:bookmarkStart", "w:bookmarkEnd", "w:commentRangeStart", "w:annotationRef"):
    ids = re.findall(r'<%s[^>]*?w:id="(\d+)"' % attr, xml) or re.findall(r'%s' % attr, xml)
    if attr in ("w:bookmarkStart", "w:bookmarkEnd", "w:commentRangeStart"):
        lines.append("%s: %d 处" % (attr, len(ids)))
    else:
        c = Counter(ids)
        dup = {k: v for k, v in c.items() if v > 1}
        lines.append("%s: 共%d 唯一%d 重复=%s" % (attr, len(ids), len(c), dict(list(dup.items())[:10])))

# 书签名称重复
bms = re.findall(r'<w:bookmarkStart[^>]*w:name="([^"]+)"', xml)
bc = Counter(bms)
dup_bm = {k: v for k, v in bc.items() if v > 1}
lines.append("书签名称重复: %s" % dict(list(dup_bm.items())[:10]))

# 书签 Start 有 id 但无对应 End
start_ids = set(re.findall(r'<w:bookmarkStart[^>]*w:id="(\d+)"', xml))
end_ids = set(re.findall(r'<w:bookmarkEnd[^>]*w:id="(\d+)"', xml))
lines.append("bookmark start 无 end: %s" % sorted(start_ids - end_ids)[:10])
lines.append("bookmark end 无 start: %s" % sorted(end_ids - start_ids)[:10])

# 校验 XML 结构: w:tbl 直接相邻无段落间隔
body_xml = re.search(r"<w:body>(.*)</w:body>", xml, re.S).group(1)
adjacent_tbl = re.findall(r"</w:tbl>\s*<w:tbl", body_xml)
lines.append("相邻表格(无段落间隔): %d 处" % len(adjacent_tbl))

# 段落内多个 sectPr / body 多个 sectPr
lines.append("body 内 sectPr: %d" % len(re.findall(r"<w:sectPr", body_xml)))

(DEMO := Path(r"E:\bidcraft_skill\dev\preview_demo")) and \
    (DEMO / "matrix" / "dup_ids.txt").write_text("\n".join(lines), encoding="utf-8")
print("\n".join(lines))
