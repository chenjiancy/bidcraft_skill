# -*- coding: utf-8 -*-
"""
bidcraft · M5 项目模板生成器 —— 编排/生成层（确定性文件操作）

一句话职责
----------
把「格式契约（招标文件投标文件格式，一字不差）+ 素材清单（占位符键/行数/份数）
+ 基础模板（样式壳）」动态合成为项目模板 docx 集，落盘 项目级/<项目>/项目模板/，
并登记产物基线（fb.register）。

动态语义（需求对齐 D4/D10/D12）：
  ① 文字以契约为准——所有段落/表格内容从招标文件原文块深拷贝，一字不改；
  ② 素材占位按素材清单增减——简历表按人员份数复制、业绩表按素材行数增减、
     证书页数/行数动态调整，不硬套基础模板固定占位。

本文件只做确定性操作；「哪些契约项生成/跳过、占位键怎么定」等语义判断
集中在下方 RULES 表（可增行），agent 维护，人工可审。

依赖：python-docx（本项目运行环境已装，格式契约解析同款）。
"""

import copy
import glob
import json
import re
from pathlib import Path

from _shared import core
from m_feedback import feedback as fb

try:
    from docx import Document
    from docx.oxml.ns import qn
    HAVE_DOCX = True
except Exception:                                    # pragma: no cover - 环境缺依赖时降级
    HAVE_DOCX = False

GEN_ID = "m5-project-gen"
GEN_VERSION = "v1.0"

# ---------------------------------------------------------------------------
# RULES 表（agent 维护，可增行）——契约项 → 项目模板文件 映射
# kind: build=生成 / skip=不生成（原因见 skip_reason）
# ---------------------------------------------------------------------------
FILE_MAP = [
    {"id": "F01", "file": "封面.docx", "kind": "build", "note": "投标文件封面（含投标文件名称/项目名称）"},
    {"id": "F02", "file": "开标一览表.docx", "kind": "build"},
    {"id": "F03a", "file": "投标函.docx", "kind": "build"},
    {"id": "F03b", "file": "投标函附录.docx", "kind": "build"},
    {"id": "F04a", "file": "法定代表人身份证明.docx", "kind": "build"},
    {"id": "F04b", "file": "授权委托书.docx", "kind": "build"},
    {"id": "F05", "file": "", "kind": "skip", "skip_reason": "技术标（监理大纲）50分，暗标编制，不入商务标项目模板"},
    {"id": "F06a", "file": "资格证明及辅助资料表.docx", "kind": "build", "note": "附表清单说明"},
    {"id": "F06b", "file": "资格证明及辅助资料表.docx", "kind": "build", "note": "附表1 企业组织机构"},
    {"id": "F06c", "file": "资格证明及辅助资料表.docx", "kind": "build", "note": "附表2 已完成工程汇总表（行数=素材业绩数）"},
    {"id": "F06d", "file": "资格证明及辅助资料表.docx", "kind": "build", "note": "附表3 已完成工程情况表（份数=素材业绩数）"},
    {"id": "F06e", "file": "资格证明及辅助资料表.docx", "kind": "build", "note": "附表4 正在监理工程汇总表（无素材→1占位行）"},
    {"id": "F06f", "file": "资格证明及辅助资料表.docx", "kind": "build", "note": "附表5 正在监理工程情况表（无素材→保留1张）"},
    {"id": "F06g", "file": "资格证明及辅助资料表.docx", "kind": "build", "note": "附表6 监理人员资质表（总监证书→图片占位）"},
    {"id": "F06h", "file": "资格证明及辅助资料表.docx", "kind": "build", "note": "附表7 监理人员配备表（行数=素材人员数）"},
    {"id": "F06i", "file": "资格证明及辅助资料表.docx", "kind": "build", "note": "附表8 监理人员简历表（份数=素材人员数）"},
    {"id": "F06j", "file": "资格证明及辅助资料表.docx", "kind": "build", "note": "附表9 拟投入仪器设备表（无素材→保留契约空行）"},
    {"id": "F06k", "file": "资格证明及辅助资料表.docx", "kind": "build", "note": "附表10 奖惩情况"},
    {"id": "F07", "file": "承诺函_项目总监到岗.docx", "kind": "build"},
    {"id": "F08", "file": "投标保证金材料.docx", "kind": "build", "note": "保证金递交说明（附件形式）"},
    {"id": "F09", "file": "基本账户开户许可证承诺函.docx", "kind": "build"},
    {"id": "F10", "file": "", "kind": "skip", "skip_reason": "参考格式（投标保函示范文本），本项目保证金待办理，按需启用"},
    {"id": "F11", "file": "", "kind": "skip", "skip_reason": "参考格式（履约保函），按需启用"},
    {"id": "F12", "file": "", "kind": "skip", "skip_reason": "参考格式（低价风险金保函），按需启用"},
    {"id": "F13", "file": "中小企业声明函.docx", "kind": "build"},
    {"id": "F14", "file": "中小企业声明函.docx", "kind": "build", "note": "划型标准附后（并入同一文件）"},
    {"id": "F15", "file": "", "kind": "skip", "skip_reason": "残疾人福利性单位声明函——本项目素材清单未标记残疾人福利性单位，按需启用"},
]

