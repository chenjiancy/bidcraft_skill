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

from _shared import core, com_util
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
# T15 技术标专属检查（M7 接入技术标检查）
# --------------------------------------------------------------------------
# 对象：项目级/<项目>/技术标/产出/技术标_<项目>.docx（单个 docx）。
# 技术标 docx 结构锚点（对齐 m6_tech/export.py）：
#   目录 = XML 含 "TOC" + "fldChar"（TOC 域）；章节标题 = XML 含 "outlineLvl"（大纲级别）；
#   页数估算口径 = 正文 1000 字/页 + 表格 500 字/页（与 M6 tech-export 页数回写一致）。
TECH_CHECKS = [
    {"id": "tech_structure", "name": "技术标结构完整性", "level": "致命", "category": "结构",
     "desc": "docx 含目录 TOC 域、章节大纲标题（outlineLvl）、正文与结尾非空（封面/目录/正文/结尾四段式）",
     "fn": "check_tech_structure"},
    {"id": "anbiao_leak", "name": "暗标敏感词复核", "level": "致命", "category": "暗标",
     "desc": "M6 设置 bidMode=暗标 时，扫描 docx 全文（段落/表格/页眉页脚）企业名/人员名/业绩名/法定代表人，命中即报（终稿层复核）",
     "fn": "check_anbiao_leak"},
    {"id": "tech_pages", "name": "页数对照（M4 约束）", "level": "致命", "category": "篇幅",
     "desc": "M6 设置 pageConstraint.max（M4 reject 抽取）vs docx 实际页数（Word COM 精确；无 COM 用 M6 同口径估算并标注）",
     "fn": "check_tech_pages"},
    # T17 扩充：图表位置 / 空白页 / 引用一致性（与 M10 补救任务单联动）
    {"id": "tech_figure_placement", "name": "图表位置合规", "level": "致命", "category": "图表",
     "desc": "文字中不得插入图表（附图附表依次附文末）：inline 图片（w:drawing/pict）段落若位于正文中段（前后 2 段内有正文且未入文末附录区）即报",
     "fn": "check_tech_figure_placement"},
    {"id": "tech_blank_pages", "name": "空白页检查", "level": "致命", "category": "篇幅",
     "desc": "不得设空白页：分页符所在段为空 或 连续 ≥3 空段即报（暗标细则常见废标项）",
     "fn": "check_tech_blank_pages"},
    {"id": "tech_ref_consistency", "name": "引用一致性（素材清单）", "level": "致命", "category": "一致性",
     "desc": "明标：素材清单业绩名/人员名须在正文出现（M6 素材注入保证，缺失=疑被改写/遗漏）；暗标去名口径跳过（anbiao_leak 反向覆盖）",
     "fn": "check_tech_ref_consistency"},
]

_TECH_OUTPUT_DIR = "技术标/产出"           # M6 终稿落位（相对 项目级/<项目>/）
_TECH_SETTINGS = "技术标/设置.json"         # M6 设置（bidMode / pageConstraint.max / personnel）


def _tech_docx_paths(out_dir):
    """技术标检查目标：单 docx（终稿文件）或目录内 *.docx。"""
    p = Path(out_dir)
    if p.is_file() and p.suffix.lower() == ".docx":
        return [p]
    if p.is_dir():
        return sorted(p.glob("*.docx"))
    return []


def _tech_settings(proj_dir):
    """读 M6 技术标/设置.json；缺失/损坏返回 None（不阻断，缺关键数据记入 issue）。"""
    p = Path(proj_dir) / _TECH_SETTINGS
    if not p.is_file():
        return None
    try:
        return core.read_json(str(p), None)
    except Exception:
        return None


def _doc_full_texts(doc):
    """docx 全文：段落 + 表格 + 页眉页脚（暗标敏感词扫描用）。"""
    texts = [p.text for p in doc.paragraphs]
    for t in doc.tables:
        for row in t.rows:
            for c in row.cells:
                texts.append(c.text)
    try:
        for sec in doc.sections:
            for hp in sec.header.paragraphs:
                texts.append(hp.text)
            for fp in sec.footer.paragraphs:
                texts.append(fp.text)
    except Exception:
        pass
    return texts


