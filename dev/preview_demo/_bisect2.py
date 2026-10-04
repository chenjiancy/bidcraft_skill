# -*- coding: utf-8 -*-
"""二分 v2：资格证明 span 865..946 四分测试。"""
import copy
import shutil
import sys
from pathlib import Path

sys.path.insert(0, r"E:\bidcraft_skill\scripts")
from docx import Document  # noqa: E402
from docx.oxml.ns import qn  # noqa: E402

from m5_project import generator as gen  # noqa: E402

DEMO = Path(r"E:\bidcraft_skill\dev\preview_demo")
TMP = DEMO / "bisect2"
shutil.rmtree(TMP, ignore_errors=True)
TMP.mkdir(parents=True)

SRC = gen._default_source_docx(Path(r"E:\监理标书制作\和县建设工程监理有限公司\项目级\马鞍山和县化工园尾水水质提升工程（EPC总承包）监理"))
blocks, _ = gen._extract_blocks(SRC)
S, E = 865, 946


def build(tag, indices):
    doc = Document()
    for i in indices:
        doc.element.body.append(copy.deepcopy(blocks[i]["node"]))
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
        d.Close(False)
        return "OK"
    except Exception:
        return "FAIL"
    finally:
        word.Quit()


total = E - S + 1  # 82
qs = []
step = 4
for k in range(step):
    qs.append(list(range(S + k * total // step, S + (k + 1) * total // step)))
print([(q[0], q[-1], len(q)) for q in qs])

results = []
for k, q in enumerate(qs):
    p = build("Q%d" % (k + 1), q)
    r = word_ok(p)
    results.append("Q%d [%d..%d] n=%d -> %s" % (k + 1, q[0], q[-1], len(q), r))
    print(results[-1])
(DEMO / "bisect2" / "quarters.txt").write_text("\n".join(results), encoding="utf-8")
