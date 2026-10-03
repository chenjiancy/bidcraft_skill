# -*- coding: utf-8 -*-
"""
M5 填充引擎 v1.0：项目模板（冻结版 docx）→ 商务标（图文混排 docx）。

流程（对每个模板文件）：
  1) 扫描占位符【xxx】（段落 + 表格单元格，跨 run）；
  2) 文字占位填充：素材清单 / 企业基础信息 / 投标截止日期（【日期】=投标截止日）/ 招标人；
  3) 图片占位填充：素材库取图 → 按系统级图片尺寸口径（image_spec）插入 → 删除占位段；
     缺图 → 删除占位段 + 缺图清单；
  4) 简历表（附表8）：OCR 识别素材库「人员/<姓名>/简历/*.png」文字 → 填 17 个占位；
     无扫描件 → 占位保留 + 待补字段清单；
  5) 表格填充：附表6/7 人员表按 personnel；附表2 业绩汇总表按 performance；
     附表9 仪器设备表固定不动；
  6) 文字占位无映射/值缺失 → 占位保留 + 待补字段清单（交标前人工补）。

输出：商务标/（10 docx 同名）+ 生成记录.json + 缺图清单.md + 待补字段清单.md。
"""
import json
import re
import subprocess
import sys
from pathlib import Path

from _shared import core

try:
    from docx import Document
    from docx.shared import Cm
    from docx.oxml.ns import qn
    HAVE_DOCX = True
except Exception:                                    # pragma: no cover
    HAVE_DOCX = False

from m5_project import image_spec as imgsp

FILL_ID = "m5-bid-fill"
FILL_VERSION = "v1.0"

# Tesseract OCR（环境实测：C:\Users\hxjlcj\AppData\Local\Programs\Tesseract-OCR\tesseract.exe，chi_sim 可用）
TESS = r"C:\Users\hxjlcj\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"

DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")


class FillError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# 文字占位 → 素材字段映射（KEY 取素材清单顶层字段或「企业基础信息」子字段）
# 值可为字符串/数字；占位符在段落或表格单元格中整体替换
# ---------------------------------------------------------------------------
def _mat_value(material, biz, key):
    """返回 (值, 是否待补)。key: 素材清单顶层键 或 企业基础信息.<子键>。"""
    if key.startswith("biz."):
        return biz.get(key[4:], ""), False
    if key in ("project", "project_id", "招标人", "投标截止日期"):
        return str(material.get(key, "")), False
    return str(material.get(key, "")), False


TEXT_KEY_MAP = {
    "【项目名称】": ("project", "素材清单.project"),
    "【项目编号】": ("project_id", "素材清单.project_id"),
    "【日期】": ("投标截止日期", "投标截止日期（2026-10-09）"),
    "【招标人】": ("招标人", "招标人"),
    "【招标人名称】": ("招标人", "招标人"),
    "【投标人名称】": ("biz.投标人名称", "企业基础信息.投标人名称"),
    "【统一社会信用代码】": ("biz.统一社会信用代码", "企业基础信息.统一社会信用代码"),
    "【企业地址】": ("biz.企业地址", "企业基础信息.企业地址"),
    "【邮编】": ("biz.邮编", "企业基础信息.邮编"),
    "【联系电话】": ("biz.联系电话", "企业基础信息.联系电话"),
    "【法定代表人联系电话】": ("biz.联系电话", "企业基础信息.联系电话"),
    "【传真】": ("biz.传真", "企业基础信息.传真"),
    "【开户银行】": ("biz.开户银行", "企业基础信息.开户银行"),
    "【开户账号】": ("biz.开户账号", "企业基础信息.开户账号"),
    "【成立时间】": ("biz.成立时间", "企业基础信息.成立时间"),
    "【经营期限】": ("biz.经营期限", "企业基础信息.经营期限"),
    "【单位性质】": ("biz.单位性质", "企业基础信息.单位性质"),
    "【法定代表人姓名】": ("biz.法定代表人姓名", "企业基础信息.法定代表人姓名"),
    "【性别】": ("biz.性别", "企业基础信息.性别"),
    "【年龄】": ("biz.年龄", "企业基础信息.年龄"),
    "【职务】": ("biz.职务", "企业基础信息.职务"),
    "【身份证号】": ("biz.身份证号", "企业基础信息.身份证号"),
    "【投标保证金金额（大写）】": ("_bail_cap", "壹万元整（固定值）"),
    "【总监姓名】": ("_director", "personnel[0].name"),
    "【总监专业】": ("_director_major", "市政公用工程（招标要求）"),
    "【企业资质等级】": ("_qual_level", "资质证书扫描件"),
    "【业主名称】": ("招标人", "招标人"),
    "【投标总价（元）】": ("_pending", "报价策略待定（素材清单 pending）"),
    "【授权代理人姓名】": ("_pending", "授权委托书待制作"),
    "【监理经历：（国内）X年（国际）X年】": ("_pending", "企业监理经历年限待补"),
    "【职工总人数X人 / 技术人员X人 / 管理人员X人】": ("_pending", "企业职工人数待补"),
}


