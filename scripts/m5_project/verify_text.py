# -*- coding: utf-8 -*-
"""⑦ generator · 代码硬校验（M5 v4，2026-10-10）。

用户规则（v4 定稿）：项目模板以**企业模板为基底**（结构/格式/布局按模板），
文字以招标原文投标文件格式为准更新（差异对齐：update=原文文字 / keep=保留
模板文字 / delete=删除；only_template 默认待人工裁决）。本模块用**代码（确定性）**
对生成的项目模板做文字一致性校验，不依赖 AI/agent。

**规则共享（单一权威）**：生成器允许的唯一文字改动是把「填写位置/提示语」
替换为占位符【xxx】/【图片：xxx】（占位填充源=素材清单），规则表全部在
gen_common（GLOBAL_PH / PARA_LABEL_RULES / ROW_RULES / TABLE_ROW_VALUE_PH /
DATE_PH_PAT / SME_PH_PATTERNS / COVER_NAME_PAT / COVER_NO_PAT / STRAY_STAR_TEXT）。
校验器对招标原文应用**同一套规则**后做比对：

1. **段落**：原文段落（应用段规则 → 占位归一 ⟦PH⟧/⟦IMG⟧ → 固定片段链）与
   模板段落固定片段链**完全相等**（逐字、顺序一致）；拆行/图片占位段不影响链；
   **keep 豁免**：差异清单中人工裁决「keep=保留企业模板文字」的固定文字，
   允许作为模板额外段落存在（不报混入）。
2. **表格**：行对齐校验——原文行与模板行按结构指纹匹配（允许按业绩/人员数
   复制行、允许原文空值格被占位/设备数据填充），非空格固定文字逐字一致；
   模板不得出现原文没有的结构行（keep 豁免项除外）。
3. **章节标题跳过**：F01 起点为「第X章 投标文件格式」标题段 → 跳过不比对
   （与生成器共用 gen_common.skip_chapter_head）。

返回 {"结论", "块数", "比对片段", "问题":[...]}；有任一问题 → 结论=不通过。
"""
import re
from pathlib import Path

from .gen_common import (COVER_NAME_PAT, COVER_NO_PAT, DATE_PH_FILES, DATE_PH_PAT,
                         GLOBAL_PH, HAVE_DOCX, Document, PARA_LABEL_RULES,
                         ROW_RULES, SME_PH_PATTERNS, STRAY_STAR_TEXT,
                         TABLE_ROW_VALUE_PH, qn, skip_chapter_head)
from .gen_text import _para_text

__all__ = ["norm_ph", "split_fixed", "apply_para_rules", "apply_cell_rules",
           "verify_docx_vs_source", "verify_contract_text"]


# 占位区域正则：
#  - 连续空白/全角空格/下划线（填写位置）
#  - 【xxx】/【图片：xxx】（生成器占位符）
#  - （项目名称）（招标人名称）（姓名）等提示占位（GLOBAL_PH 反向）
_PH_PAT = re.compile(
    r"【[^】]*】"                     # 生成器占位符
    r"|[\s\u3000_＿]{2,}"            # 连续空白/下划线填写位置（≥2 字符）
    r"|（(?:项目名称|投标人名称|招标人名称|姓名|姓 名|单位名称|采购人名称)）"
    r"|（[\s\u3000]{1,6}）"          # 空括号填写位置
    r"|_+＿+"
)


def norm_ph(text):
    """把占位区域归一为 ⟦PH⟧；图片占位 ⟦IMG⟧。固定文字原样保留。"""
    if not text:
        return text or ""
    out = []
    pos = 0
    for m in _PH_PAT.finditer(text):
        out.append(text[pos:m.start()])
        seg = m.group(0)
        out.append("⟦IMG⟧" if seg.startswith("【图片") else "⟦PH⟧")
        pos = m.end()
    out.append(text[pos:])
    return "".join(out)