def _estimate_pages(doc):
    """页数估算（M6 同口径）：正文 CJK+词 /1000 + 表格 /500。"""
    body_cjk = body_words = table_cjk = table_words = 0
    for p in doc.paragraphs:
        t = p.text or ""
        body_cjk += len(re.findall(r"[\u4e00-\u9fff]", t))
        body_words += len(re.findall(r"[A-Za-z0-9]+", t))
    for tb in doc.tables:
        for row in tb.rows:
            for c in row.cells:
                t = c.text or ""
                table_cjk += len(re.findall(r"[\u4e00-\u9fff]", t))
                table_words += len(re.findall(r"[A-Za-z0-9]+", t))
    return (body_cjk + body_words) / 1000.0 + (table_cjk + table_words) / 500.0


def check_tech_structure(out_dir, proj_dir, material, points):
    """技术标四段式结构：TOC 域 / 章节大纲标题 / 正文非空 / 结尾非空。"""
    issues = []
    targets = _tech_docx_paths(out_dir)
    if not targets:
        return False, ["未找到技术标 docx（%s）" % out_dir]
    for f in targets:
        from docx import Document
        try:
            doc = Document(str(f))
        except Exception as e:
            issues.append("%s：文档解析失败 %s" % (f.name, e))
            continue
        xml = doc.element.xml
        paras = [p.text or "" for p in doc.paragraphs]
        non_empty = [t for t in paras if t.strip()]
        if not ("TOC" in xml and "fldChar" in xml):
            issues.append("%s：缺目录 TOC 域（须 F9 更新后重新导出）" % f.name)
        if "outlineLvl" not in xml:
            issues.append("%s：缺章节大纲标题（outlineLvl 未落盘，标题体系未生效）" % f.name)
        if len(non_empty) < 5:
            issues.append("%s：正文过薄（有效段落 %d < 5，疑缺正文章节）" % (f.name, len(non_empty)))
        if non_empty and not non_empty[-1].strip():
            issues.append("%s：结尾为空（末段无内容）" % f.name)
        if not non_empty:
            issues.append("%s：正文为空" % f.name)
    return (len(issues) == 0), issues


def check_anbiao_leak(out_dir, proj_dir, material, points):
    """暗标敏感词复核（终稿层）：M6 设置 bidMode=暗标 时扫描企业名/人员名/业绩名/法定代表人。"""
    settings = _tech_settings(proj_dir)
    if settings is None or settings.get("bidMode") != "暗标":
        return True, ["跳过：M6 设置非暗标（或设置缺失，bidMode=%s）" %
                      (settings.get("bidMode") if settings else "无设置.json")]
    names = set()
    personnel = (settings.get("personnel") or [])
    for p in personnel:
        if p.get("name"):
            names.add(p["name"].strip())
    ent = (material.get("企业基础信息") or {})
    if ent.get("法定代表人姓名"):
        names.add(str(ent["法定代表人姓名"]).strip())
    ent_name = str(ent.get("企业名称") or material.get("enterprise_name") or "")
    if ent_name.strip():
        names.add(ent_name.strip())
    for perf in (material.get("performance") or []):
        if perf.get("name"):
            names.add(str(perf["name"]).strip())
    names = {n for n in names if n and len(n) >= 2}
    if not names:
        return True, ["跳过：素材清单未提供企业/人员/业绩名可复核（暗标基准为空）"]
    issues = []
    for f in _tech_docx_paths(out_dir):
        from docx import Document
        try:
            doc = Document(str(f))
        except Exception as e:
            issues.append("%s：文档解析失败 %s" % (f.name, e))
            continue
        blob = "\n".join(_doc_full_texts(doc))
        for n in sorted(names, key=len, reverse=True):
            if n in blob:
                issues.append("%s：命中暗标敏感词「%s」" % (f.name, n))
    return (len(issues) == 0), issues


