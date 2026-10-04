# -*- coding: utf-8 -*-
"""逐文件 md5 对比 OLD vs RT，找出 python-docx 真正改动的 part。"""
import hashlib
import zipfile
from pathlib import Path

DEMO = Path(r"E:\bidcraft_skill\dev\preview_demo")
OLD = Path(r"E:\监理标书制作\和县建设工程监理有限公司\项目级\马鞍山和县化工园尾水水质提升工程（EPC总承包）监理\项目模板\资格证明及辅助资料表.docx")
RT = DEMO / "matrix" / "old_roundtrip_资格证明.docx"

def parts(p):
    with zipfile.ZipFile(p) as z:
        return {i.filename: z.read(i.filename) for i in z.infolist()}

a, b = parts(OLD), parts(RT)
out = []
for name in a:
    ha = hashlib.md5(a[name]).hexdigest()[:10]
    hb = hashlib.md5(b[name]).hexdigest()[:10]
    same = "SAME" if ha == hb else "DIFF"
    out.append("%-40s %s %s/%s len=%d/%d" % (name, same, ha, hb, len(a[name]), len(b[name])))
(DEMO / "rezip" / "part_md5.txt").write_text("\n".join(out), encoding="utf-8")
