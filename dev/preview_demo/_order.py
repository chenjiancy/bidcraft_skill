# -*- coding: utf-8 -*-
"""检查 python-docx 保存的 zip 条目顺序。"""
import zipfile
from pathlib import Path

DEMO = Path(r"E:\bidcraft_skill\dev\preview_demo")
OLD = Path(r"E:\监理标书制作\和县建设工程监理有限公司\项目级\马鞍山和县化工园尾水水质提升工程（EPC总承包）监理\项目模板\资格证明及辅助资料表.docx")
RT = DEMO / "matrix" / "old_roundtrip_资格证明.docx"
AOK = DEMO / "rezip" / "A_order_same_orig.docx"

out = []
for label, p in (("OLD(Word可开)", OLD), ("RT(python-docx,Word拒)", RT), ("A重打包(Word可开)", AOK)):
    with zipfile.ZipFile(p) as z:
        order = [i.filename for i in z.infolist()]
    out.append("=== %s ===" % label)
    out.extend("  %02d %s" % (n, f) for n, f in enumerate(order))
(DEMO / "rezip" / "entry_order.txt").write_text("\n".join(out), encoding="utf-8")