def split_fixed(text):
    """按占位区域切分，返回固定片段序列（跳过空片段）。"""
    norm = norm_ph(text)
    parts = re.split(r"⟦(?:PH|IMG)⟧", norm)
    return [p for p in parts if p]


def apply_para_rules(text, fname, project_name=""):
    """对招标原文段落文本应用生成器同款段规则（规则共享，单一权威）：
    GLOBAL_PH → PARA_LABEL_RULES → DATE_PH → 封面占位 → 中小企业声明函占位。"""
    t = text or ""
    for old, new in GLOBAL_PH:
        t = t.replace(old, new)
    for pattern, repl in PARA_LABEL_RULES.get(fname, []):
        if re.search(pattern, t):
            t = re.sub(pattern, repl, t)
    if fname in DATE_PH_FILES and DATE_PH_PAT.match(t):
        t = "【日期】"
    if fname == "封面.docx":
        m = COVER_NAME_PAT.search(t)
        if m and m.group(2).strip() and "【项目名称】" not in t and project_name \
                and project_name in m.group(2).strip():
            t = t.replace(m.group(2).strip(), "【项目名称】")
        m2 = COVER_NO_PAT.search(t)
        if m2 and m2.group(2) and not m2.group(2).startswith("【") and "【项目编号】" not in t:
            t = t.replace(m2.group(2), "【项目编号】")
    if fname == "中小企业声明函.docx" and project_name and project_name in t:
        t = t.replace(project_name, "【项目名称】")
        for old, new in SME_PH_PATTERNS:
            if re.search(old, t):
                t = re.sub(old, new, t)
    return t


def apply_cell_rules(text, ctx=""):
    """对招标原文单元格文本应用生成器同款单元格规则：
    GLOBAL_PH → ROW_RULES（按表前文）→ TABLE_ROW_VALUE_PH。"""
    t = text or ""
    for old, new in GLOBAL_PH:
        t = t.replace(old, new)
    for kw, rr in ROW_RULES.items():
        if kw in ctx:
            for _tag, subs in rr.items():
                for pattern, repl in subs:
                    if re.search(pattern, t):
                        t = re.sub(pattern, repl, t)
            break
    for _tag, (pat, repl) in TABLE_ROW_VALUE_PH.items():
        if re.search(pat, t):
            t = re.sub(pat, repl, t)
    return t


def _row_fingerprint(cells):
    """行结构指纹 = 非空单元格占位归一文本元组（复制行/全空行指纹可重复）。"""
    return tuple(c for c in cells if c.strip())


def _row_match_score(srow, trow):
    """位置对应行匹配：原文非空格（占位归一后非空/非占位）必须与模板同位置
    逐字一致；原文空格值格（填写位置）允许模板任意填充（占位/设备数据）。"""
    if len(trow) < len(srow):
        return False
    for ci in range(len(srow)):
        s_cell = norm_ph(srow[ci])
        if not s_cell.strip() or s_cell.strip() == "⟦PH⟧":
            continue
        t_cell = norm_ph(trow[ci]) if ci < len(trow) else ""
        if s_cell != t_cell:
            return False
    return True


def _table_match_score(srows, trows):
    """表格指纹匹配：前 2 行位置匹配即视为同一表格（表头行足够判别；
    生成器复制表/合并表会改变表格序列，不能按索引对应）。"""
    if not srows or not trows:
        return False
    for srow, trow in zip(srows[:2], trows[:2]):
        if not _row_match_score(srow, trow):
            return False
    return True


def _table_overlap(srows, trows):
    """表格行重合度（0~1）：原文行在模板行中位置匹配的比例。
    附表 2/3/4/5 表头相似但正文行不同，用重合度选最优对应，避免表头歧义错位。"""
    if not srows:
        return 0.0
    matched = 0
    used = set()
    for srow in srows:
        for ti, trow in enumerate(trows):
            if ti in used:
                continue
            if _row_match_score(srow, trow):
                matched += 1
                used.add(ti)
                break
    return matched / len(srows)


