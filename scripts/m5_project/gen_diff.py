# -*- coding: utf-8 -*-
"""M5 项目模板 · 内容校验差异清单（D16–D20 落地）。

职责
----
项目模板制作依据三：①招标解析内容契约 ②素材清单 ③企业模板库对应模板。
引用企业模板后必须做内容校验：把「企业模板 docx 的非占位文本」与
「招标解析内容契约（原文块）」逐段/逐格对比，产出差异清单 → 用户决策
（update=用契约文本 / keep=保留模板文本）→ 生成时按决策应用。
企业模板库原模板始终保留不动。

判定规则（与用户定稿一致）：
  - 模板文本含【xxx】占位符 → 占位区，不属内容差异（跳过并标注）；
  - 契约文本含下划线空白（待填区）而模板已有固定值 → 直接引用模板固定值，
    不属内容差异（placeholder_zone）；
  - 其余实质文本差异 → 内容差异（默认建议 update，用户可改 keep）。

本文件只做确定性文本对比/应用，不改变生成器重建主链路：
生成稿文字默认 100% 契约（update 天然满足）；keep 项由 apply_diff 按
文本锚点把模板文本写回生成稿。
"""
import json
import re
from pathlib import Path

from _shared import core

PLACEHOLDER_RE = re.compile(r"【[^】]+】")
# 下划线空白：连续 2 个及以上 _ 或全角下划线＿＿，或「____」变体
UNDERSCORE_RE = re.compile(r"[_\uFF3F＿]{2,}")


def _norm(text):
    """归一化文本用于对比：去首尾空白、去全角/半角空格、去换行。"""
    return re.sub(r"[\s\u3000]+", "", text or "").strip()


def _is_placeholder_zone(text):
    """占位区：模板含【】占位，或契约该处为下划线空白（模板固定值直接引用）。"""
    if PLACEHOLDER_RE.search(text or ""):
        return True
    if UNDERSCORE_RE.search(_norm(text or "")):
        return True
    return False


def _doc_para_texts(doc):
    return [p.text or "" for p in doc.paragraphs]


def _doc_table_texts(doc):
    """表格单元格文本 → [[(行, 列, 文本)], ...]。"""
    out = []
    for ti, t in enumerate(doc.tables):
        for ri, row in enumerate(t.rows):
            for ci, cell in enumerate(row.cells):
                out.append((ti, ri, ci, cell.text or ""))
    return out


def _contract_block_texts(blocks, span):
    """从招标文件原文块 [s,e] 提取文本序列：
    段落文本列表 + 表格单元格 (表序, 行, 列, 文本) 列表。"""
    from .gen_text import _para_text
    paras, cells = [], []
    ti = 0
    for i in range(span[0], span[1] + 1):
        blk = blocks[i]
        if blk["type"] == "para":
            t = _para_text(blk["node"])
            if t and t.strip():
                paras.append(t)
        else:
            from docx.oxml.ns import qn
            for ri, r in enumerate(blk["node"].iter(qn("w:tr"))):
                for ci, c in enumerate(r.iter(qn("w:tc"))):
                    txt = "".join(t.text or "" for t in c.iter(qn("w:t")))
                    cells.append((ti, ri, ci, txt))
            ti += 1
    return paras, cells


def _match_template_item(tpl_texts, target):
    """文本锚点匹配：返回与 target 归一化等价的模板条目索引；无则 -1。"""
    tgt = _norm(target)
    for i, t in enumerate(tpl_texts):
        if tgt and _norm(t) == tgt:
            return i
    return -1


