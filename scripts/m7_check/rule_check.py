# -*- coding: utf-8 -*-
"""
bidcraft · M7 标书检查 —— 通道A 机器检查规则引擎（确定性规则，代码控制正确性）

v2.0 双通道检查 · 通道A：在 checker.py 6 项硬检查（格式/占位/敏感/可打开/页数/冻结）
之上，新增「消费 M4 解析产物」的确定性核对规则：
  - quote    报价一致性（素材清单用户确认报价 vs 最高限价 vs 商务标内金额）
  - cert     证书有效期（素材清单证书文件名推断到期日 vs 投标截止日，参考级）
  - deadline 期限文本（商务标内投标有效期/服务期表述存在性，参考级）
  - material 素材文件存在性（素材清单全部 path 落地检查，致命）

设计约定（对齐 m4_tender/rule_extract.py）：
  - CHECK_RULES 为可增行表：id / name / category（双通道差异比对对齐用）/
    level / fn
  - 标准一律读 M4 产物（投标要点_<项目>.json / 素材清单_<项目>.json），
    不重复提取招标文件（口径漂移防护）
  - 确定性可判项做硬结论；语义脆弱项（文件名推断日期）标「参考，须人工核对」

产物落位：<企业>/项目级/<项目>/标书检查/机器检查_<项目>.json/.md
"""
import re
from pathlib import Path

from _shared import core
from m4_tender import rules as t_rules      # M4 产物命名规范（单一事实来源）
from . import checker, rules as m7rules

# --------------------------------------------------------------------------
# 可增行检查规则表（通道A）
# --------------------------------------------------------------------------
CHECK_RULES = [
    {"id": "quote", "name": "报价一致性", "category": "报价", "level": "致命",
     "desc": "素材清单用户确认报价 ≤ 最高限价；商务标内出现与确认报价不同的金额即报", "fn": "check_quote"},
    {"id": "cert", "name": "证书/素材有效期", "category": "证书", "level": "警告",
     "desc": "素材清单证书文件名推断到期日 vs 投标截止日（文件名推断，参考级）", "fn": "check_cert"},
    {"id": "deadline", "name": "期限文本存在性", "category": "期限", "level": "警告",
     "desc": "商务标内投标有效期/服务期表述存在性核对（参考级）", "fn": "check_deadline"},
    {"id": "material", "name": "素材文件存在性", "category": "完整性", "level": "致命",
     "desc": "素材清单全部 path 必须落地存在（缺素材=投标文件缺附件，致命）", "fn": "check_material"},
]

# 金额/日期/关键词模式
_AMOUNT_CN = re.compile(r"([\d,]+(?:\.\d+)?)\s*万元")
_AMOUNT_RAW = re.compile(r"(?:¥|￥)?\s*([\d,]+(?:\.\d+)?)")
_DATE_FN = re.compile(r"_(\d{4})(\d{2})(\d{2})")
_DATE_FN_YM = re.compile(r"_(\d{4})(\d{2})")
_DATE_FN_Y = re.compile(r"_(\d{4})")
_QUOTE_KW = ("投标总价", "投标报价", "总报价", "投标总报价", "总价（元）", "报价（元）", "报价金额")
_PERIOD_KW = ("投标有效期", "服务期", "监理服务期限", "服务期限")
# 非报价语境排除词（规模/声明/政策数字，命中即跳过该金额）
_EXCLUDE_CTX = ("营业收入", "从业人员", "资产总额", "缴税", "万元以下", "万元及", "标段", "项目编号",
                "联系人", "电话", "手机", "邮编", "传真", "日期", "年度", "年", "编号")
_EXCLUDE_WAN_AMT = 500.0      # "X万元"金额 > 500万 视为规模/业绩数字（报价单位是元）


# --------------------------------------------------------------------------
# M4 产物读取
# --------------------------------------------------------------------------
def _tender_dir(proj_dir, tdir):
    return Path(tdir) if tdir else Path(proj_dir) / "招标解析"


