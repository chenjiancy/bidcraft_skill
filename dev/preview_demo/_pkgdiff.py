# -*- coding: utf-8 -*-
"""old(Word可开) vs old_roundtrip(Word拒) 包级 diff：Content_Types / rels / document.xml 头尾。"""
import zipfile
import difflib
from pathlib import Path

DEMO = Path(r"E:\bidcraft_skill\dev\preview_demo")
OLD = Path(r"E:\监理标书制作\示例建设工程监理有限公司\项目级\示例示例园区尾水水质提升工程（EPC总承包）监理\项目模板\资格证明及辅助资料表.docx")
RT = DEMO / "matrix" / "old_roundtrip_资格证明.docx"

out = []
with zipfile.ZipFile(OLD) as z:
    old_files = set(z.namelist())
    old_ct = z.read("[Content_Types].xml").decode("utf-8")
    old_rels = z.read("_rels/.rels").decode("utf-8")
    old_drels = z.read("word/_rels/document.xml.rels").decode("utf-8")
    old_doc = z.read("word/document.xml").decode("utf-8")
with zipfile.ZipFile(RT) as z:
    rt_files = set(z.namelist())
    rt_ct = z.read("[Content_Types].xml").decode("utf-8")
    rt_rels = z.read("_rels/.rels").decode("utf-8")
    rt_drels = z.read("word/_rels/document.xml.rels").decode("utf-8")
    rt_doc = z.read("word/document.xml").decode("utf-8")

out.append("OLD 文件: %d | RT 文件: %d | 新增: %s | 缺失: %s"
           % (len(old_files), len(rt_files),
              sorted(rt_files - old_files)[:8], sorted(old_files - rt_files)[:8]))

def diff_sec(name, a, b):
    d = list(difflib.unified_diff(a.splitlines(), b.splitlines(), lineterm="", n=1))
    out.append("--- %s diff %d 行 ---" % (name, len(d)))
    out.extend(d[:40])

diff_sec("[Content_Types].xml", old_ct, rt_ct)
diff_sec("_rels/.rels", old_rels, rt_rels)
diff_sec("document.xml.rels", old_drels, rt_drels)

# document.xml 前 3000 字符
out.append("--- OLD document.xml head ---")
out.append(old_doc[:2500])
out.append("--- RT document.xml head ---")
out.append(rt_doc[:2500])

(DEMO / "matrix" / "pkg_diff.txt").write_text("\n".join(out), encoding="utf-8")
