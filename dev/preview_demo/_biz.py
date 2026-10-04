# -*- coding: utf-8 -*-
"""干净重测：真实商务标目录全部文件 Word 打开性。"""
import time
from pathlib import Path

BIZ = Path(r"E:\监理标书制作\和县建设工程监理有限公司\项目级\马鞍山和县化工园尾水水质提升工程（EPC总承包）监理\商务标")
DEMO = Path(r"E:\bidcraft_skill\dev\preview_demo")
out = []

def test(label, p):
    import win32com.client  # noqa: E402
    word = win32com.client.Dispatch("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    try:
        d = word.Documents.Open(str(p), ReadOnly=True, ConfirmConversions=False)
        d.Close(False)
        out.append("%s -> OK (%d KB)" % (label, p.stat().st_size // 1024))
    except Exception as e:
        info = getattr(e, "excepinfo", None) or []
        out.append("%s -> FAIL %s" % (label, info[2] if len(info) > 2 else repr(e)))
    finally:
        word.Quit()
        time.sleep(0.8)

for f in sorted(BIZ.glob("*.docx")):
    test(f.stem, f)

(DEMO / "triage" / "biz_clean.txt").write_text("\n".join(out), encoding="utf-8")
print("\n".join(out))