def _load_tender_json(tdir, project, base_fn, label):
    p = tdir / ("%s.json" % base_fn(project))
    if not p.is_file():
        raise core.LibraryError("%s JSON 不存在：%s（M7 双通道检查依赖 M4 产物，先执行 M4 招标解析）" % (label, p))
    doc = core.read_json(str(p), None)
    if not doc:
        raise core.LibraryError("%s JSON 无法读取：%s" % (label, p))
    return doc


def _module(points, mid):
    for m in (points.get("modules") or []):
        if m.get("id") == mid:
            return m
    return None


def _field(points, mid, key):
    """投标要点模块字段值：{value, evidence} → value。"""
    m = _module(points, mid)
    if not m:
        return ""
    f = (m.get("fields") or {}).get(key) or {}
    return str(f.get("value", ""))


# --------------------------------------------------------------------------
# 检查实现（每个返回 (ok, issues)）
# --------------------------------------------------------------------------
def _docx_iter(out_dir):
    """遍历被检查标书 docx（目录或单 docx 文件）→ [(文件名, 段落文本list, 表格文本list)]。

    支持两种输入形态：目录（项目生成商务标 / 上传解压目录）；单 docx 文件
    （用户上传的单个投标文件，--out 直接传文件路径）。"""
    from docx import Document
    out = []
    targets = []
    p = Path(out_dir)
    if p.is_dir():
        targets = sorted(p.glob("*.docx"))
    elif p.is_file() and p.suffix.lower() == ".docx":
        targets = [p]
    else:
        raise core.LibraryError("被检查标书必须为目录（含 *.docx）或单个 docx 文件：%s" % out_dir)
    for f in targets:
        try:
            doc = Document(str(f))
        except Exception as e:
            out.append((f.name, [], [["文档解析失败：%s" % e]]))
            continue
        paras = [p.text for p in doc.paragraphs]
        tables = []
        for t in doc.tables:
            cells = []
            for row in t.rows:
                for c in row.cells:
                    cells.append(c.text)
            tables.append(cells)
        out.append((f.name, paras, tables))
    return out


def _amounts_in(texts):
    """提取文本中报价语境金额，返回 [(金额字符串, 上下文)]。

    过滤规则（防误报）：
      - 上下文含排除词（营业收入/从业人员/规模等）→ 跳过
      - "X万元"金额 > 500 万 → 视为规模/业绩数字（报价单位是元）→ 跳过
      - 裸数字仅当同一行/紧邻上下文含报价关键词才采信（防年份/编号/电话误报）
    """
    hits = []
    for txt in texts:
        t = (txt or "").strip()
        if not t:
            continue
        if "【" in t or "】" in t:
            # 含占位符的行：数字是占位提示/序号，非报价金额（占位残留由 placeholder 检查报）
            t_noph = re.sub(r"【[^】]*】", "", t)
            if not t_noph.strip():
                continue
            t = t_noph
        has_quote_kw = any(k in t for k in _QUOTE_KW)
        for m in _AMOUNT_CN.finditer(t):
            ctx = t[max(0, m.start() - 30): m.end() + 30]
            if any(e in ctx for e in _EXCLUDE_CTX):
                continue
            try:
                if float(m.group(1).replace(",", "")) > _EXCLUDE_WAN_AMT:
                    continue
            except (TypeError, ValueError):
                pass
            if has_quote_kw:
                hits.append((m.group(1), ctx.strip()[:60]))
        for m in _AMOUNT_RAW.finditer(t):
            v = m.group(1)
            ctx = t[max(0, m.start() - 20): m.end() + 20]
            if any(e in ctx for e in _EXCLUDE_CTX):
                continue
            # 纯序号排除：1-9 且紧跟「、」或「.」
            if re.match(r"^\d{1,2}$", v) and re.search(r"^\s*\d{1,2}(?:、|\.)", ctx[:8]):
                continue
            if has_quote_kw or any(k in ctx for k in _QUOTE_KW):
                hits.append((v, ctx.strip()[:60]))
    return hits