def diff_template_vs_contract(tpl_path, blocks, span, item_id, file_name):
    """企业模板 docx vs 契约块 [s,e] 内容校验 → 差异项列表。

    返回 [{文件, 契约项, 位置, 模板, 契约, 类别, 建议}, ...]
    类别：content_diff / only_template / only_contract / placeholder_zone
    建议：update（默认）/ keep（模板已有固定值可直接引用）
    """
    from docx import Document
    tpl_doc = Document(str(tpl_path))
    tpl_paras = _doc_para_texts(tpl_doc)
    tpl_cells = _doc_table_texts(tpl_doc)
    con_paras, con_cells = _contract_block_texts(blocks, span)

    diffs = []
    # 段落级对比：优先索引对齐（模板第 i 段 vs 契约第 i 段），
    # 索引不可靠时按文本锚点匹配，最后补 only_template/only_contract。
    used = set()
    for i, ctext in enumerate(con_paras):
        if i < len(tpl_paras):
            ttext = tpl_paras[i]
            if _norm(ttext) == _norm(ctext):
                used.add(i)
                continue                     # 等价 → 无差异
            if _is_placeholder_zone(ttext) or _is_placeholder_zone(ctext):
                used.add(i)
                diffs.append({"文件": file_name, "契约项": item_id,
                              "位置": "段落%d" % i, "模板": ttext, "契约": ctext,
                              "类别": "placeholder_zone", "建议": "keep"})
                continue
            # 同位置不同文本 → 实质内容差异
            used.add(i)
            diffs.append({"文件": file_name, "契约项": item_id,
                          "位置": "段落%d" % i, "模板": ttext, "契约": ctext,
                          "类别": "content_diff", "建议": "update"})
            continue
        # 契约段超出模板段落数：锚点匹配兜底
        j = next((k for k, t in enumerate(tpl_paras)
                  if k not in used and _norm(t) == _norm(ctext)), -1)
        if j >= 0:
            used.add(j)
            continue
        if _is_placeholder_zone(ctext):
            diffs.append({"文件": file_name, "契约项": item_id,
                          "位置": "段落%d（契约）" % i, "模板": "",
                          "契约": ctext, "类别": "placeholder_zone",
                          "建议": "keep"})
            continue
        diffs.append({"文件": file_name, "契约项": item_id,
                      "位置": "段落%d" % i, "模板": "",
                      "契约": ctext, "类别": "only_contract",
                      "建议": "update"})
    # 模板有、契约无（未消费的模板段）
    for j, ttext in enumerate(tpl_paras):
        if j in used or not ttext or not ttext.strip():
            continue
        if _is_placeholder_zone(ttext):
            diffs.append({"文件": file_name, "契约项": item_id,
                          "位置": "模板段落%d" % j, "模板": ttext, "契约": "",
                          "类别": "placeholder_zone", "建议": "keep"})
            continue
        diffs.append({"文件": file_name, "契约项": item_id,
                      "位置": "模板段落%d" % j, "模板": ttext, "契约": "",
                      "类别": "only_template", "建议": "keep"})
    # 表格单元格对比（同一张表内按行/列对齐：模板网格结构为准）
    for (ti, ri, ci, ctext) in con_cells:
        j = next((k for k, item in enumerate(tpl_cells)
                  if item[1] == ri and item[2] == ci), -1)
        if j < 0:
            continue                        # 模板无此格（动态增行）→ 不算差异
        ttext = tpl_cells[j][3]
        if _norm(ttext) == _norm(ctext):
            continue                        # 等价 → 无差异
        if _is_placeholder_zone(ttext) or _is_placeholder_zone(ctext):
            continue                        # 占位/待填区 → 模板固定值直接引用
        diffs.append({"文件": file_name, "契约项": item_id,
                      "位置": "表%d行%d列%d" % (ti, ri, ci), "模板": ttext,
                      "契约": ctext, "类别": "content_diff",
                      "建议": "update"})
    return diffs


