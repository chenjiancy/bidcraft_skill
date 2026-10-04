# -*- coding: utf-8 -*-
"""⑨ docxtpl 对比评估 · 路线 B：docxtpl 渲染（Jinja2 语法，行循环 + 变量替换）。"""
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(OUT / "_deps"))   # 局部安装的 docxtpl/jinja2，不污染全局

from docxtpl import DocxTemplate  # noqa: E402

DATA = {
    "project_name": "马鞍山和县化工园尾水水质提升工程（EPC总承包）监理",
    "rows": [
        {"姓名": "陈云", "出生年月": "1970年5月", "备注": "总监"},
        {"姓名": "阮旭", "出生年月": "1982年11月", "备注": "专监"},
        {"姓名": "黄诚", "出生年月": "1990年3月", "备注": "监理员"},
    ],
}


def render_docxtpl(tpl_path, out_path):
    tpl = DocxTemplate(str(tpl_path))
    tpl.render(DATA)
    tpl.save(str(out_path))
    return str(out_path)


if __name__ == "__main__":
    print(render_docxtpl(OUT / "tpl_docxtpl.docx", OUT / "out_docxtpl.docx"))