def _norm_amount(v):
    return float(str(v).replace(",", ""))


def check_quote(out_dir, tpl_dir, material, points):
    """报价一致性：确认报价 vs 最高限价；商务标内金额 vs 确认报价。"""
    issues = []
    bid_price = material.get("投标报价")
    limit_text = _field(points, "pricing", "报价上限（废标线）")
    if not bid_price:
        return True, ["跳过：素材清单未确认投标报价（无法核对报价一致性）"]
    try:
        bp = _norm_amount(bid_price)
    except (TypeError, ValueError):
        return True, ["跳过：投标报价无法解析为金额：%r" % bid_price]

    # 1) 超限价（废标线）：通过不报，超限才报
    limit = None
    for m in re.finditer(r"([\d.]+)\s*万元", limit_text or ""):
        limit = _norm_amount(m.group(1)) * 10000
    if limit is not None and bp > limit:
        issues.append("投标报价 %.2f 元 > 最高限价 %.2f 元（无效标线：%s）"
                      % (bp, limit, limit_text[:80]))

    # 2) 商务标内金额一致性
    found = []
    for fname, paras, tables in _docx_iter(out_dir):
        for t in paras:
            found.extend(_amounts_in([t]))
        for cells in tables:
            if any(any(k in c for k in _QUOTE_KW) for c in cells):
                found.extend(_amounts_in(cells))
    seen = {}
    for v, ctx in found:
        try:
            nv = _norm_amount(v)
        except (TypeError, ValueError):
            continue
        if nv not in seen:
            seen[nv] = ctx
    for nv, ctx in seen.items():
        if abs(nv - bp) > 0.01:
            issues.append("商务标内发现与确认报价 %.2f 不一致的金额 %.2f（上下文：%s）——须人工核对报价表/投标函/开标一览表一致性"
                          % (bp, nv, ctx[:60]))
    return (not issues, issues)


