# -*- coding: utf-8 -*-
"""关键对照：旧模板 python-docx 往返保存 + 真实商务标(填充产物) Word 打开性。"""
from pathlib import Path

from docx import Document  # noqa: E402

DEMO = Path(r"E:\bidcraft_skill\dev\preview_demo")
TMP = DEMO / "matrix"
LOG = []

OLD = Path(r"E:\监理标书制作\和县建设工程监理有限公司\项目级\马鞍山和县化工园尾水水质提升工程（EPC总承包）监理\项目模板\资格证明及辅助资料表.docx")
BIZ = Path(r"E:\监理标书制作\和县建设工程监理有限公司\项目级\马鞍山和县化工园尾水水质提升工程（EPC总承包）监理\商务标\资格证明及辅助资料表.docx")

# 1) OLD round-trip
rt = TMP / "old_roundtrip_资格证明.docx"
try:
    d = Document(str(OLD))
    d.save(str(rt))
    LOG.append("old roundtrip saved")
except Exception as e:
    LOG.append("old roundtrip ERR %r" % e)

# 2) 商务标 是否存在
LOG.append("商务标资格证明存在: %s (%d KB)" % (BIZ.exists(), BIZ.stat().st_size // 1024 if BIZ.exists() else 0))


def word_ok(p):
    import win32com.client  # noqa: E402
    word = win32com.client.Dispatch("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    try:
        d = word.Documents.Open(str(p), ReadOnly=True)
        d.ExportAsFixedDocument(str(p.with_suffix(".pdf")), 17)
        d.Close(False)
        return "OK"
    except Exception:
        return "FAIL"
    finally:
        word.Quit()


for p, label in ((rt, "old_roundtrip"), (BIZ, "商务标资格证明")):
    if p.exists():
        LOG.append("%s -> %s" % (label, word_ok(p)))

(DEMO / "matrix" / "roundtrip_result.txt").write_text("\n".join(LOG), encoding="utf-8")
print("\n".join(LOG))