def check_tech_pages(out_dir, proj_dir, material, points):
    """页数对照：M6 设置 pageConstraint.max（或 M4 reject 抽取）vs 实际页数（COM 精确/估算）。"""
    settings = _tech_settings(proj_dir)
    limit = None
    if settings and settings.get("pageConstraint"):
        limit = settings["pageConstraint"].get("max")
    if not limit:
        limit = _extract_page_limit(points)
    if not limit:
        return True, ["跳过：未取得页数上限（M6 设置与 M4 reject 均无「总页数不超过」条款）"]
    issues = []
    for f in _tech_docx_paths(out_dir):
        from docx import Document
        try:
            doc = Document(str(f))
        except Exception as e:
            issues.append("%s：文档解析失败 %s" % (f.name, e))
            continue
        real = None
        try:
            if com_util is not None and com_util.WordApp is not None:
                with com_util.WordApp() as w:
                    real = w.pages_of(str(f))
        except Exception:
            real = None
        if real is not None:
            if real > limit:
                issues.append("%s：实际 %d 页 > 上限 %d 页" % (f.name, real, limit))
        else:
            est = int(_estimate_pages(doc)) + 1
            note = "估算（无 Word COM，正文1000字/页+表格500字/页）"
            if est > limit:
                issues.append("%s：估算 %d 页 > 上限 %d 页（%s）" % (f.name, est, limit, note))
    return (len(issues) == 0), issues


def _extract_page_limit(points):
    """从 M4 reject 规则抽取「技术标总页数不超过 N 页」（口径对齐 M6 sources）。"""
    for m in (points.get("modules") or []):
        if m.get("id") != "reject":
            continue
        for it in (m.get("items") or []):
            rule = str(it.get("rule") or "")
            mm = re.search(r"总页数不超过\s*(\d+)\s*页", rule)
            if mm:
                return int(mm.group(1))
    return None


# --------------------------------------------------------------------------
# T17 技术标检查扩充：图表位置 / 空白页 / 引用一致性
# --------------------------------------------------------------------------
def check_tech_figure_placement(out_dir, proj_dir, material, points):
    """图表位置合规：inline 图片（w:drawing/w:pict）段落若位于正文中段（前后 2 段内有正文、未入文末附录区）即报。"""
    issues = []
    for f in _tech_docx_paths(out_dir):
        from docx import Document
        try:
            doc = Document(str(f))
        except Exception as e:
            issues.append("%s：文档解析失败 %s" % (f.name, e))
            continue
        paras = doc.paragraphs
        n = len(paras)
        body_idx = {i for i, p in enumerate(paras) if (p.text or "").strip()}
        img_idx = [i for i, p in enumerate(paras)
                   if "w:drawing" in p._p.xml or "w:pict" in p._p.xml]
        if not img_idx:
            continue
        appendix_cut = max(1, int(n * 0.85))     # 文末 15% 视为附录区
        for i in img_idx:
            near_body = any(j in body_idx for j in range(max(0, i - 2), min(n, i + 3)) if j != i)
            if near_body and i < appendix_cut:
                issues.append("%s：正文中段插入图表（段落 %d 前后有正文；附图附表应依次附文末）" % (f.name, i + 1))
    return (len(issues) == 0), issues


