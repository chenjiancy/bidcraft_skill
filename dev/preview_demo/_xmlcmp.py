# -*- coding: utf-8 -*-
"""XML 级比对：OLD vs NEW 资格证明 的 docPr id 唯一性 / sectPr 数量 / 命名空间异常。"""
import re
import zipfile
from pathlib import Path

OLD = Path(r"E:\监理标书制作\示例建设工程监理有限公司\项目级\示例示例园区尾水水质提升工程（EPC总承包）监理\项目模板\资格证明及辅助资料表.docx")
NEW = Path(r"E:\bidcraft_skill\dev\preview_demo\项目模板\资格证明及辅助资料表.docx")

OUT = Path(r"E:\bidcraft_skill\dev\preview_demo\_xmlcmp.out")
lines = []

for label, p in (("OLD", OLD), ("NEW", NEW)):
    with zipfile.ZipFile(p) as z:
        xml = z.read("word/document.xml").decode("utf-8")
        rels = z.read("word/_rels/document.xml.rels").decode("utf-8")
    docpr = re.findall(r'<wp:docPr[^>]*id="(\d+)"', xml)
    dup = [x for x in set(docpr) if docpr.count(x) > 1]
    lines.append("%s: docPr=%d 唯一=%d 重复=%s" % (label, len(docpr), len(set(docpr)), dup[:10]))
    lines.append("   sectPr 数量: %d" % len(re.findall(r'<w:sectPr', xml)))
    rel_targets = re.findall(r'Target="(media/[^"]+)"', rels)
    lines.append("   media 关系: %d（%s）" % (len(rel_targets), ",".join(sorted(set(rel_targets)))[:160]))
    # 预览图文件是否存在于包内
    files = z.namelist()
    lines.append("   包内文件数: %d" % len(files))
    # 检查是否有非标准 w:p 内嵌 w:tbl / 其他明显异常
    tbl_in_p = re.findall(r'<w:p[^>]*>.*?<w:tbl', xml, flags=re.S)
    lines.append("   p 内含 tbl: %d" % len(tbl_in_p))
    # 检查 body 内元素顺序头尾
    m = re.search(r"<w:body>(.*?)</w:body>", xml, flags=re.S)
    body = m.group(1)
    heads = re.findall(r"<w:(p|tbl|sectPr)[ >]", body[:400])
    tails = re.findall(r"<w:(p|tbl|sectPr)[ >]", body[-400:])
    lines.append("   body 头: %s | body 尾: %s" % (heads, tails))

OUT.write_text("\n".join(lines), encoding="utf-8")
