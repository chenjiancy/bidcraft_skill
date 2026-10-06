# -*- coding: utf-8 -*-
"""
bidcraft · M4 招标文件解析 —— 存储/编排层（确定性文件操作）

v1.2 分工：语义解析由 agent 完成；本层只做项目级目录存取、原文提取（④：PDF
现由 PyMuPDF 表格/多栏感知结构化提取，不再强制 agent 手工 --text-file）、
agent 产物的校验落盘（文本 + JSON 双份）、素材库对照与对照表输出。

数据落位（项目级）：<软件根>/<企业>/项目级/<项目名>/招标解析/
依赖：Python 标准库（DOCX 用 zipfile + xml.etree 提取；PDF 可选 PyMuPDF，
未安装时自动降级要求 --text-file）。
"""

import csv
import json
import os
import shutil
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

from _shared import core
from . import pdf_extract, rules, rule_extract, tender_report

W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

SUPPORTED_EXTS = (".docx", ".txt", ".md", ".text", ".pdf")
PROJECT_SUBDIR = "项目级"
TENDER_SUBDIR = "招标解析"
SOURCE_SUBDIR = "源文件"
PROJECT_DATA_SUBDIR = "项目资料"   # 项目级目录结构：项目独享资料存放处（与招标解析同级）

CHECK_CSV_COLUMNS = ["大类", "子类", "关键字", "用途", "必须", "来源条款",
                     "状态", "命中数", "素材路径", "建议"]


# --------------------------------------------------------------------------
# 项目级目录
# --------------------------------------------------------------------------
def project_tender_dir(ent, project):
    """<软件根>/<企业>/项目级/<项目名>/招标解析（不创建）。"""
    return Path(ent) / PROJECT_SUBDIR / project / TENDER_SUBDIR


def ensure_project_dir(ent, project):
    """
    校验项目名并创建/复用项目级目录结构（幂等）：
      <企业>/项目级/<项目名>/招标解析/   （M4 解析产物）
      <企业>/项目级/<项目名>/项目资料/   （项目独享资料，与招标解析同级）
    返回招标解析目录（供其余 tender-* 命令使用）。
    """
    ok, issue = rules.validate_project_name(project)
    if not ok:
        raise core.LibraryError("项目名不合法：%s" % issue)
    base = Path(ent) / PROJECT_SUBDIR / project
    base.mkdir(parents=True, exist_ok=True)
    tdir = base / TENDER_SUBDIR
    tdir.mkdir(parents=True, exist_ok=True)
    (base / PROJECT_DATA_SUBDIR).mkdir(parents=True, exist_ok=True)
    return tdir


# --------------------------------------------------------------------------
# 原文提取（确定性）
# --------------------------------------------------------------------------
def extract_docx(path):
    """从 DOCX 的 word/document.xml 提取纯文本（段落以换行分隔）。"""
    try:
        with zipfile.ZipFile(path) as z:
            if "word/document.xml" not in z.namelist():
                raise core.LibraryError("无法解析 DOCX：缺少 word/document.xml（文件可能损坏或非标准 docx）")
            xml = z.read("word/document.xml")
    except zipfile.BadZipFile:
        raise core.LibraryError("无法解析 DOCX：不是合法的 zip/docx 文件")
    root = ET.fromstring(xml)
    paras = []
    for p in root.iter(W_NS + "p"):
        line = []
        for node in p.iter():
            if node.tag == W_NS + "t" and node.text:
                line.append(node.text)
            elif node.tag == W_NS + "br":
                line.append("\n")
        paras.append("".join(line))
    return "\n".join(paras)


def decode_bytes(raw):
    """按 UTF-8 系列 → GB18030 顺序解码（带 BOM 容错）。"""
    for enc in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def read_text(path):
    """读取任意文本文件（--text-file 场景，PDF/图片由 agent 提取后传入）。"""
    return decode_bytes(Path(path).read_bytes())


def extract_text_file(path):
    """按扩展名提取正文：docx 内置解析；txt/md 直接解码；pdf 走 PyMuPDF
    表格/多栏感知结构化提取（未装 PyMuPDF 时回退要求 --text-file）；其他格式报错引导。"""
    p = Path(path)
    ext = p.suffix.lower()
    if ext == ".docx":
        return extract_docx(p)
    if ext in (".txt", ".md", ".text"):
        return read_text(p)
    if ext == ".pdf":
        return pdf_extract.extract_pdf_text(p)
    raise core.LibraryError(
        "不支持的格式：%s。脚本内置支持 DOCX/TXT/MD/PDF；图片请由 agent 提取正文后以 --text-file 传入。" % (ext or "未知"))