def _iter_docx_text(doc):
    """按 body 顺序输出 docx 文本序列：(段落文本, None) / (None, 表格行列表)。"""
    seq = []
    for child in doc.element.body.iterchildren():
        if child.tag == qn("w:p"):
            seq.append(("para", _para_text(child), None))
        elif child.tag == qn("w:tbl"):
            from docx.table import Table
            tbl = Table(child, doc)
            rows = []
            for row in tbl.rows:
                cells = []
                seen = set()
                for cell in row.cells:
                    if id(cell._tc) not in seen:
                        seen.add(id(cell._tc))
                        cells.append(cell.text)
                rows.append(cells)
            seq.append(("tbl", None, rows))
    return seq


def _iter_source_text(blocks, lo, hi, doc, fname="", project_name="",
                      skip_chapter_head=True):
    """从招标原文块 [lo,hi] 输出文本序列（应用生成器规则 + 占位归一）。

    返回 (seq, src_rows)：seq 段落链文本序列；src_rows 表格行列表（按出现顺序）。
    """
    seq = []
    tables = []
    last_para = ""
    for i in range(lo, hi + 1):
        if i < 0 or i >= len(blocks):
            continue
        blk = blocks[i]
        if blk["type"] == "para":
            t = _para_text(blk["node"])
            if skip_chapter_head and i == lo and re.search(
                    r"第[一二三四五六七八九十百]+章\s*(投标文件格式|响应文件格式)",
                    re.sub(r"\s+", "", t)):
                continue
            if t.strip() == STRAY_STAR_TEXT:      # 孤立*段生成器删除，跳过
                continue
            if t.strip():
                seq.append(("para", apply_para_rules(t, fname, project_name), None))
                last_para = t
        else:
            from docx.table import Table
            tbl = Table(blk["node"], doc)
            rows = []
            for row in tbl.rows:
                cells = []
                seen = set()
                for cell in row.cells:
                    if id(cell._tc) not in seen:
                        seen.add(id(cell._tc))
                        cells.append(apply_cell_rules(cell.text, last_para))
                rows.append(cells)
            tables.append(rows)
    return seq, tables


def _verify_table(src_rows, tpl_rows, problems, tbl_no=0):
    """表格行对齐校验（结构保留 + 固定文字逐字一致）。

    - 原文行按序在模板行中找指纹匹配（允许按业绩/人员数复制行）；
    - 匹配行逐格比对：原文空值格（占位区域）允许被占位/设备数据填充，
      非空格固定文字（占位归一后）必须逐字一致；
    - 原文行找不到匹配 → 缺失；模板行未匹配且指纹异于所有原文行 → 混入。
    （原文全空行可匹配模板任意行：设备/占位填充行由生成器合法扩展；
     生成器排版收敛允许删除表格空白行，原文空行仍可匹配模板剩余行。）
    """
    n_tbl_ok = 0
    used = set()

    for si, srow in enumerate(src_rows):
        # 在模板中找第一个未使用且位置匹配的行（原文空格值格允许模板任意填充）
        match = None
        for ti, trow in enumerate(tpl_rows):
            if ti in used:
                continue
            if _row_match_score(srow, trow):
                match = ti
                break
        if match is None:
            if all(not (c or "").strip() for c in srow):
                continue                          # 原文空行：生成器排版收敛允许删除，豁免
            problems.append({
                "位置": "表格#%d 行#%d" % (tbl_no, si), "原文": "、".join(srow)[:120], "模板": "",
                "说明": "原文表格行在模板中缺失（结构丢失或内容被改动）",
            })
            continue
        used.add(match)
        # 逐格比对：原文非空格固定文字必须与模板一致（占位归一后）
        trow = tpl_rows[match]
        for ci in range(min(len(srow), len(trow))):
            s_cell = norm_ph(srow[ci])
            t_cell = norm_ph(trow[ci])
            if not s_cell.strip() or s_cell.strip() == "⟦PH⟧":
                continue                          # 原文空值格允许填充
            if s_cell != t_cell:
                problems.append({
                    "位置": "表格#%d 行#%d 列#%d" % (tbl_no, si, ci),
                    "原文": s_cell[:80], "模板": t_cell[:80],
                    "说明": "表格单元格固定文字不一致（原文应为 %r，模板为 %r）"
                            % (s_cell[:60], t_cell[:60]),
                })
        n_tbl_ok += 1
    # 模板多余行：与任一原文行位置匹配（复制行，业绩/人员数扩展）→ 豁免；
    # keep 豁免：行指纹完全等于 keep 固定文字（人工裁决保留的模板文字）→ 豁免；
    # 否则混入
    for ti, trow in enumerate(tpl_rows):
        if ti in used:
            continue
        if any(_row_match_score(srow, trow) for srow in src_rows):
            continue                              # 复制行
        if keep_texts and all(any(norm_ph(c or "") == kt for kt in keep_texts)
                              for c in trow if (c or "").strip()):
            continue                              # keep 豁免行（人工裁决保留）
        problems.append({
            "位置": "表格#%d 行#%d" % (tbl_no, ti), "原文": "", "模板": "、".join(trow)[:120],
            "说明": "模板存在原文没有的表格行（keep 豁免项除外；疑似混入企业模板内置内容）",
        })
    return n_tbl_ok


