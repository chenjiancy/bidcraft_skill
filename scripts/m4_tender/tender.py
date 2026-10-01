# -*- coding: utf-8 -*-
"""
bidcraft · M4 招标文件解析 —— 存储/编排层（确定性文件操作）

v1.1 分工：语义解析由 agent 完成；本层只做项目级目录存取、原文提取、
agent 产物的校验落盘（文本 + JSON 双份）、素材库对照与对照表输出。

数据落位（项目级）：<软件根>/<企业>/项目级/<项目名>/招标解析/
依赖：Python 标准库（DOCX 用 zipfile + xml.etree 提取，无第三方包）。
"""

import csv
import json
import os
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

from _shared import core
from . import rules

W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

SUPPORTED_EXTS = (".docx", ".txt", ".md", ".text")
PROJECT_SUBDIR = "项目级"
TENDER_SUBDIR = "招标解析"

CHECK_CSV_COLUMNS = ["大类", "子类", "关键字", "用途", "必须", "来源条款",
                     "状态", "命中数", "素材路径", "建议"]


# --------------------------------------------------------------------------
# 项目级目录
# --------------------------------------------------------------------------
def project_tender_dir(ent, project):
    """<软件根>/<企业>/项目级/<项目名>/招标解析（不创建）。"""
    return Path(ent) / PROJECT_SUBDIR / project / TENDER_SUBDIR


def ensure_project_dir(ent, project):
    """校验项目名并创建/复用项目级招标解析目录（幂等）。"""
    ok, issue = rules.validate_project_name(project)
    if not ok:
        raise core.LibraryError("项目名不合法：%s" % issue)
    tdir = project_tender_dir(ent, project)
    tdir.mkdir(parents=True, exist_ok=True)
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
    """按扩展名提取正文：docx 内置解析；txt/md 直接解码；其他格式报错引导。"""
    p = Path(path)
    ext = p.suffix.lower()
    if ext == ".docx":
        return extract_docx(p)
    if ext in (".txt", ".md", ".text"):
        return read_text(p)
    raise core.LibraryError(
        "不支持的格式：%s。脚本内置支持 DOCX/TXT/MD；PDF/图片请由 agent 提取正文后以 --text-file 传入。" % (ext or "未知"))


def write_original(tdir, src_stem, text):
    """原文落盘：原文_<源名去扩展名>.txt → 返回相对文件名。"""
    name = rules.original_name(src_stem)
    (Path(tdir) / name).write_text(text, encoding="utf-8")
    return name


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