def write_original(tdir, src_stem, text):
    """原文落盘：原文_<源名去扩展名>.txt → 返回相对文件名。"""
    name = rules.original_name(src_stem)
    (Path(tdir) / name).write_text(text, encoding="utf-8")
    return name


def archive_source(tdir, project, src_path):
    """
    归档招标文件原件：<招标解析>/源文件/源文件_<项目名>.<ext>。

    幂等约定：目标已存在且内容相同（sha256）→ 跳过返回 (dst, False)；
    目标已存在但内容不同 → 报错（避免静默覆盖丢失旧原件）。
    """
    src = Path(src_path)
    if not src.exists():
        raise core.LibraryError("源文件不存在：%s" % src)
    sub = Path(tdir) / SOURCE_SUBDIR
    sub.mkdir(parents=True, exist_ok=True)
    ext = src.suffix.lower() or ".bin"
    dst = sub / ("源文件_%s%s" % (project, ext))
    if dst.exists():
        if core.sha256_of(dst) == core.sha256_of(src):
            return dst, False
        raise core.LibraryError(
            "源文件已存在且内容不同：%s（为避免覆盖丢失旧原件，请人工处理）" % dst)
    shutil.copy2(src, dst)
    return dst, True


# --------------------------------------------------------------------------
# 产物落盘（agent 产出 → 校验 → 双份写入）
# --------------------------------------------------------------------------
def load_doc(path):
    """读取 JSON 文档（容错 UTF-8 BOM——Windows 工具常写带 BOM 的 JSON）。"""
    try:
        return json.loads(decode_bytes(Path(path).read_bytes()))
    except Exception:
        return None


def _save_pair(tdir, base, md_path, json_path, validate):
    """校验并落盘 <base>.md / <base>.json（双份，内容由 agent 保证一致）。"""
    tdir = Path(tdir)
    md_path, json_path = Path(md_path), Path(json_path)
    if not md_path.exists():
        raise core.LibraryError("产物文本不存在：%s" % md_path)
    if not json_path.exists():
        raise core.LibraryError("产物 JSON 不存在：%s（agent 须按操作手册模板产出 JSON）" % json_path)
    doc = load_doc(json_path)
    if not doc:
        raise core.LibraryError("产物 JSON 不是合法 JSON：%s" % json_path)
    ok, issues = validate(doc)
    if not ok:
        raise core.LibraryError("产物 JSON 结构校验失败：%s\n%s" % (json_path, "；".join(issues)))
    md_dst = tdir / ("%s.md" % base)
    json_dst = tdir / ("%s.json" % base)
    md_dst.write_text(decode_bytes(md_path.read_bytes()), encoding="utf-8")
    json_dst.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    return md_dst, json_dst


def save_points(tdir, project, md_path, json_path):
    return _save_pair(tdir, rules.points_base(project), md_path, json_path, rules.validate_points_json)


def save_list(tdir, project, md_path, json_path):
    return _save_pair(tdir, rules.list_base(project), md_path, json_path, rules.validate_list_json)


# --------------------------------------------------------------------------
# 素材对照（脚本确定性操作：逐项 query 素材库 → 对照表 + CSV + 汇总）
# --------------------------------------------------------------------------
def _hit_fn(ent):
    def hit(item):
        """按 (category, subtype, keywords) 查素材库台账，返回 {hits, paths}。"""
        ids, paths = set(), []
        cat = item.get("category") or None
        sub = item.get("subtype") or None
        kws = item.get("keywords") or []
        queries = [[kw] for kw in kws] if kws else [None]
        for q in queries:
            kw = q[0] if q else None
            for r in core.query(ent, category=cat, subtype=sub, keyword=kw):
                if r.get("id") in ids:
                    continue
                ids.add(r.get("id"))
                paths.append(r.get("rel_path", ""))
        return {"hits": len(ids), "paths": paths}
    return hit


