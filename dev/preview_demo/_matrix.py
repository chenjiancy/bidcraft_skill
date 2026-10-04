# -*- coding: utf-8 -*-
"""矩阵测试：A空白 B移动sectPr C单块 D单块+移动 E小块组合 —— 定位损坏底数。"""
import copy
import shutil
import sys
from pathlib import Path

sys.path.insert(0, r"E:\bidcraft_skill\scripts")
from docx import Document  # noqa: E402
from docx.oxml.ns import qn  # noqa: E402

DEMO = Path(r"E:\bidcraft_skill\dev\preview_demo")
TMP = DEMO / "matrix"
shutil.rmtree(TMP, ignore_errors=True)
TMP.mkdir(parents=True)

from m5_project import generator as gen  # noqa: E402
SRC = gen._default_source_docx(Path(r"E:\监理标书制作\示例建设工程监理有限公司\项目级\示例示例园区尾水水质提升工程（EPC总承包）监理"))
blocks, _ = gen._extract_blocks(SRC)

LOG = []
def build(tag, blocks_idx, move_sectpr=True, native=False):
    doc = Document()
    if native:
        doc.add_paragraph("原生段落测试")
    for i in blocks_idx:
        doc.element.body.append(copy.deepcopy(blocks[i]["node"]))
    if move_sectpr:
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
        return "OK"
    except Exception:
        return "FAIL"
    finally:
        word.Quit()


cases = [
    ("A_blank_save", [], True),
    ("B_blank_move", [], True),
    ("C_blank_nomove_native", [865], False),
    ("D_blank_native", [], True),
    ("E_block865", [865], True),
    ("F_block866_867_868", [866, 867, 868], True),
    ("G_table882", [882], True),
    ("H_table890", [890], True),
    ("I_table896", [896], True),
    ("J_table916", [916], True),
    ("K_table922", [922], True),
    ("L_table930", [930], True),
    ("M_table939", [939], True),
    ("N_table946", [946], True),
]
for tag, idx, mv in cases:
    native = tag == "C_blank_nomove_native"
    p = build(tag, idx, mv, native=native)
    r = word_ok(p)
    LOG.append("%s: %s" % (tag, r))
(DEMO / "matrix" / "matrix_result.txt").write_text("\n".join(LOG), encoding="utf-8")
print("\n".join(LOG))
