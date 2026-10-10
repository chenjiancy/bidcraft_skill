# -*- coding: utf-8 -*-
"""docx 文本/占位符通用工具（跨 run 安全）。

背景：Word 文档段落文本常被拆成多个 run（内部碎片），占位符替换若只处理单个 run
会漏替换、错位（generator/filler 曾多次踩坑：doc.paragraphs.index 失效、id() 去重
误杀、跨 run 拆分）。本模块提供统一的「跨 run 取文 / 整段写入 / 占位符替换」原语，
generator / filler 全部经由这里，配套单测 tests/unit/test_docx_util.py。
"""
from docx.oxml.ns import qn


def _el(p):
    """统一取 w:p 底层元素：兼容 python-docx Paragraph 与原生 CT_P/raw element。"""
    return p._p if hasattr(p, "_p") else p


def para_text(p):
    """段落全文（含跨 run、超链接内文字）。p 为 Paragraph 或原生 w:p 元素。"""
    return "".join(t.text or "" for t in _el(p).iter(qn("w:t")))


def para_runs(p):
    """段落所有 w:r 元素（含嵌套，如超链接内 run）。"""
    return [node for node in _el(p).iter(qn("w:r"))]


def set_para_text(p, text):
    """整段替换为 text：保留首个 w:r 的 rPr 与段落 pPr，删除其余 run。

    与旧实现的差异：基于 iter(w:r)（含超链接内 run）而非 p.runs（仅顶层），
    且空段落（无 run）时补建 run，保证占位符替换永不静默丢失。
    兼容 python-docx Paragraph 与原生 w:p 元素。
    """
    el = _el(p)
    runs = [node for node in el.iter(qn("w:r"))]
    if runs:
        first = runs[0]
        t_els = [node for node in first.iter(qn("w:t"))]
        if t_els:
            t_els[0].text = text
            for t in t_els[1:]:
                t.getparent().remove(t)
        else:
            t = first.makeelement(qn("w:t"), {})
            first.append(t)
            t.text = text
        for r in runs[1:]:
            r.getparent().remove(r)      # 兼容嵌套 run（超链接内 w:r）：从真实父节点移除
    else:
        r = el.makeelement(qn("w:r"), {})
        el.append(r)
        t = r.makeelement(qn("w:t"), {})
        r.append(t)
        t.text = text


def replace_in_para(p, old, new):
    """段落文本级替换（跨 run）：替换全部命中处，保留首 run rPr 与段落 pPr。
    返回替换次数；old 为空字符串返回 0。
    """
    if not old:
        return 0
    full = para_text(p)
    if old not in full:
        return 0
    set_para_text(p, full.replace(old, new))
    return full.count(old)


def set_cell_text(cell, text):
    """清空单元格首段并写入 text（保留首 run rPr 与段落 pPr）。"""
    set_para_text(cell.paragraphs[0], text)
