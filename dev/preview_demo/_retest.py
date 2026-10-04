# -*- coding: utf-8 -*-
"""干净重测：每个文件一个全新 Word 实例，完整记录错误。"""
import time
from pathlib import Path

DEMO = Path(r"E:\bidcraft_skill\dev\preview_demo")
FILES = {
    "OLD原版": r"E:\监理标书制作\示例建设工程监理有限公司\项目级\示例示例园区尾水水质提升工程（EPC总承包）监理\项目模板\资格证明及辅助资料表.docx",
    "RT往返": str(DEMO / "matrix" / "old_roundtrip_资格证明.docx"),
    "A重打包": str(DEMO / "rezip" / "A_order_same_orig.docx"),
    "NEW演示": str(DEMO / "项目模板" / "资格证明及辅助资料表.docx"),
}
out = []

def test(label, p):
    import win32com.client  # noqa: E402
    import pythoncom  # noqa: E402
    word = win32com.client.Dispatch("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    try:
        d = word.Documents.Open(p, ReadOnly=True, ConfirmConversions=False)
        d.ExportAsFixedFormat(str(Path(p).with_suffix(".pdf2.pdf")), 17)
        d.Close(False)
        out.append("%s -> OK" % label)
    except Exception as e:
        info = getattr(e, "excepinfo", None) or []
        out.append("%s -> FAIL %r %s" % (label, e, info))
    finally:
        word.Quit()
        time.sleep(1)

for label, p in FILES.items():
    test(label, p)
(DEMO / "triage" / "clean_retest.txt").write_text("\n".join(out), encoding="utf-8")
print("\n".join(out))