# ---------------------------------------------------------------------------
# 图片占位 → 素材库图片（相对素材库根）映射；缺图（无文件）→ 缺图清单
# 值: (路径或 None=缺, 口径键, 说明)
# ---------------------------------------------------------------------------
FILL_IMG_MAP = {
    "【图片：组织机构框图（含结构、领导成员、主要技术人员、管理人员及数量）】":
        ("企业介绍/组织机构图_20261001.png", "组织机构框图", "企业介绍"),
    "【图片：企业基本账户开户许可证扫描件】":
        ("财务/财务证照/开户许可证_长期.png", "开户许可证扫描件", "财务证照"),
    "【图片：企业法人营业执照（副本）扫描件】":
        ("资质/营业执照_副本_长期.png", "营业执照扫描件", "资质"),
    "【图片：企业资质证书扫描件】": (None, "资质证书组", "甲级+乙级多张组合，v1.1 实现"),
    "【图片：拟派监理人员注册证书、岗位证书、职称、身份证等证明材料】":
        (None, "人员证书组", "6人证书组合插入，v1.1 实现"),
    "【图片：拟投入监理人员社保证明】": (None, "社保证明", "6人社保证明待出具"),
    "【图片：三体系认证证书】": (None, "三体系认证证书", "ISO9001/14001/45001 三张"),
    "【图片：总监高级工程师职称证书】": (None, "总监高级工程师职称证书", "张三职称证书"),
    "【图片：其他监理人员职称证书】": (None, "其他监理人员职称证书", "陈友龙/吴志水/裴友谊/赵六/赵七"),
    "【图片：先进（优秀）监理企业证书】": (None, "先进优秀监理企业证书", "荣誉（2张）"),
    "【图片：监理示范（优质）工程】": (None, "监理示范优质工程", "荣誉（2张）"),
    "【图片：法定代表人身份证正、反面扫描件】": (None, "身份证", "法代身份证待提供"),
    "【图片：委托代理人身份证正、反面扫描件】": (None, "身份证", "代理人身份证待提供"),
    "【图片：基本账户开户许可证（或基本账户存款信息）扫描件】":
        ("财务/财务证照/开户许可证_长期.png", "开户许可证扫描件", "财务证照；存款信息图待提供"),
}


# ---------------------------------------------------------------------------
# 通用 docx 工具
# ---------------------------------------------------------------------------
def _para_full_text(p):
    return "".join(node.text or "" for node in p._p.iter(qn("w:t")))


def _para_runs(p):
    return [node for node in p._p.iter(qn("w:r"))]


def _set_para_text(p, text):
    """整段替换为 text，保留首 run 的 rPr（样式）。"""
    runs = _para_runs(p)
    if not runs:
        r = p._p.makeelement(qn("w:r"), {})
        p._p.append(r)
        runs = [r]
    t_els = [node for node in runs[0].iter(qn("w:t"))]
    if t_els:
        t_els[0].text = text
        for t in t_els[1:]:
            t.getparent().remove(t)
    else:
        t = runs[0].makeelement(qn("w:t"), {})
        runs[0].append(t)
        t.text = text
    for r in runs[1:]:
        p._p.remove(r)


def _iter_doc_paragraphs(doc):
    """正文段落 + 表格内段落（含嵌套表格）。"""
    for p in doc.paragraphs:
        yield p
    for t in doc.tables:
        for row in t.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    yield p


def _fmt_date(deadline):
    """2026-10-09 09:00 → 2026年10月9日"""
    m = DATE_RE.match(str(deadline or "").strip())
    if not m:
        return ""
    y, mo, d = m.groups()
    return "%s年%d月%d日" % (y, int(mo), int(d))