def check_tech_blank_pages(out_dir, proj_dir, material, points):
    """空白页检查：
    - 分页符（w:br type=page）所在段为空且两侧 1 段内均空（双空夹分页）→ 空白页（合法 TOC/章末分页符空段两侧有正文，不误报）；
    - 连续 ≥3 空段（排除含分页符段避免重复计数）→ 空白区域。
    """
    issues = []
    for f in _tech_docx_paths(out_dir):
        from docx import Document
        try:
            doc = Document(str(f))
        except Exception as e:
            issues.append("%s：文档解析失败 %s" % (f.name, e))
            continue
        paras = doc.paragraphs
        n = len(paras)
        is_empty = lambda p: not (p.text or "").strip()
        for i, p in enumerate(paras):
            xml = p._p.xml
            if 'w:br' in xml and 'w:type="page"' in xml and is_empty(p):
                prev_empty = (i == 0) or is_empty(paras[i - 1])
                nxt_empty = (i == n - 1) or is_empty(paras[i + 1])
                if prev_empty and nxt_empty:
                    issues.append("%s：第 %d 段分页符所在段两侧均为空段（双空夹分页，疑空白页，不得设空白页）" % (f.name, i + 1))
        run = 0
        for i, p in enumerate(paras):
            if is_empty(p) and 'w:br' not in p._p.xml:
                run += 1
                if run >= 3:
                    issues.append("%s：第 %d 段起连续 %d 个空段（疑空白页，不得设空白页）" % (f.name, i - 1, run))
                    run = 0
            else:
                run = 0
    return (len(issues) == 0), issues


def check_tech_ref_consistency(out_dir, proj_dir, material, points):
    """引用一致性：明标时素材清单业绩名/人员名须在正文出现（M6 注入保证）；暗标去名口径跳过。"""
    settings = _tech_settings(proj_dir)
    if settings and settings.get("bidMode") == "暗标":
        return True, ["跳过：暗标口径去企业名/人名/业绩名（引用一致性由 anbiao_leak 反向覆盖）"]
    names = []
    for perf in (material.get("performance") or []):
        if perf.get("name"):
            names.append(str(perf["name"]).strip())
    for person in (material.get("personnel") or []):
        if person.get("name"):
            names.append(str(person["name"]).strip())
    names = [n for n in names if n and len(n) >= 2]
    if not names:
        return True, ["跳过：素材清单无可核对名称（业绩/人员名为空）"]
    issues = []
    for f in _tech_docx_paths(out_dir):
        from docx import Document
        try:
            doc = Document(str(f))
        except Exception as e:
            issues.append("%s：文档解析失败 %s" % (f.name, e))
            continue
        blob = "\n".join(_doc_full_texts(doc))
        missing = [n for n in names if n not in blob]
        if missing:
            issues.append("%s：清单名称未在正文出现（疑被改写/遗漏）：%s" % (f.name, "、".join(missing)))
    return (len(issues) == 0), issues


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
# 上传标书 .doc 自动转换 + 数据源项目内校验
# --------------------------------------------------------------------------
def _docx_merge_dir(out, tmp_root=None):
    """把被检查对象归一为「全 docx 目录」或单 docx 路径。

    目录：*.docx 复制 + *.doc 经 Word COM 转换为同名 .docx，合并到临时目录；
          无 Word 环境时 .doc 无法读取（注明，不降级 ok）。
    单文件：.doc → 转换单文件；.docx → 原样。
    返回 (目标路径, 说明/警告列表)；调用方负责清理返回的临时目录。"""
    p = Path(out)
    warns = []
    if p.is_file() and p.suffix.lower() == ".docx":
        return p, warns
    if p.is_file() and p.suffix.lower() == ".doc":
        if not com_util.HAVE_COM:
            return p, ["存在 .doc 文件但环境无 Word/pywin32，无法自动转换读取（跳过）：%s" % p.name]
        import tempfile
        tmp = Path(tempfile.mkdtemp(prefix="bidcraft_docconv_"))
        dst = tmp / (p.stem + ".docx")
        try:
            with com_util.WordCOM() as w:
                w.convert_to_docx(p, dst)
        except Exception as e:
            warns.append("%s：.doc 转换失败（跳过）：%s" % (p.name, e))
            return p, warns
        return dst, warns
    if not p.is_dir():
        raise core.LibraryError("被检查标书必须为目录（含 *.doc/*.docx）或单个 doc/docx 文件：%s" % out)

    docs = sorted(p.glob("*.doc"))
    if not docs:
        return p, warns
    if not com_util.HAVE_COM:
        return p, ["存在 %d 个 .doc 文件但环境无 Word/pywin32，无法自动转换读取（跳过）：%s 等"
                   % (len(docs), docs[0].name)]
    import tempfile
    import shutil
    tmp = Path(tempfile.mkdtemp(prefix="bidcraft_docconv_"))
    for d in p.glob("*.docx"):
        shutil.copy2(str(d), str(tmp / d.name))
    fail = []
    with com_util.WordCOM() as w:
        for d in docs:
            try:
                w.convert_to_docx(d, tmp / (d.stem + ".docx"))
            except Exception as e:
                fail.append("%s：%s" % (d.name, e))
    if fail:
        warns.append("以下 .doc 转换失败（跳过）：%s" % "；".join(fail[:5]))
    return tmp, warns


