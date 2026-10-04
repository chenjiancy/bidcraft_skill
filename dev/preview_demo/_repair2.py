# -*- coding: utf-8 -*-
"""定位 v2：Word「打开并修复」+ 前后 diff，全程写日志文件。"""
import difflib
import traceback
import zipfile
from pathlib import Path

LOG = Path(r"E:\bidcraft_skill\dev\preview_demo\triage\repair_v2.log")
lines = []

DEMO = Path(r"E:\bidcraft_skill\dev\preview_demo")
NEW = DEMO / "项目模板" / "资格证明及辅助资料表.docx"
REPAIRED = DEMO / "triage" / "new_repaired_资格证明.docx"

import win32com.client  # noqa: E402
try:
    word = win32com.client.Dispatch("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    try:
        doc = word.Documents.Open(str(NEW), ReadOnly=False, OpenAndRepair=True)
        lines.append("open+repair OK")
        doc.SaveAs2(str(REPAIRED), FileFormat=16)
        doc.Close(False)
        lines.append("saved repaired")
    except Exception as e:
        lines.append("repair FAIL: %r | %s" % (e, getattr(e, "excepinfo", None)))
    finally:
        word.Quit()
except Exception as e:
    lines.append("COM FAIL %r" % e)

if REPAIRED.exists():
    def xml_of(p):
        with zipfile.ZipFile(p) as z:
            return z.read("word/document.xml").decode("utf-8")
    before = xml_of(NEW)
    after = xml_of(REPAIRED)
    lines.append("before=%d after=%d" % (len(before), len(after)))
    for tag in ("w:drawing", "wp:inline", "pic:pic", "w:pict", "v:imagedata",
                "w:object", "w:altChunk", "w:sectPr", "wp:docPr"):
        lines.append("  %s: %d -> %d" % (tag, before.count(tag), after.count(tag)))
    sm = difflib.SequenceMatcher(None, before, after)
    dels = [before[op[1]:op[2]] for op in sm.get_opcodes() if op[0] == "delete"]
    ins = [after[op[1]:op[2]] for op in sm.get_opcodes() if op[0] == "insert"]
    lines.append("deleted frags=%d inserted frags=%d" % (len(dels), len(ins)))
    for f in dels[:4]:
        lines.append("DEL>> " + f[:600].replace("\n", " "))
    for f in ins[:4]:
        lines.append("INS>> " + f[:600].replace("\n", " "))
else:
    lines.append("no repaired file")

LOG.write_text("\n".join(lines), encoding="utf-8")
