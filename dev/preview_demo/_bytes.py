# -*- coding: utf-8 -*-
"""字节级对比 OLD vs RT vs A：本地头/EOCD/flag/版本。"""
from pathlib import Path

DEMO = Path(r"E:\bidcraft_skill\dev\preview_demo")
OLD = Path(r"E:\监理标书制作\和县建设工程监理有限公司\项目级\马鞍山和县化工园尾水水质提升工程（EPC总承包）监理\项目模板\资格证明及辅助资料表.docx")
RT = DEMO / "matrix" / "old_roundtrip_资格证明.docx"
A = DEMO / "rezip" / "A_order_same_orig.docx"

def hexdump(p, start, n=48):
    with open(p, "rb") as f:
        f.seek(start)
        return f.read(n).hex(" ")

def tail(p, n=120):
    sz = Path(p).stat().st_size
    with open(p, "rb") as f:
        f.seek(sz - n)
        return f.read().hex(" ")

out = []
for label, p in (("OLD", OLD), ("RT", RT), ("A", A)):
    out.append("=== %s size=%d ===" % (label, Path(p).stat().st_size))
    out.append("  head: " + hexdump(p, 0))
    out.append("  tail: " + tail(p))
(DEMO / "rezip" / "bytes_diff.txt").write_text("\n".join(out), encoding="utf-8")