def _ensure_inside(label, p, proj_dir):
    """数据源项目内硬校验：--tdir/--tpl 显式指向必须位于 项目级/<项目>/ 内，
    防止人为指向其他项目目录造成数据污染（项目数据隔离）。"""
    rp = Path(p).resolve()
    rj = Path(proj_dir).resolve()
    if not (rp == rj or rj in rp.parents):
        raise core.LibraryError(
            "数据源越界（项目数据隔离）：%s=%s 不在项目目录 %s 内；"
            "--tdir/--tpl 仅允许指向本项目（项目级/<项目>/招标解析、项目模板）" % (label, p, proj_dir))


# --------------------------------------------------------------------------
# 统一执行入口
# --------------------------------------------------------------------------
def run_rule_checks(ent, proj_dir, out_dir=None, tpl_dir=None, tdir=None, tag="", kind="auto"):
    """
    通道A 全量检查：checker.py 6 项硬检查 + CHECK_RULES 4 项确定性核对。
    out_dir 可为：目录（项目生成商务标 / 上传标书原始目录，含 .doc 自动转换）/
    单个 doc/docx 文件（上传标书）。硬检查中 format/pages/frozen 需项目模板对照，
    单文件场景或模板目录无 docx（上传标书无模板基准）时自动跳过并注明。
    --tdir/--tpl 显式指向须位于项目内（数据隔离硬校验）。
    kind：auto=按 out 路径自动推断（含「技术标」→ tech）；biz=商务标（原行为）；
          tech=技术标终稿检查（T15：tech_structure/anbiao_leak/tech_pages + 复用
          placeholder/sensitive/word_open + 素材存在性；tag 缺省默认「技术标」）。
    返回 {ok, 目录, 检查: [...]}；落盘 标书检查/机器检查_<项目>[_<tag>].json/.md。
    """
    proj_dir = Path(proj_dir)
    out = Path(out_dir) if out_dir else proj_dir / "商务标"
    tpl = Path(tpl_dir) if tpl_dir else proj_dir / "项目模板"
    tdir = _tender_dir(proj_dir, tdir)
    project = proj_dir.name
    single_file = out.is_file()
    if not (out.is_dir() or single_file):
        raise core.LibraryError("被检查标书不存在（须为目录或 doc/docx 文件）：%s" % out)

    # 数据源项目内硬校验（显式传入的 tdir/tpl；默认值天然在项目内）
    if tdir != Path(proj_dir) / "招标解析":
        _ensure_inside("--tdir", tdir, proj_dir)
    if tpl != Path(proj_dir) / "项目模板":
        _ensure_inside("--tpl", tpl, proj_dir)

    # 检查对象类型判定（T15）：auto 按 out 路径推断；tech 强制技术标检查集
    if kind == "auto":
        kind = "tech" if "技术标" in str(out) else "biz"
    is_tech = (kind == "tech")
    if is_tech and not tag:
        tag = "技术标"

    # .doc 自动转换（上传标书场景）：归一为全 docx，检查后清理临时目录
    conv_tmp = None
    try:
        out_work, conv_warns = _docx_merge_dir(out)
        if isinstance(out_work, Path) and out_work.is_dir() and \
                out_work != out and out_work.name.startswith("bidcraft_docconv_"):
            conv_tmp = out_work
        single_file = out_work.is_file()

        # 1) 读取 M4 产物（标准来源）
        material = _load_tender_json(tdir, project, t_rules.list_base, "素材清单")
        points = _load_tender_json(tdir, project, t_rules.points_base, "投标要点")

        # 2) 硬检查（checker.py 通用项；单文件/无模板基准→跳过注明）
        #    T15 技术标：单终稿 docx，无项目模板对照 → format/pages/frozen 跳过
        has_tpl = tpl.is_dir() and any(tpl.glob("*.docx"))
        skip_reason = None
        if single_file:
            skip_reason = "单文件场景无项目模板对照"
        elif not has_tpl:
            skip_reason = "无项目模板基准（上传标书目录场景，跳过模板对照类检查）"
        results = []
        for item in checker.CHECKS:
            fn = getattr(checker, item["fn"], None)
            if not fn:
                results.append({"id": item["id"], "name": item["name"], "level": item["level"],
                                "category": "格式", "ok": False,
                                "issues": ["检查实现缺失: %s" % item["fn"]]})
                continue
            if skip_reason and item["id"] in ("format", "pages", "frozen"):
                results.append({"id": item["id"], "name": item["name"], "level": item["level"],
                                "category": "格式", "ok": True,
                                "issues": ["跳过：%s（%s）" % (skip_reason, item["name"])]})
                continue
            ok, issues = fn(out_work, tpl)
            results.append({"id": item["id"], "name": item["name"], "level": item["level"],
                            "category": "格式", "ok": ok, "issues": issues})

        # 3) 确定性核对 / 技术标专属检查（T15）
        if is_tech:
            for item in TECH_CHECKS:
                fn = globals().get(item["fn"])
                if not fn:
                    results.append({"id": item["id"], "name": item["name"],
                                    "category": item["category"], "level": item["level"],
                                    "ok": False, "issues": ["检查实现缺失: %s" % item["fn"]]})
                    continue
                ok, issues = fn(out_work, proj_dir, material, points)
                results.append({"id": item["id"], "name": item["name"],
                                "category": item["category"], "level": item["level"],
                                "ok": ok, "issues": issues})
            # 技术标保留 素材存在性（业绩/证书须落地）；报价/证书有效期/期限为商务标专属
            item = next(x for x in CHECK_RULES if x["id"] == "material")
            fn = globals().get(item["fn"])
            ok, issues = fn(out_work, tpl, material, points)
            results.append({"id": item["id"], "name": item["name"],
                            "category": item["category"], "level": item["level"],
                            "ok": ok, "issues": issues})
        else:
            for item in CHECK_RULES:
                fn = globals().get(item["fn"])
                if not fn:
                    results.append({"id": item["id"], "name": item["name"],
                                    "category": item["category"], "level": item["level"],
                                    "ok": False, "issues": ["检查实现缺失: %s" % item["fn"]]})
                    continue
                ok, issues = fn(out_work, tpl, material, points)
                results.append({"id": item["id"], "name": item["name"],
                                "category": item["category"], "level": item["level"],
                                "ok": ok, "issues": issues})
        for w in conv_warns:
            results.append({"id": "doc_conv", "name": ".doc 自动转换", "level": "警告",
                            "category": "格式", "ok": True, "issues": [w]})

        ok_all = all(r["ok"] for r in results)
        doc = {"project": project, "channel": "A", "tag": tag or "项目生成商务标",
               "kind": "tech" if is_tech else "biz",
               "note": "通道A 机器检查（checker 硬检查 + 确定性核对，标准=M4 解析产物%s）" %
                       ("；技术标终稿检查 T15" if is_tech else ""),
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
    finally:
        if conv_tmp is not None:
            import shutil
            shutil.rmtree(str(conv_tmp), ignore_errors=True)


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