def write_diff_manifest(diffs, project, out_dir):
    """差异清单落盘：.md（人读）+ .json（机读/apply 用）。返回 (md, json) 路径。"""
    md_lines = ["# 内容校验差异清单（企业模板 vs 招标解析内容契约）", "",
                "- 项目：%s ｜ 生成时间：%s" % (project, core.now_iso()), "",
                "- 说明：项目模板制作引用企业模板后做内容校验；本清单列出非占位内容差异。",
                "- 决策方式：**update**=用解析契约文本更新（默认）；**keep**=保留企业模板文本。",
                "- 修改决策：直接编辑 %s.json 中对应项『建议』字段后，再运行 proj-gen --apply-diff 应用。" % "差异清单",
                ""]
    stats = {"content_diff": 0, "only_template": 0, "only_contract": 0,
             "placeholder_zone": 0}
    cur_file = None
    for d in diffs:
        if d["文件"] != cur_file:
            md_lines.append("## %s" % d["文件"])
            cur_file = d["文件"]
        stats[d["类别"]] = stats.get(d["类别"], 0) + 1
        md_lines.append("- [%s] %s ｜ 建议：%s" % (d["类别"], d["位置"], d["建议"]))
        if d["模板"]:
            md_lines.append("  模板：%s" % (d["模板"][:80]))
        if d["契约"]:
            md_lines.append("  契约：%s" % (d["契约"][:80]))
    md_lines.append("")
    md_lines.append("---")
    md_lines.append("合计差异：%d 项（内容差异 %d ｜ 仅模板 %d ｜ 仅契约 %d ｜ 占位/待填区跳过 %d）"
                    % (len(diffs), stats["content_diff"], stats["only_template"],
                       stats["only_contract"], stats["placeholder_zone"]))
    md_path = out_dir / "差异清单.md"
    json_path = out_dir / "差异清单.json"
    md_path.write_text("\n".join(md_lines), encoding="utf-8")
    json_path.write_text(json.dumps({"项目": project, "生成时间": core.now_iso(),
                                     "差异": diffs}, ensure_ascii=False, indent=2),
                         encoding="utf-8")
    return md_path, json_path


def load_decisions(diff_json_path):
    """读差异清单（含用户修改的『建议』），返回 {keep: [差异项], update: [差异项]}。"""
    data = core.read_json(diff_json_path, None) or {}
    keep, update = [], []
    for d in data.get("差异", []) or []:
        (keep if d.get("建议", "update") == "keep" else update).append(d)
    return keep, update


def apply_keep_to_docx(docx_path, keep_items):
    """把用户决策为 keep 的项按文本锚点写回生成稿（保留模板文本/固定值）。

    keep 项定位：优先按『模板』全文锚点（段落等价匹配/单元格等价匹配）。
    返回应用的项数（锚点未命中记入 missing）。
    """
    from docx import Document
    doc = Document(str(docx_path))
    applied, missing = 0, []
    for d in keep_items:
        tpl_txt = d.get("模板") or ""
        if not tpl_txt or d.get("类别") == "only_contract":
            continue                     # 仅契约有 → 无模板文本可写回
        # 单元格项：位置「表T行R列C」→ 直接索引写回
        m = re.match(r"表(\d+)行(\d+)列(\d+)", d.get("位置", ""))
        if m:
            ti, ri, ci = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if ti < len(doc.tables) and ri < len(doc.tables[ti].rows) \
                    and ci < len(doc.tables[ti].rows[ri].cells):
                cell = doc.tables[ti].rows[ri].cells[ci]
                if _norm(cell.text) != _norm(tpl_txt):
                    from .gen_text import set_cell_text
                    set_cell_text(cell, tpl_txt)
                    applied += 1
            else:
                missing.append(d.get("位置", ""))
            continue
        # 段落项：优先按位置索引（模板/生成稿段落结构一致），锚点匹配兜底
        m = re.match(r"段落(\d+)", d.get("位置", ""))
        if m and int(m.group(1)) < len(doc.paragraphs):
            p = doc.paragraphs[int(m.group(1))]
            if _norm(p.text) != _norm(tpl_txt):
                from .gen_text import _set_para_text
                _set_para_text(p, tpl_txt)
                applied += 1
            continue
        hit = False
        for p in doc.paragraphs:         # 锚点兜底（索引漂移场景）
            if _norm(p.text) == _norm(tpl_txt):
                hit = True
                break
        if not hit:
            missing.append(d.get("位置", ""))
    doc.save(str(docx_path))
    return applied, missing