# ---------------------------------------------------------------------------
# 简历表 OCR（rapidocr-onnxruntime 优先；tesseract 为 fallback）
# ---------------------------------------------------------------------------
RESUME_TAG_MAP = {
    "姓名": "人员姓名", "性别": "性别", "出生年月": "出生年月",
    "最终学历": "学历", "毕业院校专业及时间": "毕业院校专业及时间",
    "政治面貌": "政治面貌", "现任职务": "现任职务", "技术职称": "技术职称",
    "聘任时间": "聘任时间", "从事设计工作年限": "从事设计工作年限",
    "从事造价工作年限": None,                      # 模板无此字段，忽略
    "从事监理工作年限": "从事监理工作年限（年）",
    "居民身份证号码": "身份证号", "相关专业经历": "相关专业经历",
    "主要经历": "主要经历",
}
# 长标签优先匹配（避免子串误切）
_RESUME_LABELS = sorted([t for t in RESUME_TAG_MAP if RESUME_TAG_MAP[t]],
                        key=len, reverse=True)

_rapid_engine = None


def _get_rapid():
    global _rapid_engine
    if _rapid_engine is None:
        from rapidocr_onnxruntime import RapidOCR
        _rapid_engine = RapidOCR()
    return _rapid_engine


def _ocr_boxes(img_path):
    """rapidocr → [(text, x, y)]；失败则 tesseract TSV fallback。"""
    try:
        eng = _get_rapid()
        result, _ = eng(str(img_path))
        out = []
        for box, text, _s in (result or []):
            out.append((text, int(box[0][0]), int(box[0][1])))
        if out:
            return out
    except Exception:
        pass
    return _ocr_tsv(img_path)


def _parse_cert(cert_str):
    """从素材清单 personnel.cert 解析证书名称/编号：
    '省监理工程师岗位证书皖监师2020000823'→('省监理工程师岗位证书','2020000823')"""
    s = cert_str or ""
    s = re.sub(r"（[^）]*）", "", s)
    n = re.search(r"(\d{6,})", s)
    names = re.findall(r"[\u4e00-\u9fff]{2,12}?(?:注册证|岗位证书|师证书|证书|师证|证)", s)
    name = max(names, key=len) if names else ""
    return name, (n.group(1) if n else "")


# 宽松标签（rapidocr 可能拆段/漏字）：(标签, 简历表占位键, 值清洗)
# 注：从事设计/从事造价年限扫描件通常为空且易与「从事施工」错位 → 不提取，保留占位待补
_LOOSE_LABELS = [
    ("主要经历", "主要经历", None),
    ("相关专业", "相关专业经历", None),
    ("居民身份证", "身份证号", "去号码前缀"),
    ("从事监理", "从事监理工作年限（年）", "去尾部工作年限"),
    ("聘任时间", "聘任时间", None),
    ("技术职称", "技术职称", None),
    ("现任职务", "现任职务", None),
    ("政治面貌", "政治面貌", None),
    ("毕业院校", "毕业院校专业及时间", "去专业及时间前缀|毕业院校重排"),
    ("最终学历", "学历", None),
    ("出生年月", "出生年月", None),
    ("性别", "性别", None),
    ("姓名", "人员姓名", None),
]


def _cluster_rows(cells, tol=30):
    """rapidocr 文本按 y 聚类成表格行（同一行 y 浮动容忍 30px）；行内按 x 排序、
    x 差 <10 的拆段合并；输出 [{y0, s(紧凑无空格)}] 按 y 升序。"""
    rows = []
    for text, x, y in sorted(cells, key=lambda c: (c[2], c[1])):
        for r in rows:
            if abs(y - r["y0"]) <= tol:
                r["items"].append((text, x))
                break
        else:
            rows.append({"y0": y, "items": [(text, x)]})
    out = []
    for r in rows:
        items = sorted(r["items"], key=lambda t: t[1])
        merged = []
        for text, x in items:
            if merged and x - merged[-1][1] < 10:
                merged[-1] = (merged[-1][0] + text, merged[-1][1])
            else:
                merged.append((text, x))
        out.append({"y0": r["y0"], "s": "".join(t for t, _ in merged).replace(" ", "")})
    return sorted(out, key=lambda r: r["y0"])