# 生成文件 → 字体映射（与模板库基础模板保持一致，2026-10-03 实测模板库 10 文件字体分布）
# 仿宋类：公文/声明/承诺（封面、投标函、附录、授权、法代、承诺函）；宋体类：表格为主（资格证明、开标一览表、声明函）
FILE_FONT = {
    "封面.docx": "仿宋",
    "开标一览表.docx": "宋体",
    "投标函.docx": "仿宋",
    "投标函附录.docx": "仿宋",
    "法定代表人身份证明.docx": "仿宋",
    "授权委托书.docx": "仿宋",
    "资格证明及辅助资料表.docx": "宋体",
    "承诺函_项目总监到岗.docx": "仿宋",
    "投标保证金材料.docx": "仿宋",
    "基本账户开户许可证承诺函.docx": "仿宋",
    "中小企业声明函.docx": "宋体",
}

# 段落级全局占位替换（安全集合：仅确认为填空提示的原文模式；固定条款一字不改）
GLOBAL_PH = [
    ("（项目名称）", "【项目名称】"),        # 封面/投标函 提示占位（中小企业声明函已是具体项目名，不匹配）
    ("（投标人名称）", "【投标人名称】"),      # F04a 法定代表人身份证明
    ("（招标人名称）", "【招标人名称】"),      # F04b 授权委托书
    ("（姓名）", "【法定代表人姓名】"),        # F04b 授权委托书
]

# 行路由占位规则：{表格前文标题特征: {行首标签: [(正则, 替换串), ...]}}
# 匹配：表格前文含表特征 → 按行首标签路由 → 值格做正则替换（其余格走通用规则）
ROW_RULES = {
    "开标一览表": {
        "投标总价（人民币）": [(r"报价为\s+", "报价为【投标总价（元）】")],
        "项目总监理工程师": [(r"姓名\s+", "姓名【总监姓名】"), (r"专业\s+", "专业【总监专业】")],
    },
    "投标文件附录": {
        "预付款": [(r"合同价款的\s*/\s*", "合同价款的【预付款比例】/")],
    },
}

# 标签值型表格的列（行首标签）清洗：噪声词 → 移除后作占位键
TAG_NOISE = ["（", "）", "(", ")", "：", ":", "　", " ", "\u3000", "\n", "\t"]

# 简历表等表格：清洗后标签 → 语义化占位键（未映射的用清洗键）
TAG_MAP = {
    "姓名": "人员姓名", "性别": "人员性别", "出生年月": "人员出生年月",
    "最终学历": "人员学历", "政治面貌": "人员政治面貌", "现任职务": "项目职务",
    "技术职称": "人员职称", "聘任时间": "职称聘任时间",
    "居民身份证号码": "人员身份证号码", "证书名称及证书编号": "人员证书及编号",
    "相关专业经历": "人员专业经历", "施工监理主要经历": "人员监理经历",
    "从事施工工作年限": "从事施工工作年限", "从事监理工作年限": "从事监理工作年限",
    "从事设计工作年限": "从事设计工作年限",
}


