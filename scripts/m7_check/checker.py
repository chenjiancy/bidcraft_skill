# -*- coding: utf-8 -*-
"""
M7 交标前质量检查（② 建议落地）：三道检查 + 可增行检查项表。

三道：
  1) 格式结构完整性（format）—— 输出文件与项目模板一一对应、表格结构一致、
     无悬空 XML 引用（Word「文件已损坏」类问题）;
  2) 占位符清零（placeholder）——【图片：*】必须为 0；文字占位仅允许
     待补字段清单中登记的保留项；
  3) 敏感/残留痕迹（sensitive）—— 可配置关键词表（占位痕迹、预览框说明、
     未替换括注等），命中即报。

检查项表 CHECKS 可增行：新检查只要实现一个返回 (ok, issues) 的函数并登记。
"""
import re
import zipfile
from pathlib import Path

from _shared import core

# ---------------------------------------------------------------------------
# 可增行检查项表：id / 名称 / 级别 / 说明 / 实现函数
# ---------------------------------------------------------------------------
CHECKS = [
    {"id": "format", "name": "格式结构完整性", "level": "致命",
     "desc": "输出文件与项目模板一一对应；表格结构一致；无悬空 XML 引用", "fn": "check_format"},
    {"id": "placeholder", "name": "占位符清零", "level": "致命",
     "desc": "【图片：*】占位必须为 0；文字占位仅允许待补字段清单登记项", "fn": "check_placeholder"},
    {"id": "sensitive", "name": "敏感/残留痕迹", "level": "警告",
     "desc": "扫描未清理痕迹与配置关键词（预览框说明/占位提示/未替换括注等）", "fn": "check_sensitive"},
]

# 敏感/残留痕迹关键词（可增行；命中即记入报告）
SENSITIVE_PATTERNS = [
    "此处将插入",      # 预览框灰底说明残留
    "IMG_PH",          # 预览框 docPr 打标残留
    "（企业名称）",      # 中小企业声明函括注未替换
    "占位",            # 占位提示文字
    "待补",            # 待补提示
    "TODO",
    "待完善",
    "示例",
    "样例",
]


# ---------------------------------------------------------------------------
# 基础扫描工具
# ---------------------------------------------------------------------------
def _docx_paths(d):
    return sorted(Path(d).glob("*.docx")) if Path(d).is_dir() else []


def _iter_doc_text(doc):
    """段落 + 表格单元格文本。"""
    for p in doc.paragraphs:
        yield p.text
    for t in doc.tables:
        for row in t.rows:
            for c in row.cells:
                yield c.text


def _dangling_refs(path):
    """zip 级检查：document.xml 中所有 r:id / r:embed / r:link 是否在 rels 可解析；
    返回未解析的引用列表。"""
    bad = []
    try:
        with zipfile.ZipFile(str(path)) as z:
            names = set(z.namelist())
            rel_name = "word/_rels/document.xml.rels"
            if rel_name not in names:
                return ["缺 document.xml.rels"]
            xml = z.read("word/document.xml").decode("utf-8", "ignore")
            rels = z.read(rel_name).decode("utf-8", "ignore")
    except (zipfile.BadZipFile, KeyError, OSError) as e:
        return ["文件不可解析: %s" % e]
    defined = set(re.findall(r'Id="([^"]+)"', rels))
    for attr in ("r:id", "r:embed", "r:link"):
        for m in re.findall(attr + r'="([^"]+)"', xml):
            if m not in defined:
                bad.append("%s=%s" % (attr, m))
    return bad


def _scan_placeholders(doc):
    """扫描所有【...】占位 → [(位置描述, 占位符)]。"""
    hits = []
    for i, p in enumerate(doc.paragraphs):
        for ph in re.findall(r"【[^】]+】", p.text):
            hits.append(("段落%d" % i, ph))
    for ti, t in enumerate(doc.tables):
        for ri, row in enumerate(t.rows):
            for ci, c in enumerate(row.cells):
                for ph in re.findall(r"【[^】]+】", c.text):
                    hits.append(("表%d行%d列%d" % (ti, ri, ci), ph))
    return hits


def _load_pending_allowlist(out_dir):
    """从 商务标/待补字段清单.md 提取允许保留的【...】占位。"""
    allow = set()
    p = Path(out_dir) / "待补字段清单.md"
    if not p.is_file():
        return allow
    try:
        text = p.read_text(encoding="utf-8")
    except Exception:
        return allow
    for ph in re.findall(r"【[^】]+】", text):
        allow.add(ph)
    return allow