def _clean_val(val, mode):
    if not mode:
        return val
    for m in mode.split("|"):
        if m == "去尾部工作年限":
            val = re.split(r"工作年限", val)[0]
        elif m == "去号码前缀":
            val = re.sub(r"^(号码?|码)", "", val)
        elif m == "去专业及时间前缀":
            val = re.sub(r"^专业及时间", "", val)
        elif m == "毕业院校重排":
            mm = re.match(r"^(管理/\S+)(建筑施工与.*)$", val)
            if mm:
                val = mm.group(2) + mm.group(1)
    return val


def _extract_row_fields(rows):
    fields = {}
    for r in rows:
        s = r["s"]
        if len(s) <= 20 and "简历" in s:      # 标题行（拟投入监理人员简历表）
            continue
        for lab, ph, clean in _LOOSE_LABELS:
            if ph is None or ph in fields:
                continue
            pos = s.find(lab)
            if pos < 0:
                continue
            after = s[pos + len(lab):]
            nxt = len(after)
            for lab2, _ph2, _c2 in _LOOSE_LABELS:
                p2 = after.find(lab2)
                if 0 <= p2 < nxt:
                    nxt = p2
            val = _clean_val(after[:nxt].strip(), clean)
            if val:
                fields[ph] = val
    return fields


def _extract_experience(rows, fields):
    """相关专业经历/主要经历跨行提取（经历文本在证书表之后多行）。"""
    if not rows:
        return
    start_i = end_i = None
    for i, r in enumerate(rows):
        if "相关专业" in r["s"]:
            start_i = i
            break
    if start_i is not None:
        for i in range(start_i + 1, len(rows)):
            if "主要经历" in rows[i]["s"] or "要经历" in rows[i]["s"]:
                end_i = i
                break
        seg = rows[start_i]["s"]
        seg = seg[seg.find("相关专业") + len("相关专业"):]
        for j in range(start_i + 1, end_i if end_i is not None else len(rows)):
            seg += rows[j]["s"]
        if end_i is not None:
            s2 = rows[end_i]["s"]
            if "主要经历" in s2:
                seg += s2[s2.find("主要经历") + len("主要经历"):]
            else:
                seg += s2[s2.find("要经历") + len("要经历"):]
        seg = re.sub(r"^经历", "", seg.strip())
        seg = re.sub(r"经历(?=\d)", "；", seg)     # 标签拆段残渣 → 分号分隔
        if seg:
            fields["相关专业经历"] = seg
    if "主要经历" not in fields:
        for i in range(len(rows) - 1, -1, -1):
            s = rows[i]["s"]
            pos = s.find("主要经历")
            tag = "主要经历"
            if pos < 0:
                pos = s.find("要经历")
                tag = "要经历"
            if pos >= 0:
                v = s[pos + len(tag):]
                for j in range(i + 1, len(rows)):
                    v += rows[j]["s"]
                v = v.strip()
                if v:
                    fields["主要经历"] = v
                break


def ocr_resume_fields(png_path, cert_str=None):
    """OCR 简历扫描件 → {简历表占位符: 值}（rapidocr，行聚类+宽松标签+跨行经历）。"""
    cells = _ocr_boxes(png_path)
    if not cells:
        return {}
    rows = _cluster_rows(cells)
    fields = _extract_row_fields(rows)
    _extract_experience(rows, fields)
    # 性别 fallback：OCR 漏识别「男/女」时按身份证号第 17 位奇偶推断（奇=男 偶=女）
    if not fields.get("性别"):
        idno = fields.get("身份证号", "")
        if len(idno) >= 17 and idno[16].isdigit():
            fields["性别"] = "男" if int(idno[16]) % 2 else "女"
    # 证书名称/编号：优先素材清单 cert 解析（结构化可靠）
    if cert_str:
        cname, cno = _parse_cert(cert_str)
        if cno and "证书编号" not in fields:
            fields["证书编号"] = cno
        if cname and "证书名称" not in fields:
            fields["证书名称"] = cname
    return fields


def _find_resume_scan(lib_root, name):
    """人员简历扫描件：人员/<姓名>/简历/*.png（取 P0 或首个）。"""
    d = Path(lib_root) / "人员" / name / "简历"
    if not d.is_dir():
        return None
    files = sorted(d.glob("*.png")) + sorted(d.glob("*.jpg")) + sorted(d.glob("*.jpeg"))
    if not files:
        return None
    p0 = [f for f in files if "P0" in f.name]
    return str((p0 or files)[0])


