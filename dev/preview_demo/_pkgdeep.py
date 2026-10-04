# -*- coding: utf-8 -*-
"""深度对比：包内文件大小 / 压缩方式 / document.xml 全文哈希。"""
import hashlib
import zipfile
from pathlib import Path

DEMO = Path(r"E:\bidcraft_skill\dev\preview_demo")
OLD = Path(r"E:\监理标书制作\和县建设工程监理有限公司\项目级\马鞍山和县化工园尾水水质提升工程（EPC总承包）监理\项目模板\资格证明及辅助资料表.docx")
RT = DEMO / "matrix" / "old_roundtrip_资格证明.docx"
NEW = DEMO / "项目模板" / "资格证明及辅助资料表.docx"

out = []
for label, p in (("OLD", OLD), ("RT", RT), ("NEW", NEW)):
    with zipfile.ZipFile(p) as z:
        infos = z.infolist()
        comp = {}
        for i in infos:
            comp.setdefault(i.compress_type, 0)
            comp[i.compress_type] += 1
        total = sum(i.file_size for i in infos)
        out.append("%s: zip=%dKB 文件数=%d 压缩方式=%s 未压缩总大小=%dKB"
                   % (label, p.stat().st_size // 1024, len(infos), comp, total // 1024))
        for i in infos[:8]:
            out.append("   %-40s size=%dKB comp=%s" % (i.filename, i.file_size // 1024, i.compress_type))
        h = hashlib.md5(z.read("word/document.xml")).hexdigest()[:12]
        out.append("   document.xml md5=%s len=%d" % (h, len(z.read("word/document.xml"))))

(DEMO / "matrix" / "pkg_deep.txt").write_text("\n".join(out), encoding="utf-8")
