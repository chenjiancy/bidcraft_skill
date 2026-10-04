# -*- coding: utf-8 -*-
"""用 Word「打开并修复」定位损坏点：修复后另存，diff document.xml。"""
import zipfile
import shutil
from pathlib import Path

import win32com.client  # noqa: E402

DEMO = Path(r"E:\bidcraft_skill\dev\preview_demo")
NEW = DEMO / "项目模板" / "资格证明及辅助资料表.docx"
REPAIRED = DEMO / "triage" / "new_repaired_资格证明.docx"

word = win32com.client.Dispatch("Word.Application")
word.Visible = False
word.DisplayAlerts = 0
try:
    doc = word.Documents.Open(str(NEW), ReadOnly=False, OpenAndRepair=True)
    doc.SaveAs2(str(REPAIRED), FileFormat=16)  # 16 = docx
    doc.Close(False)
    print("repaired saved")
finally:
    word.Quit()

# diff: 提取修复前后 document.xml 的差异摘要
def xml_of(p):
    with zipfile.ZipFile(p) as z:
        return z.read("word/document.xml").decode("utf-8")

before = xml_of(NEW)
after = xml_of(REPAIRED)

# 统计差异
import re
out = Path(DEMO / "triage" / "repair_diff.txt")
lines = []
lines.append("before len=%d after len=%d" % (len(before), len(after)))
for tag in ("w:drawing", "w:inline", "pic:pic", "w:pict", "v:imagedata", "w:object", "w:txbxContent", "w:altChunk"):
    lines.append("%s: before=%d after=%d" % (tag, before.count(tag), after.count(tag)))
# 找到 before 中 after 里没有的片段（修复删除的部分）
import difflib
sm = difflib.SequenceMatcher(None, before, after)
removed_chars = []
for op in sm.get_opcodes():
    if op[0] == "delete":
        removed_chars.append(before[op[1]:op[2]])
lines.append("--- 被 Word 删除的片段数: %d ---" % len(removed_chars))
for frag in removed_chars[:5]:
    lines.append("DEL>> " + frag[:500].replace("\n", " "))
out.write_text("\n".join(lines), encoding="utf-8")
print("diff written")