# ---------------------------------------------------------------------------
# 三道检查实现（每个返回 (ok: bool, issues: list[str])）
# ---------------------------------------------------------------------------
def _table_signatures(doc):
    """每张表首行首格文本（去空白）作为签名；filler 会按人员复制简历范本表，
    故输出表数可多于模板，但模板每张表的签名必须仍存在。"""
    sigs = []
    for t in doc.tables:
        if not t.rows:
            continue
        first = t.rows[0].cells[0].text.replace(" ", "").replace("\u3000", "") if t.rows[0].cells else ""
        sigs.append(first)
    return sigs


def check_format(out_dir, tpl_dir):
    issues = []
    outs, tpls = _docx_paths(out_dir), _docx_paths(tpl_dir)
    out_names = {f.name for f in outs}
    for t in tpls:
        if t.name not in out_names:
            issues.append("缺输出文件（模板有、商务标无）：%s" % t.name)
    for o in outs:
        if o.name not in {t.name for t in tpls}:
            issues.append("多余输出文件（模板无对应）：%s" % o.name)
        tpl = next((t for t in tpls if t.name == o.name), None)
        for bad in _dangling_refs(o):
            issues.append("%s：悬空引用 %s" % (o.name, bad))
        if tpl is not None:
            try:
                from docx import Document
                d_o, d_t = Document(str(o)), Document(str(tpl))
                t_sigs, o_sigs = _table_signatures(d_t), _table_signatures(d_o)
                for sig in t_sigs:
                    if sig and sig not in o_sigs:
                        issues.append("%s：缺失表格（模板表头签名「%s」未在输出中出现）"
                                      % (o.name, sig))
                if len(d_o.tables) < len(d_t.tables):
                    issues.append("%s：表格数 %d < 模板 %d（模板表缺失）"
                                  % (o.name, len(d_o.tables), len(d_t.tables)))
            except Exception as e:
                issues.append("%s：文档解析失败 %s" % (o.name, e))
    return (not issues, issues)


def check_placeholder(out_dir, tpl_dir):
    issues = []
    allow = _load_pending_allowlist(out_dir)
    try:
        from docx import Document
    except Exception as e:
        return False, ["python-docx 不可用: %s" % e]
    for o in _docx_paths(out_dir):
        try:
            doc = Document(str(o))
        except Exception as e:
            issues.append("%s：文档解析失败 %s" % (o.name, e))
            continue
        for where, ph in _scan_placeholders(doc):
            if ph.startswith("【图片："):
                issues.append("%s %s：图片占位未填充 %s" % (o.name, where, ph))
            elif ph not in allow:
                issues.append("%s %s：清单外残留占位 %s（未在待补字段清单登记）" % (o.name, where, ph))
    return (not issues, issues)


def check_sensitive(out_dir, tpl_dir):
    issues = []
    try:
        from docx import Document
    except Exception as e:
        return False, ["python-docx 不可用: %s" % e]
    for o in _docx_paths(out_dir):
        try:
            doc = Document(str(o))
        except Exception as e:
            continue
        for i, txt in enumerate(_iter_doc_text(doc)):
            for pat in SENSITIVE_PATTERNS:
                if pat in txt:
                    ctx = txt.strip().replace("\n", " ")[:60]
                    issues.append("%s：命中「%s」→ %s" % (o.name, pat, ctx))
    return (not issues, issues)


# ---------------------------------------------------------------------------
# 统一执行入口
# ---------------------------------------------------------------------------
def run_checks(ent, proj_dir, out_dir=None, tpl_dir=None):
    """商务标 → M7 检查报告。返回 {ok, 检查: [...]}。"""
    proj_dir = Path(proj_dir)
    out = Path(out_dir) if out_dir else proj_dir / "商务标"
    tpl = Path(tpl_dir) if tpl_dir else proj_dir / "项目模板"
    results = []
    for item in CHECKS:
        fn = globals().get(item["fn"])
        if not fn:
            results.append({"id": item["id"], "name": item["name"], "level": item["level"],
                            "ok": False, "issues": ["检查实现缺失: %s" % item["fn"]]})
            continue
        ok, issues = fn(out, tpl)
        results.append({"id": item["id"], "name": item["name"], "level": item["level"],
                        "ok": ok, "issues": issues})
    ok_all = all(r["ok"] for r in results)
    _write_report(out, results, ok_all)
    return {"ok": ok_all, "目录": str(out), "检查": results}


def _write_report(out, results, ok_all):
    lines = ["# M7 检查报告（交标前质检）", "",
             "总判定：**%s**" % ("全部通过" if ok_all else "存在未通过项"), ""]
    for r in results:
        lines.append("## %s [%s] %s（%s）" % (r["id"], "✓" if r["ok"] else "✗",
                                             r["name"], r["level"]))
        if not r["issues"]:
            lines.append("- 无")
        for x in r["issues"]:
            lines.append("- %s" % x)
        lines.append("")
    (Path(out) / "M7检查报告.md").write_text("\n".join(lines), encoding="utf-8")