class GenError(RuntimeError):
    pass


def _clean_tag(tag):
    t = tag
    for ch in TAG_NOISE:
        t = t.replace(ch, "")
    return t.strip()


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


def set_cell_text(cell, text):
    """清空单元格并写入文本（保留首个 run 的 rPr 与段落 pPr）。"""
    p = cell.paragraphs[0]
    runs = p.runs
    if runs:
        runs[0].text = text
        for r in runs[1:]:
            r._element.getparent().remove(r._element)
    else:
        p.add_run(text)


def _replace_text_in_runs(p, old, new):
    """段落文本级替换（保留首 run rPr 与段落 pPr；占位词跨 run 也能命中）。"""
    full = "".join(r.text for r in p.runs)
    if old in full:
        newtext = full.replace(old, new)
        runs = p.runs
        if runs:
            runs[0].text = newtext
            for r in runs[1:]:
                r._element.getparent().remove(r._element)
        else:
            p.add_run(newtext)
        return True
    return False


def _apply_global_ph(doc):
    n = 0
    for p in doc.paragraphs:
        for old, new in GLOBAL_PH:
            if _replace_text_in_runs(p, old, new):
                n += 1
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                t = cell.text
                for old, new in GLOBAL_PH:
                    if old in t:
                        set_cell_text(cell, t.replace(old, new))
                        n += 1
    return n


def _strip_shading_and_highlight(doc):
    """去除文字底纹：段落级（pPr/w:shd）与 run 级（rPr/w:shd + rPr/w:highlight）。
    表格/单元格底纹（tcPr/tblPr）属表格样式，保留。
    注意：iter() 遍历中直接删除会跳过未访问节点 → 先收集、后删除。"""
    targets = []
    for node in doc.element.body.iter():
        if node.tag in (qn("w:pPr"), qn("w:rPr")):
            for child in list(node):
                if child.tag in (qn("w:shd"), qn("w:highlight")):
                    targets.append(child)
    for child in targets:
        child.getparent().remove(child)
    return len(targets)


def _apply_file_font(doc, font):
    """统一文件字体（与模板库基础模板一致）：遍历 run 与段落标记（pPr/rPr）
    设置 rFonts ascii/hAnsi/eastAsia。先收集、后修改（避免 iter 修改问题）。"""
    n = 0
    targets = []

    def collect(rpr):
        rf = rpr.find(qn("w:rFonts"))
        if rf is None:
            rf = rpr.makeelement(qn("w:rFonts"), {})
            rpr.insert(0, rf)
        rf.set(qn("w:ascii"), font)
        rf.set(qn("w:hAnsi"), font)
        rf.set(qn("w:eastAsia"), font)
        return 1

    for r in doc.element.body.iter(qn("w:r")):
        rPr = r.find(qn("w:rPr"))
        if rPr is None:
            rPr = r.makeelement(qn("w:rPr"), {})
            r.insert(0, rPr)
        n += collect(rPr)
    for ppr in doc.element.body.iter(qn("w:pPr")):
        rpr = ppr.find(qn("w:rPr"))
        if rpr is not None:
            n += collect(rpr)
    return n