# ---------------------------------------------------------------------------
# 图片插入
# ---------------------------------------------------------------------------
def _insert_image(p, img_path, w_cm, h_cm):
    """段落 p：清文本后新增 run 插入图片（宽高 Cm）。"""
    _set_para_text(p, "")
    run = p.add_run()
    run.add_picture(str(img_path), width=Cm(w_cm), height=Cm(h_cm))


def _fill_image_placeholders(doc, lib_root, missing):
    """段落级【图片：xxx】：取图插入（按口径），删除占位段；缺图删除占位 + missing。"""
    for p in list(doc.paragraphs):
        t = _para_full_text(p).strip()
        if not (t.startswith("【图片：") and t.endswith("】")):
            continue
        spec_key = imgsp.spec_for(t)
        mapped = FILL_IMG_MAP.get(t)
        if not mapped:
            missing.append((t, "无填充规则"))
            p._p.getparent().remove(p._p)
            continue
        path, rule_key, note = mapped
        if path is None:
            missing.append((t, note))
            p._p.getparent().remove(p._p)
            continue
        full = Path(lib_root) / path
        if not full.is_file():
            missing.append((t, "素材库缺文件: %s" % path))
            p._p.getparent().remove(p._p)
            continue
        size = imgsp.fit_size(str(full), rule_key)
        if not size:
            missing.append((t, "口径键缺失: %s" % rule_key))
            p._p.getparent().remove(p._p)
            continue
        _insert_image(p, str(full), size[0], size[1])


def _fill_cell_image(cell, img_path, w_cm, h_cm):
    """表格单元格内图片占位：首段落插图。"""
    p = cell.paragraphs[0] if cell.paragraphs else cell.add_paragraph()
    _set_para_text(p, "")
    _insert_image(p, img_path, w_cm, h_cm)


# ---------------------------------------------------------------------------
# 表格填充
# ---------------------------------------------------------------------------
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


def _scan_remaining_placeholders(doc, fname, pending):
    """填充后残留【xxx】扫描 → 待补清单（未映射/缺值的占位符）。"""
    seen = set()
    for p in _iter_doc_paragraphs(doc):
        for ph in re.findall(r"【[^】]+】", _para_full_text(p)):
            if ph not in seen:
                seen.add(ph)
                pending.append("%s：残留占位符（%s）" % (ph, fname))
    return len(seen)


def _fill_text_placeholders(doc, material, biz, deadline, pending):
    """段落级文字占位：映射有值则替换；无映射/值空 → pending 保留占位。"""
    filled = 0
    # 正文括注占位（非【】格式）：中小企业声明函「承接企业为（企业名称）」
    biz_name = biz.get("投标人名称", "") or ""
    if biz_name:
        for p in _iter_doc_paragraphs(doc):
            t = _para_full_text(p)
            if "（企业名称）" in t:
                _set_para_text(p, t.replace("（企业名称）", biz_name))
                filled += 1
    for p in _iter_doc_paragraphs(doc):
        t = _para_full_text(p)
        if "【" not in t:
            continue
        for ph, (key, note) in TEXT_KEY_MAP.items():
            if ph not in t:
                continue
            if key == "_pending":
                pending.append("%s → %s（保留占位待补）" % (ph, note))
                continue
            if key == "_director":
                ps = material.get("personnel", [])
                v = ps[0].get("name", "") if ps else ""
            elif key == "_director_major":
                v = "市政公用工程"
            elif key == "_qual_level":
                v = "房屋建筑工程监理甲级；市政公用工程监理乙级"
            elif key == "_bail_cap":
                v = "壹万元整"
            elif key == "投标截止日期":
                v = _fmt_date(deadline)
            else:
                v, _ = _mat_value(material, biz, key)
            if not v:
                pending.append("%s → %s（值缺失，保留占位待补）" % (ph, note))
                continue
            _set_para_text(p, t.replace(ph, v))
            filled += 1
            t = _para_full_text(p)
    return filled


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def _load_material(proj_dir):
    p = Path(proj_dir) / "招标解析" / "素材清单.json"
    return core.read_json(str(p), None) or {}


