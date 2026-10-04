# -*- coding: utf-8 -*-
"""重打包矩阵：同一内容，不同 zip 封装方式 → Word 接受性。"""
import io
import zipfile
import shutil
from pathlib import Path

DEMO = Path(r"E:\bidcraft_skill\dev\preview_demo")
TMP = DEMO / "rezip"
shutil.rmtree(TMP, ignore_errors=True)
TMP.mkdir(parents=True)

OLD = Path(r"E:\监理标书制作\示例建设工程监理有限公司\项目级\示例示例园区尾水水质提升工程（EPC总承包）监理\项目模板\资格证明及辅助资料表.docx")

with zipfile.ZipFile(OLD) as z:
    entries = [(i, z.read(i.filename)) for i in z.infolist()]

def rezip(tag, order=None, compress=zipfile.ZIP_DEFLATED, store_raw=False):
    p = TMP / (tag + ".docx")
    with zipfile.ZipFile(p, "w", compression=compress) as z:
        it = entries if order is None else order
        for info, data in it:
            if store_raw:
                z.writestr(info, data)
            else:
                z.writestr(info.filename, data, compress_type=compress)
    return p

def word_ok(p):
    import win32com.client  # noqa: E402
    word = win32com.client.Dispatch("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    try:
        d = word.Documents.Open(str(p), ReadOnly=True)
        d.ExportAsFixedFormat(str(p.with_suffix(".pdf")), 17)
        d.Close(False)
        return "OK"
    except Exception:
        return "FAIL"
    finally:
        word.Quit()

# 变体
by_name = sorted(entries, key=lambda e: e[0].filename)
ct_first = [e for e in entries if e[0].filename == "[Content_Types].xml"] + \
           [e for e in entries if e[0].filename != "[Content_Types].xml"]
stored = entries  # STORED

cases = [
    ("A_order_same_orig", entries, zipfile.ZIP_DEFLATED),
    ("B_sorted", by_name, zipfile.ZIP_DEFLATED),
    ("C_ct_first", ct_first, zipfile.ZIP_DEFLATED),
    ("D_stored", stored, zipfile.ZIP_STORED),
]
log = []
for tag, order, comp in cases:
    p = rezip(tag, order, comp)
    log.append("%s -> %s (zip=%dKB)" % (tag, word_ok(p), p.stat().st_size // 1024))
(DEMO / "rezip" / "rezip_result.txt").write_text("\n".join(log), encoding="utf-8")
print("\n".join(log))
