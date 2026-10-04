# -*- coding: utf-8 -*-
"""⑦ generator 拆包 · 表格处理（列表型/标签值型占位、份数复制、附表9设备行）。"""
import copy
import re

from .gen_common import (HAVE_DOCX, Document, qn, TABLE_ROW_VALUE_PH, TPL_KEY_MAP)  # noqa: F401
from .gen_text import _clean_tag, set_cell_text

__all__ = [
    "_row_is_blank", "_is_list_table", "_header_cells", "_fill_list_table",
    "_dedup_cells", "_fill_label_table", "_personnel_count",
    "_post_process_tables", "_extract_tpl_equip_rows", "_fill_equip_from_tpl",
    "_duplicate_tables_by_contract",
]


def _row_is_blank(row):
    return all((c.text or "").strip() == "" for c in row.cells)


def _is_list_table(table):
    """列表型：首行含『序号』列；或首行全非空且行数>1。标签值型：首行存在空值格。"""
    rows = table.rows
    if not rows:
        return False
    first = [c.text.strip() for c in rows[0].cells]
    if any("序号" in t for t in first if t):
        return True
    return len(rows) > 1 and all(first) and not _row_is_blank(rows[1])


def _header_cells(table):
    return [c.text.strip() for c in table.rows[0].cells]


def _fill_list_table(table, rows_target=None, tag_map=None):
    """列表型：表头保留；数据行空值格填【列头键】；序号列自动编号；行数按 rows_target 增删。"""
    header = _header_cells(table)
    filled = 0
    rows = list(table.rows)
    data_rows = rows[1:] if len(rows) > 1 else []
    ellipsis = [r for r in data_rows if "…" in "".join(c.text for c in r.cells)]
    keep = [r for r in data_rows if r not in ellipsis]

    def ph_key(h):
        k = _clean_tag(h)
        if tag_map:
            k = tag_map.get(k, k)
        return k

    # 已有数据行占位
    for ri, r in enumerate(keep):
        for j, c in enumerate(r.cells):
            if (c.text or "").strip() != "":
                continue
            if j < len(header) and header[j]:
                if "序号" in header[j]:
                    set_cell_text(c, str(ri + 1))
                else:
                    k = ph_key(header[j])
                    if k:
                        set_cell_text(c, "【%s】" % k)
                        filled += 1
    # 行数动态增减
    if rows_target is not None and len(keep) != rows_target:
        anchor = keep[-1]._tr if keep else table.rows[0]._tr
        if len(keep) < rows_target:
            src = keep[-1] if keep else table.rows[0]
            for idx in range(len(keep) + 1, rows_target + 1):
                new_tr = copy.deepcopy(src._tr)
                anchor.addnext(new_tr)
                anchor = new_tr
                new_row = table.rows[table._tbl.index(new_tr)]
                for j, c in enumerate(new_row.cells):
                    if j < len(header) and header[j]:
                        if "序号" in header[j]:
                            set_cell_text(c, str(idx))
                        else:
                            k = ph_key(header[j])
                            if k:
                                set_cell_text(c, "【%s】" % k)
                                filled += 1
        else:
            for r in keep[rows_target:]:
                table._tbl.remove(r._tr)
    return filled


def _dedup_cells(row):
    """python-docx 对合并单元格（gridSpan/vMerge）返回重复引用，按元素去重。"""
    out = []
    seen = set()
    for c in row.cells:
        if id(c._tc) not in seen:
            seen.add(id(c._tc))
            out.append(c)
    return out


def _fill_label_table(table, tag_map=None):
    """标签值型：行内『标签→空值格』配对（非空格=标签，空格=该标签的值），
    空值格填【标签键】。规则：
      - 注：/附： 开头 → 不参与（注意仅带冒号，避免误伤『注册地址』等）；
      - 纯数字（序号）不更新标签；
      - 证书类行（首格含『证书』）的第 2 列（序号列）空值不填，留人工补序号；
      - 证书名称及证书编号（简历表）→ 填【证书名称】【证书编号】双占位（模板库同款键）；
      - 键映射值以「图片：」开头 → 填【图片：xxx】（图片占位值格）；
      - TABLE_ROW_VALUE_PH 命中 → 整行值格替换为占位（模板库整行占位方式）。"""
    filled = 0
    for row in table.rows:
        cells = _dedup_cells(row)
        if not cells:
            continue
        first = (cells[0].text or "").strip()
        row_rule = None
        for tag, rr in TABLE_ROW_VALUE_PH.items():
            if first.startswith(tag):
                row_rule = rr
                break
        if row_rule:
            pat, repl = row_rule
            targets = cells[1:] if len(cells) > 1 else [cells[0]]
            for c in targets:
                if re.search(pat, c.text or ""):
                    set_cell_text(c, repl)
                    filled += 1
                    break
            continue
        current_tag = None
        for ci, c in enumerate(cells):
            t = (c.text or "").strip()
            if t:
                if t.startswith("注：") or t.startswith("注:") or t.startswith("附：") or t.startswith("附:"):
                    current_tag = None
                elif not t.isdigit():
                    current_tag = t
                continue
            if not current_tag:
                continue
            if ci == 1 and "证书" in current_tag:
                continue                      # 证书行序号列空值留人工
            key = _clean_tag(current_tag)
            if not key:
                continue
            if tag_map:
                key = tag_map.get(key, key)
            if key == "证书名称" and "证书编号" in current_tag:
                set_cell_text(c, "【证书名称】【证书编号】")
            else:
                set_cell_text(c, "【%s】" % key)
            filled += 1
    return filled