def _deadline_date(material, points):
    """投标截止日：素材清单 投标截止日期 优先（ISO 或中文），回退投标要点 basic。"""
    raw = None
    for src in (material.get("投标截止日期"), _field(points, "basic", "投标截止时间")):
        if src:
            raw = str(src)
            break
    if not raw:
        return None
    # 中文格式：2026年8月10日
    m = re.search(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", raw)
    if not m:
        # ISO 格式：2026-08-10
        m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", raw)
    if not m:
        return None
    try:
        import datetime
        return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def _path_dates(path):
    """文件名推断日期集合：_YYYYMMDD / _YYYYMM → 全部日期列表。
    语义：取最大日期为「推断到期日」（保守判定：证书不过期则到期日在最远未来）。"""
    from datetime import date
    name = Path(str(path)).stem
    out = []
    for m in _DATE_FN.finditer(name):
        try:
            out.append(date(int(m.group(1)), int(m.group(2)), int(m.group(3))))
        except ValueError:
            pass
    for m in _DATE_FN_YM.finditer(name):
        try:
            out.append(date(int(m.group(1)), int(m.group(2)), 28))
        except ValueError:
            pass
    for m in _DATE_FN_Y.finditer(name):
        try:
            out.append(date(int(m.group(1)), 12, 31))
        except ValueError:
            pass
    return sorted(set(out))


def check_cert(out_dir, tpl_dir, material, points):
    """证书/素材有效期：有「有效期语义」的素材做到期日推断（参考级）。

    有效期语义素材：注册证书/岗位证书（注册有效期）、企业资质、ISO 认证、
    身份证（到期日）。无有效期语义（荣誉=颁发日、职称/毕业证/简历、社保=
    开具日、业绩合同）不参与推断——避免误报。"""
    issues = []
    deadline = _deadline_date(material, points)
    if deadline is None:
        return True, ["跳过：无法解析投标截止日（素材清单 投标截止日期 / 投标要点 basic 投标截止时间）"]
    paths = []
    for person in (material.get("personnel") or []):
        for k in ("注册证书", "岗位证书"):
            paths.extend(person.get(k) or [])
    for group in ("qualification_required", "iso_certificates"):
        for item in (material.get(group) or []):
            p = item.get("path")
            if p:
                paths.append(p)
    biz = material.get("企业基础信息") or {}
    for k in ("法定代表人身份证", "委托代理人身份证"):
        paths.extend(biz.get(k) or [])
    for p in sorted(set(str(x) for x in paths if x)):
        dates = _path_dates(p)
        if not dates:
            continue
        max_d = dates[-1]
        if max_d < deadline:
            issues.append("素材文件名推断到期日 %s < 投标截止日 %s：%s（推断自文件名，须人工核对证书原件/扫描件是否过期）"
                          % (max_d, deadline, Path(p).name))
    return (not issues, issues)


def check_deadline(out_dir, tpl_dir, material, points):
    """期限文本存在性：商务标内投标有效期/服务期表述存在性（参考级）。

    仅报「缺失」；找到的表述作为信息（issue 前缀「信息」），但不再使 ok=False
    ——存在性为正常态，缺失才构成问题。"""
    issues = []
    std = {
        "投标有效期": _field(points, "basic", "投标有效期"),
        "服务期": _field(points, "basic", "服务期"),
    }
    body = []
    for fname, paras, tables in _docx_iter(out_dir):
        for t in paras:
            body.append(t)
        for cells in tables:
            body.extend(cells)
    found_any = True
    for kw, std_text in std.items():
        hits = [t.strip().replace("\n", " ")[:80] for t in body if kw in t]
        if not hits:
            issues.append("商务标未找到【%s】表述（招标标准：%s）——可能缺失，须人工核对"
                          % (kw, (std_text or "（未解析到标准）")[:50]))
            found_any = False
        else:
            # 信息级：存在（不导致 ok=False）
            issues.append("[信息]【%s】表述存在（招标标准：%s）：%s"
                          % (kw, (std_text or "")[:40], hits[0]))
    return (found_any, issues)


def check_material(out_dir, tpl_dir, material, points):
    """素材文件存在性：素材清单全部 path 落地检查（致命：缺素材=缺附件）。"""
    issues = []
    paths = []
    for person in (material.get("personnel") or []):
        for k in ("注册证书", "岗位证书", "职称", "简历", "毕业证"):
            for p in (person.get(k) or []):
                paths.append(("人员 %s · %s" % (person.get("name", "?"), k), p))
    for group, gname in (("qualification_required", "企业资质"),
                         ("iso_certificates", "体系认证"),
                         ("honors", "荣誉"),
                         ("performance", "业绩"),
                         ("social_security_required", "社保")):
        for item in (material.get(group) or []):
            if item.get("path"):
                paths.append(("%s · %s" % (gname, item.get("name", "?")), item["path"]))
    biz = material.get("企业基础信息") or {}
    for k in ("法定代表人身份证", "委托代理人身份证"):
        for p in (biz.get(k) or []):
            paths.append(("企业基础信息 · %s" % k, p))
    if not paths:
        return True, ["跳过：素材清单无素材路径（可能为空清单）"]
    for label, p in paths:
        if not Path(str(p)).is_file():
            issues.append("素材缺失（致命）：%s → %s" % (label, p))
    return (not issues, issues)


# --------------------------------------------------------------------------
# 统一执行入口
# --------------------------------------------------------------------------
def run_rule_checks(ent, proj_dir, out_dir=None, tpl_dir=None, tdir=None, tag=""):
    """
    通道A 全量检查：checker.py 6 项硬检查 + CHECK_RULES 4 项确定性核对。
    out_dir 可为：目录（项目生成商务标默认）/ 单个 docx（上传标书，仅执行
    CHECK_RULES 语义核对；硬检查中 format/pages/frozen 需项目模板对照，
    单文件场景自动跳过并注明）。
    返回 {ok, 目录, 检查: [...]}；落盘 标书检查/机器检查_<项目>[_<tag>].json/.md。
    """
    proj_dir = Path(proj_dir)
    out = Path(out_dir) if out_dir else proj_dir / "商务标"
    tpl = Path(tpl_dir) if tpl_dir else proj_dir / "项目模板"
    tdir = _tender_dir(proj_dir, tdir)
    project = proj_dir.name
    single_file = out.is_file()
    if not (out.is_dir() or single_file):
        raise core.LibraryError("被检查标书不存在（须为目录或 docx 文件）：%s" % out)

    # 1) 读取 M4 产物（标准来源）
    material = _load_tender_json(tdir, project, t_rules.list_base, "素材清单")
    points = _load_tender_json(tdir, project, t_rules.points_base, "投标要点")

    # 2) 硬检查（checker.py 6 项；单文件上传场景：format/pages/frozen 需模板对照→跳过注明）
    results = []
    for item in checker.CHECKS:
        fn = getattr(checker, item["fn"], None)
        if not fn:
            results.append({"id": item["id"], "name": item["name"], "level": item["level"],
                            "category": "格式", "ok": False,
                            "issues": ["检查实现缺失: %s" % item["fn"]]})
            continue
        if single_file and item["id"] in ("format", "pages", "frozen"):
            results.append({"id": item["id"], "name": item["name"], "level": item["level"],
                            "category": "格式", "ok": True,
                            "issues": ["跳过：单文件上传场景无项目模板对照（%s）" % item["name"]]})
            continue
        ok, issues = fn(out, tpl)
        results.append({"id": item["id"], "name": item["name"], "level": item["level"],
                        "category": "格式", "ok": ok, "issues": issues})

    # 3) 确定性核对（CHECK_RULES）
    for item in CHECK_RULES:
        fn = globals().get(item["fn"])
        if not fn:
            results.append({"id": item["id"], "name": item["name"],
                            "category": item["category"], "level": item["level"],
                            "ok": False, "issues": ["检查实现缺失: %s" % item["fn"]]})
            continue
        ok, issues = fn(out, tpl, material, points)
        results.append({"id": item["id"], "name": item["name"],
                        "category": item["category"], "level": item["level"],
                        "ok": ok, "issues": issues})

    ok_all = all(r["ok"] for r in results)
    doc = {"project": project, "channel": "A", "tag": tag or "项目生成商务标",
           "note": "通道A 机器检查（checker 硬检查 + 确定性核对，标准=M4 解析产物）",
           "结论": "全部通过" if ok_all else "存在未通过项",
           "检查": results, "generated": core.now_iso()}

    # 4) 落盘 标书检查/机器检查_<项目>[_<tag>].json/.md + 回读
    cdir = Path(proj_dir) / m7rules.check_subdir()
    cdir.mkdir(parents=True, exist_ok=True)
    base = m7rules.machine_base(project, tag)
    json_path = cdir / ("%s.json" % base)
    md_path = cdir / ("%s.md" % base)
    json_path.write_text(__import__("json").dumps(doc, ensure_ascii=False, indent=2),
                         encoding="utf-8")
    md_path.write_text(_render_md(doc), encoding="utf-8")
    core.readback.verify_json(json_path, required_fields=("project", "检查"), label="机器检查 json")
    core.readback.verify_file(md_path, label="机器检查 md")
    return {"ok": ok_all, "目录": str(cdir), "tag": tag or "项目生成商务标",
            "检查": results, "json": str(json_path), "md": str(md_path)}


def _render_md(doc):
    lines = ["# M7 通道A · 机器检查 · %s" % doc.get("project"), "",
             "总判定：**%s**" % doc.get("结论"), ""]
    for r in doc.get("检查") or []:
        mark = "✓" if r.get("ok") else "✗"
        lines.append("## %s [%s] %s（%s）" % (r.get("id"), mark, r.get("name"),
                                              r.get("level")))
        if not r.get("issues"):
            lines.append("- 无")
        for x in r.get("issues") or []:
            lines.append("- %s" % x)
        lines.append("")
    return "\n".join(lines)
