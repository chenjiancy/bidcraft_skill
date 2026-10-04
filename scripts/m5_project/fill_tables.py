# -*- coding: utf-8 -*-
"""⑦ filler 拆包 · 表格填充（人员配备表/简历表/业绩汇总表）。"""
import re

from .fill_ocr import _find_resume_scan, ocr_resume_fields
from .fill_text import _iter_doc_paragraphs, _para_full_text, _set_para_text

__all__ = [
    "_table_first", "_fill_personnel_tables", "_duplicate_resume_tables",
    "_fill_resume_tables", "_iter_resume_cells", "_fill_performance_tables",
]


def _table_first(t):
    return "".join(c.text for c in t.rows[0].cells)


def _fill_personnel_tables(doc, material, pending):
    """附表7 拟投入监理人员配备表（表头含「项目职务」）：按 personnel 逐行填充。"""
    persons = material.get("personnel", []) or []
    for t in doc.tables:
        first = _table_first(t)
        if "项目职务" not in first or "出生年月" in first:
            continue
        if len(t.rows) <= 1:
            continue
        for ri, person in enumerate(persons[: len(t.rows) - 1], start=1):
            row = t.rows[ri]
            vals = {
                "人员姓名": person.get("name", ""),
                "年龄": str(person.get("age", "") or ""),
                "项目职务": person.get("role", ""),
            }
            cert = person.get("cert", "")
            if cert:
                vals["专业"] = cert
            for cell in row.cells:
                ct = cell.text.strip()
                for ph, v in vals.items():
                    if "【%s】" % ph in ct:
                        _set_para_text(cell.paragraphs[0], v)
                        break


def _duplicate_resume_tables(doc, count):
    """附表8 简历表：范本 1 份 → 按人员数复制（动态语义②，与生成器一致）。"""
    if count <= 1:
        return [t for t in doc.tables if "出生年月" in _table_first(t)]
    import copy
    resumes = [t for t in doc.tables
               if "出生年月" in _table_first(t) and len(t.rows) >= 11]
    if not resumes:
        return []
    node = resumes[0]._tbl
    last = node
    for _ in range(count - 1):
        new = copy.deepcopy(node)
        last.addnext(new)
        last = new
    return [t for t in doc.tables
            if "出生年月" in _table_first(t) and len(t.rows) >= 11]


def _fill_resume_tables(doc, lib_root, material, pending):
    """附表8 简历表（份数=personnel）：复制范本 → OCR 简历扫描件 → 填占位；无扫描件 → 待补。"""
    persons = material.get("personnel", []) or []
    resumes = _duplicate_resume_tables(doc, len(persons))
    for idx, t in enumerate(resumes):
        person = persons[idx] if idx < len(persons) else {}
        name = person.get("name", "")
        scan = _find_resume_scan(lib_root, name) if name else None
        fields = ocr_resume_fields(scan, cert_str=person.get("cert", "")) if scan else {}
        if not fields and name:
            pending.append("简历表[%s]：无简历扫描件或OCR为空，需人工补 17 字段" % name)
        for ri, row in enumerate(t.rows):
            for cell in _iter_resume_cells(row):
                for p in cell.paragraphs:
                    ct = _para_full_text(p)
                    if "【" not in ct:
                        continue
                    is_cert = "证书名称" in ct or "证书编号" in ct
                    if is_cert:
                        # 证书表：仅序号 1 行填证书；序号≥2 行清空占位（动态证书行，多证书人工后补）
                        seq = row.cells[1].text.strip()
                        if seq != "1":
                            _set_para_text(p, "")
                            continue
                    new = ct
                    changed = False
                    for m in re.finditer(r"【([^】]+)】", ct):
                        ph_key = m.group(1)
                        v = fields.get(ph_key, "")
                        if v:
                            new = new.replace("【%s】" % ph_key, v)
                            changed = True
                        elif ph_key not in fields:
                            pending.append("简历表[%s]：字段【%s】OCR未识别，需人工补"
                                           % (name, ph_key))
                    if changed:
                        _set_para_text(p, new)


def _iter_resume_cells(row):
    # 注意：不能用 id(cell._tc) 去重（Python 对象 id 会复用，误杀正常单元格）；
    # 用 XML 元素唯一 XPath 路径去重（gridSpan 合并格路径相同）。
    seen = set()
    for cell in row.cells:
        key = cell._tc.getroottree().getpath(cell._tc)
        if key in seen:
            continue
        seen.add(key)
        yield cell


def _fill_performance_tables(doc, material, pending):
    """附表2 已完成工程汇总表（表头含「项目名称…所在地…施工合同金额」且金额无（万元）后缀）：按 performance 逐行填。
    附表4 正在监理工程汇总表（金额含（万元））无素材，保留占位。"""
    perf = material.get("performance", []) or []
    for t in doc.tables:
        first = _table_first(t).replace(" ", "")   # 表头中文字间可能有空格（所在 地）
        if "项目名称" not in first or "所在地" not in first:
            continue
        if "（万元）" in first:          # 附表4 在监工程，非已完成业绩
            continue
        for ri, p in enumerate(perf[: len(t.rows) - 1], start=1):
            row = t.rows[ri]
            for cell in row.cells:
                ct = cell.text.strip()
                for ph, key in (("【业绩项目名称/所在地】", "project"),
                                ("【起止日期】", "sign_date"),
                                ("【施工合同金额（万元）】", "amount_wan")):
                    if ph in ct:
                        _set_para_text(cell.paragraphs[0],
                                       str(p.get(key, "") or ""))
                        break
