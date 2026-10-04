# -*- coding: utf-8 -*-
"""二分定位：从招标文件源提取资格证明块，纯拷贝(无任何占位处理)后逐组 Word 测试。"""
import shutil
import sys
from pathlib import Path

sys.path.insert(0, r"E:\bidcraft_skill\scripts")
from docx import Document  # noqa: E402
from docx.oxml.ns import qn  # noqa: E402

DEMO = Path(r"E:\bidcraft_skill\dev\preview_demo")
TMP = DEMO / "bisect"
shutil.rmtree(TMP, ignore_errors=True)
TMP.mkdir(parents=True)

from m5_project import generator as gen  # noqa: E402

SRC = gen._default_source_docx(Path(r"E:\监理标书制作\和县建设工程监理有限公司\项目级\马鞍山和县化工园尾水水质提升工程（EPC总承包）监理"))
# 从契约 JSON 取资格证明 span
proj = Path(r"E:\监理标书制作\和县建设工程监理有限公司\项目级\马鞍山和县化工园尾水水质提升工程（EPC总承包）监理")
contract = gen.core.read_json(gen._default_contract_path(proj), None)
span = (865, 946)  # F06a..F06k 资格证明及辅助资料表 合并范围
print("span:", span, "src:", SRC)
blocks, src_doc = gen._extract_blocks(SRC)
print("总块数:", len(blocks))


def build(indices, tag):
    doc = Document()
    for i in indices:
        doc.element.body.append(__import__("copy").deepcopy(blocks[i]["node"]))
    body_el = doc.element.body
    sp_el = body_el.find(qn("w:sectPr"))
    if sp_el is not None:
        body_el.remove(sp_el)
        body_el.append(sp_el)
    p = TMP / (tag + ".docx")
    doc.save(str(p))
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
        return True
    except Exception:
        return False
    finally:
        word.Quit()


results = {}
s, e = span
tests = [("full", list(range(s, e + 1))),
         ("first_half", list(range(s, s + (e - s + 1) // 2))),
         ("second_half", list(range(s + (e - s + 1) // 2, e + 1)))]
for tag, idx in tests:
    p = build(idx, tag)
    ok = word_ok(p)
    results[tag] = ok
    print("%s: %s (%d blocks)" % (tag, "OK" if ok else "FAIL", len(idx)))
    if not ok:
        (DEMO / "bisect" / ("result_%s.txt" % tag)).write_text("FAIL", encoding="utf-8")