def _load_deadline(proj_dir):
    p = Path(proj_dir) / "招标解析" / "投标要点.json"
    data = core.read_json(str(p), None) or {}
    return data.get("overview", {}).get("deadline", "") or \
        data.get("deadline", "") or "2026-10-09"


def fill_project(ent, proj_dir, out_dir=None, lib_root=None, register=True):
    """项目模板（冻结版）→ 商务标。返回统计。"""
    if not HAVE_DOCX:
        raise FillError("填充引擎依赖 python-docx，当前环境未安装")
    ent = Path(ent)
    proj_dir = Path(proj_dir)
    lib_root = Path(lib_root) if lib_root else ent / "企业级" / "素材库"
    tpl_dir = proj_dir / "项目模板"
    out = Path(out_dir) if out_dir else proj_dir / "商务标"
    out.mkdir(parents=True, exist_ok=True)

    material = _load_material(proj_dir)
    biz = material.get("企业基础信息", {}) or {}
    deadline = material.get("投标截止日期", "") or _load_deadline(proj_dir)

    stats = {"文件": [], "缺图": [], "待补": [], "文字占位填充": 0}
    for f in sorted(tpl_dir.glob("*.docx")):
        doc = Document(str(f))
        missing, pending = [], []
        filled = _fill_text_placeholders(doc, material, biz, deadline, pending)
        _fill_image_placeholders(doc, lib_root, missing)
        _fill_personnel_tables(doc, material, pending)
        _fill_resume_tables(doc, lib_root, material, pending)
        _fill_performance_tables(doc, material, pending)
        # 残留占位符扫描 → 待补清单
        _scan_remaining_placeholders(doc, f.name, pending)
        # 表内图片占位（组织机构框图）
        for t in doc.tables:
            for row in t.rows:
                for cell in row.cells:
                    ct = cell.text.strip()
                    if ct.startswith("【图片：") and "组织机构框图" in ct:
                        src = Path(lib_root) / "企业介绍/组织机构图_20261001.png"
                        if src.is_file():
                            _fill_cell_image(cell, str(src), 15, 8.5)
                        else:
                            missing.append((ct, "组织机构图素材缺失"))
        doc.save(str(out / f.name))
        stats["文件"].append({"文件": f.name, "填充文字": filled,
                              "缺图": [x[0] for x in missing],
                              "待补": list(dict.fromkeys(pending))})
        stats["缺图"] += [tuple(x) for x in missing]
        stats["待补"] += pending
        stats["文字占位填充"] += filled

    stats["缺图"] = list(dict.fromkeys(stats["缺图"]))
    stats["待补"] = list(dict.fromkeys(stats["待补"]))
    _write_reports(out, stats, deadline)
    if register:
        core.write_json(str(out / "生成记录.json"), {
            "id": FILL_ID, "version": FILL_VERSION, "日期": deadline,
            "项目": material.get("project", ""),
            "统计": {k: v for k, v in stats.items() if k not in ("文件",)},
        })
    return stats


def _write_reports(out, stats, deadline):
    lines = ["# 缺图清单（商务标生成 %s）" % _fmt_date(deadline), "",
             "以下图片素材缺失，占位段已删除；补齐后重新生成商务标：", ""]
    for ph, note in stats["缺图"]:
        lines.append("- %s（%s）" % (ph, note))
    if not stats["缺图"]:
        lines.append("- 无")
    (out / "缺图清单.md").write_text("\n".join(lines), encoding="utf-8")

    lines = ["# 待补字段清单（商务标生成 %s）" % _fmt_date(deadline), "",
             "以下文字占位无值或待确认，**保留占位符**，交标前人工填写：", ""]
    for x in stats["待补"]:
        lines.append("- %s" % x)
    if not stats["待补"]:
        lines.append("- 无")
    (out / "待补字段清单.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="M5 填充引擎：项目模板 → 商务标")
    ap.add_argument("--ent", default=r"E:\监理标书制作\示例建设工程监理有限公司")
    ap.add_argument("--proj", default=r"E:\监理标书制作\示例建设工程监理有限公司\项目级\示例示例园区尾水水质提升工程（EPC总承包）监理")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    s = fill_project(args.ent, args.proj, out_dir=args.out)
    print(json.dumps({k: v for k, v in s.items() if k != "文件"},
                     ensure_ascii=False, indent=1))