def run_check(ent, tdir, project):
    """读素材清单.json → 逐项对照 → 写 素材对照_<项目>.csv → 返回 (rows, summary, csv_name)。"""
    tdir = Path(tdir)
    list_json = tdir / ("%s.json" % rules.list_base(project))
    if not list_json.exists():
        raise core.LibraryError("素材清单 JSON 不存在：%s（先执行 tender-parse 落盘产物）" % list_json)
    doc = load_doc(list_json)
    if not doc or not doc.get("items"):
        raise core.LibraryError("素材清单 JSON 为空或结构不完整：%s" % list_json)
    rows = rules.build_check_rows(doc["items"], _hit_fn(ent))
    summary = rules.summarize(rows)
    csv_name = "%s.csv" % rules.check_base(project)
    _write_check_csv(tdir / csv_name, rows)
    return rows, summary, csv_name


def _write_check_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(CHECK_CSV_COLUMNS)
        for r in rows:
            w.writerow([
                r["category"], r["subtype"], "、".join(r["keywords"]), r["purpose"],
                "必须" if r["required"] else "加分", r["source"], r["status"],
                r["hits"], "、".join(r["paths"][:5]), r["suggestion"],
            ])


# --------------------------------------------------------------------------
# v2.1 响应文件格式独立文件（脚本化提取：原文 → 章节切片 → 落盘）
# --------------------------------------------------------------------------
def _find_original(tdir):
    """定位原文文件：原文_*.txt（唯一，找不到/多个时明确报错）。"""
    cands = sorted(Path(tdir).glob("原文_*.txt"))
    if not cands:
        raise core.LibraryError("未找到原文文件（原文_*.txt）：%s（先执行 tender-extract）" % tdir)
    if len(cands) > 1:
        raise core.LibraryError("存在多个原文文件：%s（请先整理，或手动指定）" % "、".join(p.name for p in cands))
    return cands[0]


def extract_fmt(tdir, project, start=None, end=None):
    """
    响应文件格式章节脚本化提取 → 响应文件格式_<项目>.txt（一字不改切片）。

    自动定位「响应文件格式/投标文件格式」章节；start/end（1 基行号）可覆盖。
    返回 {path, start, end, lines, chars}。
    """
    tdir = Path(tdir)
    src = _find_original(tdir)
    text = decode_bytes(src.read_bytes())
    lines = text.splitlines()
    try:
        fmt_text, s, e = rules.extract_fmt(lines, start, end)
    except ValueError as ex:
        raise core.LibraryError("响应文件格式章节定位失败：%s" % ex)
    dst = tdir / ("%s.txt" % rules.fmt_base(project))
    dst.write_text(fmt_text, encoding="utf-8")
    return {"path": str(dst), "start": s, "end": e,
            "lines": e - s + 1, "chars": len(fmt_text)}


# --------------------------------------------------------------------------
# v2.1 双通道解析 · 通道A 文档解析（规则引擎落盘）+ 双通道差异比对
# --------------------------------------------------------------------------
def run_rule_extract(tdir, project):
    """
    通道A：规则引擎从原文抽取确定性字段 → 文档解析_<项目>.json。
    返回 {path, fields, count}。
    """
    tdir = Path(tdir)
    src = _find_original(tdir)
    text = decode_bytes(src.read_bytes())
    fields = rule_extract.extract_fields(text)
    doc = {"project": project, "channel": "A", "note": "文档解析（规则引擎，确定性字段）",
           "fields": fields, "generated": core.now_iso()}
    dst = tdir / ("%s.json" % rules.rule_base(project))
    dst.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"path": str(dst), "fields": fields, "count": len(fields)}