def _apply_row_rules(doc, ctx_map):
    n = 0
    for table in doc.tables:
        ctx = ctx_map.get(table._tbl, "")
        rules = None
        for kw, rr in ROW_RULES.items():
            if kw in ctx:
                rules = rr
                break
        if not rules:
            continue
        for row in table.rows:
            cells = row.cells
            if not cells:
                continue
            # 标签 = 第一个非纯数字的非空格（兼容 序号|项目|内容 型表）
            tag = next((c.text.strip() for c in cells
                        if c.text.strip() and not c.text.strip().isdigit()), "")
            subs = rules.get(tag)
            if not subs:
                continue
            for c in cells[1:]:
                newtext = c.text
                changed = False
                for pattern, repl in subs:
                    if re.search(pattern, newtext):
                        newtext = re.sub(pattern, repl, newtext)
                        changed = True
                if changed:
                    set_cell_text(c, newtext)
                    n += 1
    return n


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
      - 注/附开头 → 不参与；
      - 纯数字（序号）不更新标签；
      - 证书类行（首格含『证书』）的第 2 列（序号列）空值不填，留人工补序号。"""
    filled = 0
    for row in table.rows:
        cells = _dedup_cells(row)
        if not cells:
            continue
        current_tag = None
        for ci, c in enumerate(cells):
            t = (c.text or "").strip()
            if t:
                if t.startswith("注") or t.startswith("附"):
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
            set_cell_text(c, "【%s】" % key)
            filled += 1
    return filled


def _post_process_tables(doc, material, ctx_map):
    """占位填充：行路由 → 列表型/标签值型（附表8 简历表走 TAG_MAP 语义键）。
    表格语义按「前文标题上下文」路由（表标题在表外段落，不在表首行）。"""
    stats = {}
    personnel = material.get("personnel", [])
    performance = material.get("performance", [])
    for ti, table in enumerate(doc.tables):
        ctx = ctx_map.get(table._tbl, "")
        if _is_list_table(table):
            rows_target = None
            if "监理人员配备" in ctx:
                rows_target = max(len(personnel), 1)
            elif "已完成工程" in ctx and "情况表" not in ctx:
                rows_target = max(len(performance), 1)
            elif "正在监理工程" in ctx and "情况表" not in ctx:
                rows_target = 1
            stats[ti] = _fill_list_table(table, rows_target=rows_target)
        else:
            tag_map = TAG_MAP if ("简历表" in ctx or "出生年月" in
                                   "".join(c.text for c in table.rows[0].cells)) else None
            stats[ti] = _fill_label_table(table, tag_map=tag_map)
    return stats


def _para_text(node):
    return "".join(t.text or "" for t in node.iter(qn("w:t")))


def _duplicate_tables_by_contract(doc, tbl_meta, material, ctx_map):
    """
    动态语义②——份数复制（按契约项块范围路由，不依赖表内标题文字）：
      - F06d 附表3 已完成工程情况表：每个业绩一张（复制 len(performance) 份）；
      - F06i 附表8 监理人员简历表：每名人员一张（复制 len(personnel) 份）。
    复制到目标 doc 中对应表格之后；复制表同步登记上下文（ctx_map），
    保证后续占位路由正确。
    """
    personnel = material.get("personnel", [])
    performance = material.get("performance", [])
    for node, item_id in tbl_meta:
        if item_id == "F06d":
            n = max(len(performance), 1)
        elif item_id == "F06i":
            n = max(len(personnel), 1)
        else:
            continue
        ctx = ctx_map.get(node, "")
        anchor = node
        for _ in range(n - 1):
            new_tbl = copy.deepcopy(node)
            anchor.addnext(new_tbl)
            anchor = new_tbl
            ctx_map[new_tbl] = ctx


def _item_id_for_block(i, items):
    for it in items:
        r = it.get("块范围") or []
        if len(r) == 2 and r[0] <= i <= r[1]:
            return it["id"]
    return None


def _extract_blocks(src_path):
    """从招标文件 docx 提取块序列（段落/表格元素引用 + 顺序索引）。"""
    if not HAVE_DOCX:
        raise GenError("生成器依赖 python-docx")
    doc = Document(src_path)
    blocks = []
    for child in doc.element.body.iterchildren():
        tag = child.tag
        if tag == qn("w:p"):
            blocks.append({"type": "para", "node": child})
        elif tag == qn("w:tbl"):
            blocks.append({"type": "table", "node": child})
    return blocks, doc


def build_docx(blocks, span, items, out_path, material, font=None):
    """
    从招标文件原文块 [s,e] 深拷贝构建项目模板 docx：
      1) 段落/表格逐块深拷贝（文字 100% 契约）；
      2) 契约项驱动的份数复制（附表3/附表8 动态语义②）；
      3) 段落级全局占位替换 + 行路由占位 + 列表/标签值型占位；
      4) 后处理：去除文字底纹/高亮 + 统一文件字体（与模板库基础模板一致）。
    返回 {"占位符数", "段落占位", "表格占位"}。
    """
    if not HAVE_DOCX:
        raise GenError("生成器依赖 python-docx，当前环境未安装")
    doc = Document()
    s, e = span
    ctx_map = {}                       # 表格节点 → 表格前最近非空段落文本
    tbl_meta = []                      # [(表格节点, 契约项id)] 用于份数复制
    last_para = ""
    for i in range(s, e + 1):
        blk = blocks[i]
        if blk["type"] == "para":
            t = _para_text(blk["node"]).strip()
            if t:
                last_para = t
            doc.element.body.append(copy.deepcopy(blk["node"]))
        else:
            new_node = copy.deepcopy(blk["node"])
            ctx_map[new_node] = last_para
            tbl_meta.append((new_node, _item_id_for_block(i, items)))
            doc.element.body.append(new_node)
    _duplicate_tables_by_contract(doc, tbl_meta, material, ctx_map)
    ph_para = _apply_global_ph(doc)
    ph_row = _apply_row_rules(doc, ctx_map)
    tbl_stats = _post_process_tables(doc, material, ctx_map)
    n_shade = _strip_shading_and_highlight(doc)
    n_font = _apply_file_font(doc, font) if font else 0
    doc.save(out_path)
    total = ph_para + ph_row + sum(tbl_stats.values())
    info = {"占位符数": total, "段落占位": ph_para, "表格占位": ph_row + sum(tbl_stats.values())}
    if n_shade:
        info["去底纹"] = n_shade
    if n_font:
        info["统一字体"] = font
    return info


def _resolve_project_dir(ent, project):
    root = Path(ent) / "项目级"
    cands = [d for d in root.iterdir() if d.is_dir()] if root.is_dir() else []
    if not cands:
        raise GenError("项目级下没有项目目录")
    for d in cands:
        if d.name == project:
            return d
    return None


def _default_contract_path(proj_dir):
    p = proj_dir / "招标解析" / "格式契约" / "格式契约_第五章_投标文件格式.json"
    if not p.is_file():
        raise GenError("找不到格式契约：%s" % p)
    return p


def _default_material_path(proj_dir):
    p = proj_dir / "招标解析" / "素材清单.json"
    if not p.is_file():
        raise GenError("找不到素材清单：%s" % p)
    return p


def _default_source_docx(proj_dir):
    cands = sorted(glob.glob(str(proj_dir / "招标解析" / "招标文件-*.docx")))
    if not cands:
        raise GenError("找不到招标文件 docx（招标解析/招标文件-*.docx）")
    return Path(cands[0])


def generate(ent, project, contract_path=None, material_path=None, source_path=None,
             out_dir=None, base_dir="", register_baseline=True):
    """
    主入口：
      1) 读契约 JSON / 素材清单 / 招标文件 docx；
      2) 按 FILE_MAP 生成各项目模板 docx（F06 合并为资格证明及辅助资料表.docx）；
      3) 生成记录.json + 项目占位符清单.md；
      4) 登记产物基线（fb.register）。
    返回 {"目录": ..., "文件": [...], "未生成": [...]}。
    """
    if not HAVE_DOCX:
        raise GenError("生成器依赖 python-docx，当前环境未安装")
    ent = Path(ent)
    proj_dir = _resolve_project_dir(ent, project)
    if proj_dir is None:
        raise GenError("项目目录不存在：项目级/%s" % project)
    contract_path = Path(contract_path or _default_contract_path(proj_dir))
    material_path = Path(material_path or _default_material_path(proj_dir))
    source_path = Path(source_path or _default_source_docx(proj_dir))

    contract = core.read_json(contract_path, None)
    if not contract or "格式文件" not in contract:
        raise GenError("格式契约 JSON 无『格式文件』清单：%s" % contract_path)
    material = core.read_json(material_path, None)
    if not material:
        raise GenError("素材清单 JSON 为空：%s" % material_path)

    out = Path(out_dir) if out_dir else proj_dir / "项目模板"
    out.mkdir(parents=True, exist_ok=True)

    blocks, _ = _extract_blocks(source_path)
    by_id = {it.get("id"): it for it in contract["格式文件"]}

    results = []
    skipped = []
    merged = {}
    for m in FILE_MAP:
        if m["kind"] == "skip":
            skipped.append({"契约项": m["id"], "原因": m.get("skip_reason", "")})
            continue
        it = by_id.get(m["id"])
        if not it:
            skipped.append({"契约项": m["id"], "原因": "契约中无此项"})
            continue
        merged.setdefault(m["file"], []).append(it)

    for fname, items in merged.items():
        ids = [it["id"] for it in items]
        lo = min(it.get("块范围", [0])[0] for it in items if it.get("块范围"))
        hi = max(it.get("块范围", [0])[-1] for it in items if it.get("块范围"))
        out_file = out / fname
        info = build_docx(blocks, (lo, hi), items, out_file, material,
                          font=FILE_FONT.get(fname))
        rel = "项目级/%s/项目模板/%s" % (project, fname)
        if register_baseline:
            try:
                # 版本不显式传：首次登记 v1，重新生成自动 bump，保证可追溯
                fb.register(ent, rel, level="项目级", project=project, ptype="项目模板",
                            generator=GEN_ID, note="由格式契约+素材清单动态生成")
            except Exception as ex:                    # 基线登记失败不阻断生成
                info["基线登记"] = "失败：%s" % ex
        results.append({
            "文件": fname, "契约项": ids, "块范围": [lo, hi],
            "占位符数": info.get("占位符数", 0),
            "字体": info.get("统一字体", FILE_FONT.get(fname, "")),
            "去底纹": info.get("去底纹", 0),
        })

    record = {
        "项目": project, "生成时间": core.now_iso(),
        "生成器": "%s %s" % (GEN_ID, GEN_VERSION),
        "输入": {"契约": str(contract_path), "素材清单": str(material_path),
                 "招标文件": str(source_path), "基础模板目录": base_dir or "-"},
        "文件": results, "未生成": skipped,
    }
    (out / "生成记录.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_ph_manifest(out, results, material)
    return {"目录": str(out), "文件": results, "未生成": skipped}


def _write_ph_manifest(out_dir, results, material):
    """扫描各生成 docx 的【】占位符，输出 项目占位符清单.md。"""
    lines = ["# 项目占位符清单", ""]
    lines.append("- 项目：%s ｜ 生成器：%s %s ｜ 生成时间：%s"
                 % (material.get("project", ""), GEN_ID, GEN_VERSION, core.now_iso()))
    lines.append("- 说明：占位符统一【xxx】；图片占位【图片：xxx】；人工审核可增删；")
    lines.append("  审核通过后冻结（只读+版本号），商务标只认冻结版。")
    lines.append("")
    total = 0
    for r in results:
        fname = r["文件"]
        p = out_dir / fname
        phs = _scan_placeholders(p) if p.is_file() else []
        total += len(phs)
        lines.append("## %s（%d 个）" % (fname, len(phs)))
        for ph in sorted(phs):
            lines.append("- %s" % ph)
        lines.append("")
    lines.append("---")
    lines.append("合计占位符：%d 个（按生成器统计；人工增删后以登记清单为准）" % total)
    (out_dir / "项目占位符清单.md").write_text("\n".join(lines), encoding="utf-8")


def _scan_placeholders(docx_path):
    """提取 docx 中的【】占位符（跨 run 拼接后正则）。"""
    import zipfile
    try:
        with zipfile.ZipFile(docx_path) as z:
            xml = z.read("word/document.xml").decode("utf-8", errors="replace")
    except Exception:
        return []
    texts = []
    for m in re.finditer(r"<w:p[ >].*?</w:p>|<w:p/>", xml, flags=re.S):
        parts = re.findall(r"<w:t[^>]*>(.*?)</w:t>", m.group(0), flags=re.S)
        if parts:
            texts.append("".join(parts))
    full = "\n".join(texts)
    return sorted(set(re.findall(r"【[^】]+】", full)))