def verify_docx_vs_source(docx_path, blocks, lo, hi, fname="", project_name="",
                          skip_chapter_head=True, doc=None, keep_texts=None):
    """文字一致性硬校验：项目模板 docx ↔ 招标原文块 [lo,hi]（v4）。

    keep_texts：差异清单中人工裁决「keep」的企业模板固定文字（占位归一后）；
    模板中与之等价的多余段落/表格行豁免（不报混入）——keep=人工确定保留
    企业模板文字（模板有、原文无的固定文字）。
    返回 {"结论", "块数", "比对片段", "问题":[...]}。
    """
    if not HAVE_DOCX:
        raise GenError("校验器依赖 python-docx")
    keep_texts = [norm_ph(t or "") for t in (keep_texts or [])]
    docx = Document(str(docx_path))
    tpl_seq = _iter_docx_text(docx)
    src_seq, src_tables = _iter_source_text(blocks, lo, hi, doc, fname, project_name,
                                            skip_chapter_head=skip_chapter_head)

    problems = []
    # 段落链：完全相等（逐字、顺序；keep 豁免）
    src_fixed = []
    for kind, t, _rows in src_seq:
        src_fixed.extend(split_fixed(t))
    tpl_fixed = []
    for kind, t, _rows in tpl_seq:
        tpl_fixed.extend(split_fixed(t))
    n = min(len(src_fixed), len(tpl_fixed))
    for i in range(n):
        if src_fixed[i] != tpl_fixed[i]:
            problems.append({
                "位置": "段落固定片段#%d" % i,
                "原文": src_fixed[i][:80], "模板": tpl_fixed[i][:80],
                "说明": "招标原文与项目模板固定文字不一致（原文应为 %r，模板为 %r）"
                        % (src_fixed[i][:60], tpl_fixed[i][:60]),
            })
    if len(src_fixed) > len(tpl_fixed):
        problems.append({
            "位置": "段落固定片段#%d..%d" % (n, len(src_fixed) - 1),
            "原文": "、".join(src_fixed[n:])[:120], "模板": "",
            "说明": "模板缺少 %d 段招标原文固定文字（疑似内容丢失）" % (len(src_fixed) - n),
        })
    if len(tpl_fixed) > len(src_fixed):
        extra = [t for t in tpl_fixed[n:] if t not in keep_texts]
        if extra:
            problems.append({
                "位置": "段落固定片段#%d..%d" % (n, len(tpl_fixed) - 1),
                "原文": "", "模板": "、".join(extra)[:120],
                "说明": "模板多出 %d 段非原文固定文字（keep 豁免项除外；疑似混入企业模板内置内容）"
                        % len(extra),
            })
    # 表格：表格级最优匹配对齐（复制表/合并表改变序列；表头相似表用行重合度区分）
    tpl_tables = [rows for kind, _t, rows in tpl_seq if kind == "tbl"]
    used_tables = set()
    for si, srows in enumerate(src_tables):
        best, best_score = None, 0.0
        for ti, trows in enumerate(tpl_tables):
            if ti in used_tables:
                continue
            sc = _table_overlap(srows, trows)
            if sc > best_score:
                best, best_score = ti, sc
        if best is None or best_score < 0.5:
            problems.append({
                "位置": "表格#%d" % si, "原文": "（存在表格，首行 %r）" % (srows[0] if srows else ""),
                "模板": "",
                "说明": "招标原文表格在模板中缺失（结构丢失或内容被改动）",
            })
            continue
        used_tables.add(best)
        _verify_table(srows, tpl_tables[best], problems, tbl_no=si)
    for ti, trows in enumerate(tpl_tables):
        if ti in used_tables:
            continue
        if any(_table_overlap(srows, trows) >= 0.5 for srows in src_tables):
            continue                              # 复制表（简历表按人员/业绩表按数量）
        problems.append({
            "位置": "表格#%d" % ti, "原文": "",
            "模板": "（存在表格，首行 %r）" % (trows[0] if trows else ""),
            "说明": "模板存在原文没有的表格（疑似混入企业模板内置内容）",
        })

    ok = not problems
    return {"结论": "通过" if ok else "不通过",
            "块数": len(src_seq), "比对片段": len(src_fixed),
            "问题": problems[:50]}