def run_dual_diff(tdir, project):
    """
    双通道差异比对：通道A 文档解析.json vs 通道B 投标要点.json → 差异清单。

    差异类型：事实值不同 / 存在性差异（v2.1 三类中的确定性两类；语义冲突由
    agent 在投标要点 diffs 中标注）。落盘 双通道差异_<项目>.json/.md。
    返回 (diff_list, md_path, json_path)。
    """
    tdir = Path(tdir)
    rule_json = tdir / ("%s.json" % rules.rule_base(project))
    points_json = tdir / ("%s.json" % rules.points_base(project))
    for p, what in ((rule_json, "文档解析（先执行 tender-rule）"),
                    (points_json, "投标要点（先执行 tender-parse）")):
        if not p.exists():
            raise core.LibraryError("缺少 %s：%s" % (what, p))
    fields = (load_doc(rule_json) or {}).get("fields") or {}
    doc_b = load_doc(points_json) or {}
    diffs = rules.compare_dual(fields, doc_b)
    md_lines = ["# 双通道解析差异 · %s" % project, "",
                "- 通道A：文档解析（规则引擎）｜通道B：agent 语义解析（9 模块）",
                "- 差异类型：事实值不同 / 存在性差异 / 语义冲突",
                "- 裁决：以招标原文为最终依据，并入投标要点 diffs 块由用户确认", ""]
    if not diffs:
        md_lines.append("（两通道对已抽取确定性字段无实质差异）")
    for i, d in enumerate(diffs, 1):
        md_lines.append("%d. [%s] %s" % (i, d["差异类型"], d["解析项"]))
        md_lines.append("   通道A：%s" % d["通道A"])
        md_lines.append("   通道B：%s" % d["通道B"])
    md_path = tdir / ("%s.md" % rules.diff_base(project))
    json_path = tdir / ("%s.json" % rules.diff_base(project))
    md_path.write_text("\n".join(md_lines), encoding="utf-8")
    json_path.write_text(json.dumps({"project": project, "diffs": diffs,
                                     "generated": core.now_iso()},
                                    ensure_ascii=False, indent=2), encoding="utf-8")
    return diffs, md_path, json_path


# --------------------------------------------------------------------------
# v2.3 投标要点 HTML 展示（闸门① 核对形态；脚本化渲染）
# --------------------------------------------------------------------------
def render_report(tdir, project):
    """
    读 投标要点.json + 双通道差异.json → 渲染单文件 HTML → 投标要点_<项目>.html。

    返回 {path, chars}。HTML 为闸门① 展示形态（浏览器打开核对）。
    """
    tdir = Path(tdir)
    points_json = tdir / ("%s.json" % rules.points_base(project))
    diff_json = tdir / ("%s.json" % rules.diff_base(project))
    for p, what in ((points_json, "投标要点（先执行 tender-parse）"),
                    (diff_json, "双通道差异（先执行 tender-diff）")):
        if not p.exists():
            raise core.LibraryError("缺少 %s：%s" % (what, p))
    points_doc = load_doc(points_json)
    diff_doc = load_doc(diff_json)
    if not points_doc:
        raise core.LibraryError("投标要点 JSON 无法读取：%s" % points_json)
    html_text = tender_report.render_report_html(
        points_doc, diff_doc or {}, core.now_iso()[:10])
    dst = tdir / ("%s.html" % rules.report_base(project))
    dst.write_text(html_text, encoding="utf-8")
    return {"path": str(dst), "chars": len(html_text)}


# --------------------------------------------------------------------------
# v2.4 补遗/澄清归档与原文提取（跨文件比对前置；语义对比由 agent 按提示词执行）
# --------------------------------------------------------------------------
ANNEX_SUBDIR = "补遗"


def run_annex(tdir, project, annex_file, annex_type):
    """
    归档补遗/澄清/修改文件到 招标解析/补遗/ 并提取正文 → 补遗原文_<项目>_<n>.txt。

    返回 {path, text_path, type, kind, lines}。语义跨文件比对由 agent 按提示词
    【补遗/澄清比对】执行（输出对投标人影响对照表，更新相关模块）。
    """
    tdir = Path(tdir)
    src = Path(annex_file)
    if not src.exists():
        raise core.LibraryError("补遗文件不存在：%s" % src)
    sub = tdir / ANNEX_SUBDIR
    sub.mkdir(parents=True, exist_ok=True)
    # 序号：补遗_<项目>_<n>.<ext>（n 递增，避免覆盖）
    ext = src.suffix.lower() or ".bin"
    n = 1
    while (sub / ("补遗_%s_%d%s" % (project, n, ext))).exists():
        n += 1
    dst = sub / ("补遗_%s_%d%s" % (project, n, ext))
    shutil.copy2(src, dst)
    # 提取正文：DOCX/TXT/MD/PDF 内置；其他格式需 agent 以 --text-file 提供
    try:
        text = extract_text_file(src)
        kind = "auto"
    except core.LibraryError as ex:
        raise core.LibraryError(
            "%s；原件已归档至 %s，请 agent 提取正文后另行补录（或补传 --text-file）" % (ex, dst))
    text_name = rules.annex_base(project) + "_%d.txt" % n
    (tdir / text_name).write_text(text, encoding="utf-8")
    return {"path": str(dst), "text_path": str(tdir / text_name), "type": annex_type,
            "kind": kind, "lines": len(text.splitlines())}
