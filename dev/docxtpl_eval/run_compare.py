# -*- coding: utf-8 -*-
"""⑨ docxtpl 对比评估 · 对比器：渲染两种路线产物 → 测 ①文字保真 ②样式保留 ③代码行数 → 报告。

结论维度（对照产品需求）：
  - 文字保真：招标原文固定文字渲染后一字不差；
  - 样式保留：标题/正文 run 字体字号粗体、表格边框、循环行边框；
  - 代码量：渲染器实现行数；
  - 依赖：第三方（docxtpl+jinja2）vs 现有（python-docx 标准工具）。
"""
import json
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(OUT.parent.parent / "scripts"))   # scripts，供 docx_util 相对导入
sys.path.insert(0, str(OUT))

from docx import Document  # noqa: E402

from _build_templates import build_original, inject_jinja  # noqa: E402
from render_self import render_self, DATA  # noqa: E402
from render_docxtpl import render_docxtpl  # noqa: E402


# --------------------------------------------------------------------------
# 测量
# --------------------------------------------------------------------------
def _full_text(path):
    doc = Document(path)
    lines = [p.text for p in doc.paragraphs if p.text]
    for t in doc.tables:
        for row in t.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    if p.text:
                        lines.append(p.text)
    return lines


def _style_snapshot(path):
    doc = Document(path)
    snap = {"title_run": None, "body_runs": [], "table_borders": False,
            "header_bold": False, "loop_row_borders": []}
    for p in doc.paragraphs:
        if p.text.startswith("第一章"):
            r = p.runs[0]
            snap["title_run"] = {"font": r.font.name, "size": r.font.size.pt if r.font.size else None,
                                 "bold": bool(r.bold)}
    for p in doc.paragraphs:
        if p.text.startswith("项目名称："):
            r = p.runs[0]
            snap["body_runs"].append({"font": r.font.name,
                                      "size": r.font.size.pt if r.font.size else None,
                                      "bold": bool(r.bold)})
    tbl = doc.tables[0]
    tb = tbl._tbl.tblPr
    snap["table_borders"] = tb.find("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}tblBorders") is not None
    for c in tbl.rows[0].cells:
        snap["header_bold"] = bool(c.paragraphs[0].runs and c.paragraphs[0].runs[0].bold) or snap["header_bold"]
    for row in tbl.rows[1:]:
        cell = row.cells[0]
        snap["loop_row_borders"].append(bool(
            row._tr.find("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}trPr")))
    return snap


def _count_lines(py_path):
    return sum(1 for _ in open(py_path, encoding="utf-8"))


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------
def run():
    s = build_original(OUT / "tpl_self.docx")
    d = inject_jinja(s, OUT / "tpl_docxtpl.docx")
    out_self = render_self(s, OUT / "out_self.docx")
    out_docx = render_docxtpl(d, OUT / "out_docxtpl.docx")

    fixed = ["第一章 投标文件格式", "项目名称：", "（盖章）", "姓名", "出生年月", "备注"]
    result = {
        "fixed_text": {"self": {}, "docxtpl": {}},
        "style": {"self": _style_snapshot(out_self), "docxtpl": _style_snapshot(out_docx)},
        "lines": {"self_render": _count_lines(OUT / "render_self.py"),
                  "docxtpl_render": _count_lines(OUT / "render_docxtpl.py")},
        "deps": {"self": ["python-docx（已在产品依赖）", "docx_util（自研公共工具）"],
                 "docxtpl": ["docxtpl", "jinja2（第三方，CI 需新增依赖）"]},
        "rows_rendered": {},
    }
    for name, path in (("self", out_self), ("docxtpl", out_docx)):
        lines = "\n".join(_full_text(path))
        for t in fixed:
            result["fixed_text"][name][t] = t in lines
        result["rows_rendered"][name] = doc_tables_rows(path)
    return result


def doc_tables_rows(path):
    doc = Document(path)
    n = 0
    for t in doc.tables:
        n += len(t.rows)
    return n


if __name__ == "__main__":
    res = run()
    (OUT / "对比结果.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(res, ensure_ascii=False, indent=2))