def verify_contract_text(ent, project, out_dir, source_path, contract, material=None,
                         gen_map=None, diff_path=None):
    """对生成的全部 docx 执行文字一致性硬校验（V5：无差异清单驱动，纯深拷贝比对）。

    gen_map: {文件: [契约项...]}——与 gen_main merged 一致；
    by_id 取自 contract['格式文件']；跳过未定位块范围。
    diff_path: 保留兼容参数（V5 不使用；项目模板文字=招标原文深拷贝，不允许豁免）。
    返回 {"结论", "文件":[{文件, 结论, 问题}]}。
    """
    from .gen_blocks import _extract_blocks
    blocks, _doc = _extract_blocks(source_path)
    project_name = str((material or {}).get("project", "") or "")
    by_id = {it.get("id"): it for it in contract["格式文件"]}
    keep_by_file = {}
    if diff_path and Path(diff_path).is_file():
        data = _read_json_plain(diff_path)
        for d in (data.get("差异") or []):
            if d.get("类别") == "only_template" and d.get("建议") == "keep":
                keep_by_file.setdefault(d.get("文件", ""), []).append(d.get("模板") or "")
    files = []
    for fname, ids in (gen_map or {}).items():
        items = [by_id[i] for i in ids if i in by_id]
        valid = [it for it in items if it.get("块范围")]
        if not valid:
            files.append({"文件": fname, "结论": "跳过", "问题": ["契约未定位块范围"]})
            continue
        lo = min(it.get("块范围", [0])[0] for it in valid)
        hi = max(it.get("块范围", [0])[-1] for it in valid)
        # 章节标题不拷贝（与生成器共用 skip_chapter_head，单一权威）
        lo = skip_chapter_head(blocks, lo)
        p = Path(out_dir) / fname
        if not p.is_file():
            files.append({"文件": fname, "结论": "不通过", "问题": ["文件不存在"]})
            continue
        r = verify_docx_vs_source(p, blocks, lo, hi, fname=fname,
                                  project_name=project_name, doc=_doc,
                                  keep_texts=keep_by_file.get(fname))
        files.append({"文件": fname, "结论": r["结论"], "问题": r["问题"]})
    allok = all(f["结论"] == "通过" or f["结论"] == "跳过" for f in files)
    return {"结论": "通过" if allok else "不通过", "文件": files}


def _read_json_plain(path):
    """差异清单 JSON 读取（不依赖 _shared 加载器，避免编码耦合）。"""
    try:
        import json
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return {}