def _personnel_count(material):
    """实际需要的监理人员数（简历表份数/配备表行数口径）。
    范本 v1.2：优先读素材清单「监理人员配置口径.简历表份数/合计」；
    无口径字段时回退 personnel 数组长度（向下兼容）。"""
    cfg = material.get("监理人员配置口径") or {}
    if isinstance(cfg, dict):
        for k in ("简历表份数", "合计"):
            if cfg.get(k):
                try:
                    return max(int(cfg[k]), 1)
                except (TypeError, ValueError):
                    pass
    return max(len(material.get("personnel", [])), 1)


def _post_process_tables(doc, material, ctx_map):
    """占位填充：行路由 → 列表型/标签值型（占位键名统一走 TPL_KEY_MAP，参照模板库）。
    表格语义按「前文标题上下文」路由（表标题在表外段落，不在表首行）。"""
    stats = {}
    personnel = material.get("personnel", [])
    performance = material.get("performance", [])
    n_personnel = _personnel_count(material)
    for ti, table in enumerate(doc.tables):
        ctx = ctx_map.get(table._tbl, "")
        if _is_list_table(table):
            rows_target = None
            if "监理人员配备" in ctx:
                rows_target = n_personnel
            elif "已完成工程" in ctx and "情况表" not in ctx:
                rows_target = max(len(performance), 1)
            elif "正在监理工程" in ctx and "情况表" not in ctx:
                rows_target = 1
            stats[ti] = _fill_list_table(table, rows_target=rows_target, tag_map=TPL_KEY_MAP)
        else:
            stats[ti] = _fill_label_table(table, tag_map=TPL_KEY_MAP)
    return stats


def _extract_tpl_equip_rows(tpl_path):
    """从模板库资格证明及辅助资料表.docx 提取附表9 仪器设备表数据行（tr 元素列表）。
    企业固定设备数据（范本 v1.2：用户确认直接写入模板，无需改动）。"""
    if not HAVE_DOCX:
        return []
    try:
        tdoc = Document(str(tpl_path))
    except Exception:
        return []
    for t in tdoc.tables:
        first = "".join(c.text for c in t.rows[0].cells)
        if "仪器名称" in first:
            return [r._tr for r in t.rows[1:]
                    if any((c.text or "").strip() for c in r.cells)]
    return []


def _fill_equip_from_tpl(doc, ctx_map, tpl_rows):
    """附表9 仪器设备表：表头保留契约原文，数据行整体替换为模板库范本数据行。
    在 _post_process_tables 之后调用（先按契约空行处理，再整体替换为企业固定设备）。"""
    if not tpl_rows:
        return 0
    n = 0
    for table in doc.tables:
        ctx = ctx_map.get(table._tbl, "")
        first = "".join(c.text for c in table.rows[0].cells)
        if "仪器" not in ctx and "仪器名称" not in first:
            continue
        rows = list(table.rows)
        header_tr = rows[0]._tr
        for r in rows[1:]:
            table._tbl.remove(r._tr)
        anchor = header_tr
        for tr in tpl_rows:
            new_tr = copy.deepcopy(tr)
            anchor.addnext(new_tr)
            anchor = new_tr
            n += 1
    return n


def _duplicate_tables_by_contract(doc, tbl_meta, material, ctx_map):
    """
    动态语义②——份数复制（按契约项块范围路由，不依赖表内标题文字）：
      - F06d 附表3 已完成工程情况表：每个业绩一张（复制 len(performance) 份）；
      - F06i 附表8 监理人员简历表：每名人员一张（复制份数 = 实际需要的监理人员数，
        口径 = 素材清单「监理人员配置口径.简历表份数」，无则回退 personnel 长度）。
    复制到目标 doc 中对应表格之后；复制表同步登记上下文（ctx_map），
    保证后续占位路由正确。
    """
    personnel = material.get("personnel", [])
    performance = material.get("performance", [])
    for node, item_id in tbl_meta:
        if item_id == "F06d":
            n = max(len(performance), 1)
        elif item_id == "F06i":
            n = _personnel_count(material)
        else:
            continue
        ctx = ctx_map.get(node, "")
        anchor = node
        for _ in range(n - 1):
            new_tbl = copy.deepcopy(node)
            anchor.addnext(new_tbl)
            anchor = new_tbl
            ctx_map[new_tbl] = ctx
