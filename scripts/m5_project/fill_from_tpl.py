# -*- coding: utf-8 -*-
"""
M5（v3 适配版）商务标生成引擎：企业级模板库深拷贝 → 项目模板 → 占位填充。

用户 2026-10-19 定案流程（替代 proj-gen 招标原文深拷贝路径）：
  1) 深拷贝 企业级模板库/<代理机构>/商务标母版-招标式/ 9 件 → 项目模板/
  2) 按素材清单填充：文字占位（{{ }}）+ 图片占位（表格图框）
  3) 图片一律按模板单元格宽×行高等比适配（fit inside cell box）
  4) 一页两张图片的，两图之间插入 1cm 间距行（trHeight exact + 段落 line exact 双保险）
  5) 未命中不兜底：缺图/待补/清单外逐项披露到报告，交用户处理

模块契约：脚本平台无关（不依赖豆包私有能力）；素材一旦归档受保护，本模块只读。
"""
import json
import re
import shutil
from pathlib import Path

from _shared import core            # noqa: E402

from .fill_common import FILL_ID, FILL_VERSION, HAVE_DOCX, FillError   # noqa: E402

try:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Cm
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.text.paragraph import Paragraph
    from copy import deepcopy
except Exception:  # pragma: no cover
    Document = None

from .image_spec import fit_size     # noqa: E402

# 模板库 9 件（企业级母版，文件顺序即生成顺序）
TPL_FILES = ["封面.docx", "投标函.docx", "投标函附录.docx", "授权委托书.docx",
             "法定代表人身份证明.docx", "承诺书.docx", "其他.docx",
             "投标单位业绩材料和奖项.docx", "资格证明及辅助资料表.docx"]

# 采购式 6 件（大成·采购式骨架，2026-10-19 定案：以已完标书为准拆分，无附录/承诺书/其他/业绩奖项件）
TPL_FILES_PH = ["封面.docx", "开标一览表.docx", "投标函.docx",
                "法定代表人身份证明.docx", "授权委托书.docx",
                "资格证明及辅助资料表.docx"]


def _load_material(proj_dir):
    """读素材清单：优先 素材清单.json，回退 素材清单_<项目>.json。"""
    p = Path(proj_dir) / "招标解析"
    for name in ("素材清单.json",):
        f = p / name
        if f.is_file():
            return core.read_json(str(f), None) or {}
    # 回退带项目名前缀
    cands = sorted(p.glob("素材清单_*.json"))
    if cands:
        return core.read_json(str(cands[0]), None) or {}
    return {}


def _fmt_date(s):
    if not s:
        return s
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", str(s))
    if m:
        return "%s年%s月%s日" % (m.group(1), m.group(2), m.group(3))
    return str(s)


# ==================== 占位替换 ====================
def iter_textbox_paragraphs(doc):
    """遍历文档中所有文本框（w:txbxContent）内的段落（python-docx doc.paragraphs 不可见）。
    模板库母版图片占位段多为文本框内段落（2026-10-19 端到端试跑发现），
    填充引擎必须覆盖；parent=doc 提供 part 供插图/文本替换使用。"""
    body = doc.element.body
    for txbx in body.iter(qn("w:txbxContent")):
        for p_el in txbx.iter(qn("w:p")):
            yield Paragraph(p_el, doc)


def repl_braces(text, vmap, perf_seq_ref):
    """{{ }} 占位替换：业绩项目名称按序消费 perf_seq。"""
    def rep(m):
        k = m.group(1).strip()
        if k == "业绩项目名称":
            if perf_seq_ref[0] < len(perf_seq_ref[1]):
                v = perf_seq_ref[1][perf_seq_ref[0]]
                perf_seq_ref[0] += 1
                return v
            return m.group(0)
        return vmap.get(k, m.group(0))
    return re.sub(r"\{\{\s*([^}]+?)\s*\}\}", rep, text)


def fill_braces_doc(doc, vmap, perf_seq=None):
    perf_ref = [0, perf_seq or []]
    used = 0
    for para in doc.paragraphs:
        full = para.text or ""
        # 图片占位文案（【图片占位：…】）只是给人工看的说明标记，其中的 {{ }} 不做文本替换
        # （业绩名称/人员名等由图片填充按行列定位；缺图时保留原标记）
        if "{{" in full and "【图片占位：" not in full:
            nt = repl_braces(full, vmap, perf_ref)
            if nt != full:
                for r in para.runs[1:]:
                    r._r.getparent().remove(r._r)
                if para.runs:
                    para.runs[0].text = nt
                used += 1
    for tbl in doc.tables:
        for row in tbl.rows:
            for cell in row.cells:
                for para in cell.paragraphs:
                    full = para.text or ""
                    if "{{" in full and "【图片占位：" not in full:
                        nt = repl_braces(full, vmap, perf_ref)
                        if nt != full:
                            for r in para.runs[1:]:
                                r._r.getparent().remove(r._r)
                            if para.runs:
                                para.runs[0].text = nt
                            used += 1
    # 文本框内段落（母版图片占位段常见于此，{{ }} 文字占位同样覆盖）
    for para in iter_textbox_paragraphs(doc):
        full = para.text or ""
        if "{{" in full and "【图片占位：" not in full:
            nt = repl_braces(full, vmap, perf_ref)
            if nt != full:
                for r in para.runs[1:]:
                    r._r.getparent().remove(r._r)
                if para.runs:
                    para.runs[0].text = nt
                used += 1
    return used


# ==================== 图片填充（按单元格宽×行高适配） ====================
def cell_box_cm(cell):
    """返回 (max_w_cm, max_h_cm)：单元格宽 + 行高（exact/atLeast，twips/567=cm）。"""
    mw = cell.width / 360000.0 if cell.width else 16.0
    mh = 24.6
    tr = cell._tc.getparent()          # tc → tr
    if tr is not None:
        trPr = tr.find(qn("w:trPr"))
        if trPr is not None:
            trH = trPr.find(qn("w:trHeight"))
            if trH is not None:
                val = trH.get(qn("w:val"))
                if val:
                    mh = int(val) / 567.0
    return mw, mh


def _resolve(p, proj):
    """素材路径解析：绝对路径直用；相对路径按项目目录解析。
    容错：历史素材清单将『企业级\项目级』误拼入项目级路径，自动纠偏。"""
    if not p:
        return ""
    p = str(p)
    # 纠偏：企业级\项目级\... → 项目级\...（素材清单历史数据缺陷）
    p = re.sub(r"企业级[\\/]+项目级", "项目级", p)
    p = Path(p)
    if p.is_absolute() and p.is_file():
        return str(p)
    cand = proj / p
    return str(cand) if cand.is_file() else str(p)


def insert_img_fit_cell(para, img_path, spec_key, mw, mh):
    """按单元格 max_w/max_h 等比适配插图（水平居中）。"""
    if not img_path or not Path(img_path).is_file():
        return False
    size = fit_size(img_path, spec_key, max_w=mw, max_h=mh)
    if not size:
        return False
    w, h = size
    for r in list(para.runs):
        r._r.getparent().remove(r._r)
    para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    para.add_run().add_picture(str(img_path), width=Cm(w), height=Cm(h))
    return True


def fill_img_table_cell(doc, ti, ri, ci, img_path, spec_key):
    try:
        cell = doc.tables[ti].rows[ri].cells[ci]
    except Exception:
        return False
    for para in cell.paragraphs:
        if "【图片占位：" in (para.text or ""):
            mw, mh = cell_box_cm(cell)
            return insert_img_fit_cell(para, img_path, spec_key, mw, mh)
    return False


def insert_gap_row_after(tbl, row_idx, gap_cm=1.0):
    """在 row_idx 行后插入 gap 空行（trHeight exact + 段落 line exact 双保险）。"""
    src_tr = tbl.rows[row_idx]._tr
    new_tr = deepcopy(src_tr)
    for tc in new_tr.findall(qn("w:tc")):
        for p in tc.findall(qn("w:p")):
            for node in list(p):
                if node.tag != qn("w:pPr"):
                    p.remove(node)
            pPr = p.find(qn("w:pPr"))
            if pPr is None:
                pPr = OxmlElement("w:pPr")
                p.insert(0, pPr)
            for old in pPr.findall(qn("w:spacing")):
                pPr.remove(old)
            sp = OxmlElement("w:spacing")
            sp.set(qn("w:line"), str(int(gap_cm * 567)))
            sp.set(qn("w:lineRule"), "exact")
            pPr.append(sp)
    trPr = new_tr.find(qn("w:trPr"))
    if trPr is None:
        trPr = OxmlElement("w:trPr")
        new_tr.insert(0, trPr)
    for trH in trPr.findall(qn("w:trHeight")):
        trPr.remove(trH)
    trH = OxmlElement("w:trHeight")
    trH.set(qn("w:val"), str(int(gap_cm * 567)))
    trH.set(qn("w:hRule"), "exact")
    trPr.append(trH)
    src_tr.addnext(new_tr)


def add_gap_between_two_img_rows(doc, ti, gap_cm=1.0):
    """双图框表格（已知索引）行 0/行 1 之间插 gap。fill 后占位文字已消失，
    故按「行内含图片」检测 + 已有 gap 行跳过。"""
    try:
        tbl = doc.tables[ti]
    except IndexError:
        return False
    if len(tbl.rows) < 2:
        return False

    def has_img(row):
        for cell in row.cells:
            for para in cell.paragraphs:
                if para._p.find(".//" + qn("w:drawing")) is not None:
                    return True
        return False

    if not (has_img(tbl.rows[0]) and has_img(tbl.rows[1])):
        return False
    if len(tbl.rows) > 2:
        return False
    insert_gap_row_after(tbl, 0, gap_cm)
    return True


# ==================== 采购式资格证明行/表级填充（2026-10-19 重配） ====================
def _repl_cell_keys(cell, mapping):
    """单元格内 {{ }} 键替换（保留格式：只改首 run，清空其余 run）。"""
    for para in cell.paragraphs:
        t = para.text or ""
        nt = t
        for k, v in mapping.items():
            nt = nt.replace("{{ " + k + " }}", v).replace("{{" + k + "}}", v)
        if nt != t:
            for r in list(para.runs[1:]):
                r._r.getparent().remove(r._r)
            if para.runs:
                para.runs[0].text = nt


def _repl_para_keys(para, mapping):
    """单段 {{ }} 键替换（简历经历段按段独立消费）。"""
    t = para.text or ""
    nt = t
    for k, v in mapping.items():
        nt = nt.replace("{{ " + k + " }}", v).replace("{{" + k + "}}", v)
    if nt != t:
        for r in list(para.runs[1:]):
            r._r.getparent().remove(r._r)
        if para.runs:
            para.runs[0].text = nt


def fill_cgys_qual_rows(doc, material):
    """采购式资格证明行/表级填充：表1业绩汇总(行1-4)、表2-5业绩明细(每表1条)、
    表9人员配备(行1-4)、表10-13简历(每表1人，含经历段按段消费)。
    先行级替换表格键，fill_braces_doc 只处理正文残余——键已消费不再被全局覆盖。"""
    perf = material.get("performance") or []
    staff = material.get("personnel") or []
    # 表1 业绩汇总：行1..N 按 perf（列：业主名称1/项目名称2/合同金额4/起止时间5）
    try:
        t = doc.tables[1]
        for i, row in enumerate(t.rows[1:1 + len(perf)]):
            mapping = {
                "业绩业主单位": perf[i].get("业主单位") or "",
                "业绩项目名称": perf[i].get("name") or "",
                "业绩合同金额": perf[i].get("合同金额") or "",
                "业绩起止时间": perf[i].get("起止时间") or "",
            }
            for c in row.cells:
                _repl_cell_keys(c, mapping)
    except Exception:
        pass
    # 表2-5 业绩明细：每表 1 条
    for ti in range(2, 2 + min(4, len(perf))):
        try:
            tbl = doc.tables[ti]
        except Exception:
            continue
        it = perf[ti - 2]
        mapping = {
            "业绩业主单位": it.get("业主单位") or "",
            "业绩项目名称": it.get("name") or "",
            "业绩合同金额": it.get("合同金额") or "",
            "业绩起止时间": it.get("起止时间") or "",
            "业绩监理服务期": it.get("监理服务期") or "",
            "姓名": staff[0].get("name") if staff else "",
        }
        for row in tbl.rows:
            for c in row.cells:
                _repl_cell_keys(c, mapping)
    # 表9 人员配备：行1..N 按 staff（列：姓名1/年龄2/学历3/专业4/职称5/职务6）
    try:
        t = doc.tables[9]
        for i, row in enumerate(t.rows[1:1 + len(staff)]):
            mapping = {
                "人员姓名": staff[i].get("name") or "",
                "人员年龄": staff[i].get("年龄") or "",
                "人员学历": staff[i].get("学历") or "",
                "人员专业": staff[i].get("专业") or "",
                "人员职称": staff[i].get("职称") or "",
                "人员职务": staff[i].get("职务") or "",
            }
            for c in row.cells:
                _repl_cell_keys(c, mapping)
    except Exception:
        pass
    # 表10-13 简历：每表 1 人（姓名/性别/出生/学历/专业/职称/职务 + 经历段按段消费）
    for ti in range(10, 10 + min(4, len(staff))):
        try:
            tbl = doc.tables[ti]
        except Exception:
            continue
        p0 = staff[ti - 10]
        exp = p0.get("经历") or []
        mapping = {
            "人员姓名": p0.get("name") or "",
            "人员出生年月": p0.get("出生年月") or "",
            "人员学历": p0.get("学历") or "",
            "人员专业": p0.get("专业") or "",
            "人员职称": p0.get("职称") or "",
            "人员职务": p0.get("职务") or "",
        }
        cnt_t, cnt_p = 0, 0
        for row in tbl.rows:
            for c in row.cells:
                for para in c.paragraphs:
                    t = para.text or ""
                    has_t = "人员经历时间" in t
                    has_p = "人员经历项目" in t
                    if not (has_t or has_p):
                        _repl_cell_keys(c, mapping)
                        continue
                    # 经历段：同段非经历键（姓名/职务/职称等）+ 经历键一并替换；
                    # 经历素材缺失时经历键保留 → scan_residual 披露待补（不静默删）
                    m2 = dict(mapping)
                    if has_t and cnt_t < len(exp):
                        m2["人员经历时间"] = exp[cnt_t].get("时间") or ""
                    if has_p and cnt_p < len(exp):
                        m2["人员经历项目"] = exp[cnt_p].get("项目") or ""
                    _repl_para_keys(para, m2)
                    if has_t:
                        cnt_t += 1
                    if has_p:
                        cnt_p += 1


def _flat_paths(items):
    """素材对象展平路径：path 字段 + paths 列表（去空）。"""
    out = []
    for it in items or []:
        if isinstance(it, dict):
            if it.get("path"):
                out.append(str(it["path"]))
            for p in it.get("paths") or []:
                if p:
                    out.append(str(p))
    return out


def fill_cgys_images(doc, material, missing):
    """采购式资格证明图占位：按图占位文案关键词分类填充（_fill_kw 依序消费素材路径）。
    素材缺/空不兜底，逐项披露到缺图清单。"""
    iso = _flat_paths(material.get("iso_certificates"))
    ss = []
    for it in material.get("social_security_required") or []:
        ss += [str(p) for p in it.get("paths") or [] if p]
    perf_paths = [str(p) for it in material.get("performance") or [] for p in (it.get("paths") or [])]
    qual = [it.get("path") for it in material.get("qualification_required") or [] if it.get("path")]
    staff = material.get("personnel") or []

    def per_paths(idx, kind):
        if idx < len(staff):
            return [str(x) for x in (staff[idx].get(kind) or []) if x]
        return []

    honors = material.get("honors") or []
    honor_paths = [h.get("path", "") for h in honors if h.get("path", "")]
    _fill_kw(doc, "三体系认证证书", iso, "三体系认证证书", missing)
    _fill_kw(doc, "社保证明", ss, "社保证明", missing)
    _fill_kw(doc, "业绩材料", perf_paths, "业绩合同验收报告", missing)
    _fill_kw(doc, "企业资质证书", qual, "企业资质证书", missing)
    _fill_kw(doc, "总监理工程师注册执业证书", per_paths(0, "注册证书"), "注册监理工程师证书", missing)
    _fill_kw(doc, "总监一级造价师证书", per_paths(0, "一级造价师证书"), "一级造价工程师证书", missing)
    _fill_kw(doc, "专业监理工程师中级职称", per_paths(1, "职称证书") or per_paths(1, "职称"), "职称证书", missing)
    _fill_kw(doc, "拟派项目总监的优秀总监证书", honor_paths, "优秀总监证书", missing)
    _fill_kw(doc, "先进（优秀）监理企业证书", honor_paths, "先进监理企业证书", missing)
    _fill_kw(doc, "证明材料", [], "证明材料", missing)


# ==================== 素材索引（从素材清单动态取路径） ====================
def build_maps(material):
    biz = material.get("企业基础信息", {}) or {}
    persons = {p["name"]: p for p in material.get("personnel", [])}
    Q = {it["name"]: it for it in material.get("qualification_required", [])}

    def q(name):
        it = Q.get(name)
        return (it.get("path") or "") if it else ""

    def p(name, kind, idx=0):
        per = persons.get(name)
        if not per:
            return ""
        lst = per.get(kind) or []
        return lst[idx] if idx < len(lst) else ""

    def honor(kw):
        for h in material.get("honors", []):
            if kw in h.get("name", ""):
                return h.get("path", "") or ""
        return ""

    PERF = {}
    for it in material.get("performance", []):
        nm = it.get("name", "")
        key = "横江" if "横江" in nm else ("南北" if ("南北" in nm or "北部" in nm) else nm)
        PERF[key] = it.get("paths") or []

    ss = [str(Path(pth).as_posix()) for pth in
          (material.get("social_security_required") or [{}])[0].get("paths", [])]

    # 资格表 65 图框（索引依赖大成资格表模板结构）
    CELL_MAP = [
        ((1, 0, 0), q("企业资质证书（房屋建筑工程监理甲级）"), "资质证书_房屋建筑工程甲级"),
        ((2, 0, 0), q("企业资质证书（市政公用工程监理乙级）"), "资质证书_市政公用工程乙级"),
        ((3, 0, 0), q("企业法人营业执照（副本）"), "营业执照扫描件"),
        ((4, 0, 0), p("陈云", "注册证书", 0), "注册监理工程师证书"),
        ((5, 0, 0), q("企业基本账户开户许可证"), "开户许可证扫描件"),
        ((5, 1, 0), "", "存款信息"),                       # 保证金回单（项目资料）填充时补
        ((10, 0, 0), PERF.get("横江", [""])[0], "业绩合同验收报告_竖版"),
        ((11, 0, 0), PERF.get("横江", [""])[1], "业绩合同验收报告_竖版"),
        ((12, 0, 0), PERF.get("横江", [""])[2], "业绩合同验收报告_竖版"),
        ((13, 0, 0), PERF.get("横江", [""])[3], "业绩合同验收报告_竖版"),
        ((15, 0, 0), PERF.get("南北", [""])[0], "业绩合同验收报告_竖版"),
        ((16, 0, 0), PERF.get("南北", [""])[1], "业绩合同验收报告_竖版"),
        ((17, 0, 0), PERF.get("南北", [""])[2], "业绩合同验收报告_竖版"),
        ((18, 0, 0), PERF.get("南北", [""])[3], "业绩合同验收报告_竖版"),
        ((19, 0, 0), PERF.get("南北", [""])[4], "业绩合同验收报告_竖版"),
        ((20, 0, 0), PERF.get("南北", [""])[5], "业绩合同验收报告_竖版"),
        ((24, 0, 0), p("陈云", "注册证书", 0), "注册监理工程师证书"),
        ((25, 0, 0), p("陈云", "职称", 0), "职称证"),
        ((25, 1, 0), p("陈云", "职称", 1), "职称证"),
        ((26, 0, 0), p("陈云", "身份证", 0), "身份证"),
        ((26, 2, 0), p("陈云", "身份证", 1), "身份证"),
        ((28, 0, 0), p("陈友龙", "注册证书", 0), "注册监理工程师证书"),
        ((29, 0, 0), p("陈友龙", "职称", 0), "职称证"),
        ((29, 1, 0), p("陈友龙", "职称", 1), "职称证"),
        ((30, 0, 0), p("陈友龙", "身份证", 0), "身份证"),
        ((30, 2, 0), p("陈友龙", "身份证", 1), "身份证"),
        ((32, 0, 0), p("吴志水", "岗位证书", 0), "岗位证书"),
        ((33, 0, 0), p("吴志水", "职称", 0), "职称证"),
        ((33, 1, 0), p("吴志水", "职称", 1), "职称证"),
        ((34, 0, 0), p("吴志水", "身份证", 0), "身份证"),
        ((34, 2, 0), p("吴志水", "身份证", 1), "身份证"),
        ((36, 0, 0), p("裴友谊", "岗位证书", 0), "岗位证书"),
        ((37, 0, 0), p("裴友谊", "职称", 0), "职称证"),
        ((37, 1, 0), p("裴友谊", "职称", 1), "职称证"),
        ((38, 0, 0), p("裴友谊", "身份证", 0), "身份证"),
        ((38, 2, 0), p("裴友谊", "身份证", 1), "身份证"),
        ((40, 0, 0), p("阮旭", "岗位证书", 0), "岗位证书"),
        ((41, 0, 0), p("阮旭", "身份证", 0), "身份证"),
        ((41, 2, 0), p("阮旭", "身份证", 1), "身份证"),
        ((43, 0, 0), p("黄诚", "岗位证书", 0), "岗位证书"),
        ((44, 0, 0), p("黄诚", "身份证", 0), "身份证"),
        ((44, 2, 0), p("黄诚", "身份证", 1), "身份证"),
        ((45, 0, 0), ss[0] if ss else "", "社保证明"),
        ((46, 0, 0), ss[1] if ss else "", "社保证明"),
        ((49, 0, 0), material.get("iso_certificates", [{}])[0].get("path", ""), "三体系认证证书"),
        ((50, 0, 0), material.get("iso_certificates", [{}])[1].get("path", ""), "三体系认证证书"),
        ((51, 0, 0), material.get("iso_certificates", [{}])[2].get("path", ""), "三体系认证证书"),
        ((52, 0, 0), p("陈云", "职称", 0), "总监高级工程师职称证书"),
        ((52, 1, 0), p("陈云", "职称", 1), "总监高级工程师职称证书"),
        ((53, 0, 0), p("陈友龙", "职称", 0), "小型职称证书"),
        ((54, 0, 0), p("陈友龙", "职称", 1), "小型职称证书"),
        ((55, 0, 0), p("吴志水", "职称", 2), "小型职称证书"),
        ((55, 1, 0), p("吴志水", "职称", 1), "小型职称证书"),
        ((56, 0, 0), p("裴友谊", "职称", 0), "小型职称证书"),
        ((56, 1, 0), p("裴友谊", "职称", 1), "小型职称证书"),
        ((57, 0, 0), honor("优秀监理企业_20230201") or honor("2021"), "先进优秀监理企业证书"),
        ((57, 1, 0), honor("优秀监理企业_20240301") or honor("2022"), "先进优秀监理企业证书"),
        ((58, 0, 0), honor("优秀监理企业_20250101") or honor("2023"), "先进优秀监理企业证书"),
        ((58, 1, 0), honor("先进监理企业"), "先进优秀监理企业证书"),
        ((59, 0, 0), honor("监理示范工程_20241201") or honor("2024"), "监理示范优质工程"),
        ((59, 1, 0), honor("监理示范工程_20251201") or honor("2025"), "监理示范优质工程"),
        ((60, 0, 0), honor("安全生产标准化示范工地"), "监理示范优质工程"),
        ((60, 1, 0), honor("黄山杯"), "监理示范优质工程"),
        ((61, 0, 0), q("企业基本账户开户许可证"), "存款信息"),
        ((62, 0, 0), q("企业基本账户开户许可证"), "存款信息"),
    ]

    # 业绩奖项 32 图框（T13/T14 项目说明 3 图框未命中时跳过）
    YJ_MAP = [
        ((0, 0), material.get("iso_certificates", [{}])[0].get("path", ""), "三体系认证证书"),
        ((1, 0), material.get("iso_certificates", [{}])[1].get("path", ""), "三体系认证证书"),
        ((2, 0), material.get("iso_certificates", [{}])[2].get("path", ""), "三体系认证证书"),
        ((3, 0), PERF.get("横江", [""])[0], "业绩合同验收报告_竖版"),
        ((4, 0), PERF.get("横江", [""])[1], "业绩合同验收报告_竖版"),
        ((5, 0), PERF.get("横江", [""])[2], "业绩合同验收报告_竖版"),
        ((6, 0), PERF.get("横江", [""])[3], "业绩合同验收报告_竖版"),
        ((7, 0), PERF.get("南北", [""])[0], "业绩合同验收报告_竖版"),
        ((8, 0), PERF.get("南北", [""])[1], "业绩合同验收报告_竖版"),
        ((9, 0), PERF.get("南北", [""])[2], "业绩合同验收报告_竖版"),
        ((10, 0), PERF.get("南北", [""])[3], "业绩合同验收报告_竖版"),
        ((11, 0), PERF.get("南北", [""])[4], "业绩合同验收报告_竖版"),
        ((12, 0), PERF.get("南北", [""])[5], "业绩合同验收报告_竖版"),
        ((15, 0), p("陈云", "职称", 0), "总监高级工程师职称证书"),
        ((15, 1), p("陈云", "职称", 1), "总监高级工程师职称证书"),
        ((16, 0), p("陈友龙", "职称", 0), "小型职称证书"),
        ((16, 1), p("陈友龙", "职称", 1), "小型职称证书"),
        ((17, 0), p("吴志水", "职称", 0), "小型职称证书"),
        ((17, 1), p("吴志水", "职称", 1), "小型职称证书"),
        ((18, 0), p("裴友谊", "职称", 0), "小型职称证书"),
        ((18, 1), p("裴友谊", "职称", 1), "小型职称证书"),
        ((19, 0), honor("优秀监理企业_20230201") or honor("2021"), "先进优秀监理企业证书"),
        ((19, 1), honor("优秀监理企业_20240301") or honor("2022"), "先进优秀监理企业证书"),
        ((20, 0), honor("优秀监理企业_20250101") or honor("2023"), "先进优秀监理企业证书"),
        ((20, 1), honor("先进监理企业"), "先进优秀监理企业证书"),
        ((21, 0), honor("监理示范工程_20241201") or honor("2024"), "监理示范优质工程"),
        ((21, 1), honor("监理示范工程_20251201") or honor("2025"), "监理示范优质工程"),
        ((22, 0), honor("安全生产标准化示范工地"), "监理示范优质工程"),
        ((22, 1), honor("黄山杯"), "监理示范优质工程"),
    ]
    return biz, persons, CELL_MAP, YJ_MAP


# ==================== 深拷贝模板库 → 项目模板 ====================
def _find_master_dir(src, want="招标式"):
    """在代理机构目录下定位母版目录：优先『商务标母版-<want>』子目录；退化 src 本身。
    模板库结构与 _模板制作规范（商务标母版-<骨架>/）一致（2026-10-19 端到端试跑发现拷贝 0 件的根因）。"""
    files = TPL_FILES_PH if want == "采购式" else TPL_FILES
    if all((src / fn).is_file() for fn in files):
        return src
    for d in sorted(src.iterdir()):
        if d.is_dir() and "商务标母版" in d.name and want in d.name and (d / files[0]).is_file():
            return d
    return src


def copy_lib_to_proj(ent_dir, proj_dir, agent=None, want="招标式"):
    """深拷贝企业级模板库对应代理机构母版到项目模板/（先备份旧版到 dev 或回收站提示）。
    返回拷贝件数。"""
    ent = Path(ent_dir)
    proj = Path(proj_dir)
    lib_dir = ent / "企业级" / "模板库"
    # 代理机构：参数优先，否则从素材清单读
    if not agent:
        material = _load_material(proj)
        agent = material.get("招标代理机构", "") or ""
    agent = agent.strip()
    if not agent:
        raise FillError("无法确定代理机构（素材清单缺『招标代理机构』），请用 --agent 指定")
    src = _find_master_dir(lib_dir / agent, want=want)
    if not src.is_dir():
        raise FillError("模板库中不存在代理机构目录：%s" % src)
    tpl_dir = proj / "项目模板"
    tpl_dir.mkdir(parents=True, exist_ok=True)
    copied = 0
    files = TPL_FILES_PH if want == "采购式" else TPL_FILES
    for fn in files:
        s = src / fn
        if not s.is_file():
            continue
        shutil.copy2(str(s), str(tpl_dir / fn))
        copied += 1
    return copied, str(src)


# ==================== 主流程 ====================
def fill_from_tpl(ent, proj, out_dir=None, agent=None, register=True, skeleton="招标式"):
    if not HAVE_DOCX or Document is None:
        raise FillError("填充引擎依赖 python-docx，当前环境未安装")
    ent = Path(ent)
    proj = Path(proj)
    out = Path(out_dir) if out_dir else proj / "商务标"
    out.mkdir(parents=True, exist_ok=True)
    files = TPL_FILES_PH if skeleton == "采购式" else TPL_FILES

    # 1) 深拷贝模板库 → 项目模板
    copied, src_lib = copy_lib_to_tpl(ent, proj, agent, want=skeleton)

    # 2) 素材清单
    material = _load_material(proj)
    biz = material.get("企业基础信息", {}) or {}
    deadline = material.get("投标截止日期", "") or "2026-10-09"
    agent = material.get("招标代理机构", "") or agent or ""
    _, _, CELL_MAP, YJ_MAP = build_maps(material) if skeleton == "招标式" else (None, None, [], [])

    # 素材路径统一按项目目录解析
    def R(p):
        return _resolve(p, proj)

    CELL_MAP = [(idx, R(img), sk) for idx, img, sk in CELL_MAP]
    YJ_MAP = [(idx, R(img), sk) for idx, img, sk in YJ_MAP]
    # 保证金回单：项目资料固定件（素材清单未列，存在即填）
    rcd = str(proj / "项目资料" / "保证金回单.png")
    CELL_MAP = [(idx, (rcd if (idx == (5, 1, 0)) else img), sk)
                for idx, img, sk in CELL_MAP]

    V = {
        "project_name": material.get("project", ""),
        "project_code": material.get("招标编号", "") or biz.get("项目编号", ""),
        "bid_date": _fmt_date(deadline),
        "buyer_name": material.get("招标人", "") or biz.get("招标人", ""),
        "bid_bond_cn": material.get("投标保证金", "") or "",
        "company_name": biz.get("投标人名称", "") or "",
        "company_nature": biz.get("单位性质", "") or "",
        "company_address": biz.get("企业地址", "") or "",
        "company_zip": biz.get("邮编", "") or "",
        "company_phone": biz.get("联系电话", "") or "",
        "company_fax": biz.get("传真", "") or "",
        "bank_name": biz.get("开户银行", "") or "",
        "bank_account": biz.get("开户账号", "") or "",
        "company_founded": biz.get("成立时间", "") or "",
        "company_term": biz.get("经营期限", "") or "",
        "industry": biz.get("所属行业", "") or "",
        "日期": _fmt_date(deadline),
        "姓名": biz.get("法定代表人姓名", "") or "",
        "性别": biz.get("性别", "") or "",
        "年龄": str(biz.get("年龄", "") or ""),
        "职务": biz.get("职务", "") or "",
        "agent_name": biz.get("委托代理人姓名", "") or "",
        "agent_gender": biz.get("委托代理人性别", "") or "",
        "agent_age": str(biz.get("委托代理人年龄", "") or ""),
        "agent_title": biz.get("委托代理人职务", "") or "",
        "agent_job": biz.get("委托代理人职务", "") or "",
        "agent_id": biz.get("委托代理人身份证号", "") or "",
        "license_no": biz.get("统一社会信用代码", "") or "",
        "staff_count": biz.get("从业人员", "") or "",
        "tech_count": biz.get("技术人员", "") or "",
        "mgmt_count": biz.get("管理人员", "") or "",
        "revenue": biz.get("营业收入", "") or "",
        "assets": biz.get("资产总额", "") or "",
        "enterprise_scale": biz.get("企业规模", "") or "",
        "legal_phone": biz.get("法定代表人电话", "") or "",
        "agent_phone": biz.get("委托代理人手机号", "") or "",
        "项目说明": material.get("项目说明", "") or "",
    }
    if skeleton == "采购式":
        # 采购式专属键：开标一览表总监/报价；法代/授权已由 biz 覆盖
        st = material.get("personnel") or []
        V["supervisor_name"] = st[0].get("name", "") if st else ""
        V["supervisor_major"] = st[0].get("专业", "") if st else ""
        V["bid_price_num"] = material.get("投标报价", "") or ""

    stats = {"文件": [], "缺图": [], "待补": [], "清单外": [], "文字占位填充": 0}
    # 业绩项目名称按序消费：素材清单 performance 的 name 列表（模板 {{ 业绩项目名称 }} 依次取用）
    perf_names = [it.get("name", "") for it in material.get("performance", [])]
    tpl_dir = proj / "项目模板"
    for fn in files:
        src = tpl_dir / fn
        if not src.is_file():
            continue
        doc = Document(str(src))
        missing = []
        if skeleton == "采购式":
            # 资格证明：先行级表格填充（业绩/人员/简历行级消费），再文字占位（只处理正文残余），最后图占位关键词填充
            if fn == "资格证明及辅助资料表.docx":
                fill_cgys_qual_rows(doc, material)
            filled = fill_braces_doc(doc, V, perf_names)
            if fn == "法定代表人身份证明.docx":
                _fill_kw(doc, "法定代表人有效期内居民身份证", biz.get("法定代表人身份证") or [], "身份证_法代授权", missing)
            elif fn == "授权委托书.docx":
                _fill_kw(doc, "委托代理人有效期内居民身份证", biz.get("委托代理人身份证") or [], "身份证_法代授权", missing)
            elif fn == "资格证明及辅助资料表.docx":
                fill_cgys_images(doc, material, missing)
        else:
            # 文字占位
            filled = fill_braces_doc(doc, V, perf_names)
            # 图片占位：关键词定位（法代/授权/承诺书）
            if fn == "法定代表人身份证明.docx":
                _fill_kw(doc, "法定代表人有效期内居民身份证", biz.get("法定代表人身份证") or [], "身份证_法代授权", missing)
            elif fn == "授权委托书.docx":
                _fill_kw(doc, "委托代理人有效期内居民身份证", biz.get("委托代理人身份证") or [], "身份证_法代授权", missing)
            elif fn == "承诺书.docx":
                _fill_kw(doc, "账户开户许可证", [_q_first(material, "企业基本账户开户许可证")], "开户许可证扫描件", missing)
            elif fn == "投标单位业绩材料和奖项.docx":
                for (ri, ci), img, skey in YJ_MAP:
                    if img and not fill_img_table_cell(doc, ri, ci, 0, img, skey):
                        missing.append(("业绩T%s" % ri, skey))
                    elif not img:
                        missing.append(("业绩T%s" % ri, "素材清单未指定（披露）"))
                for ti in [15, 16, 17, 18, 19, 20, 21, 22]:
                    add_gap_between_two_img_rows(doc, ti)
            elif fn == "资格证明及辅助资料表.docx":
                # 附表7 姓名按行
                staff = [p0.get("name", "") for p0 in material.get("personnel", [])]
                for tbl in doc.tables:
                    hdr = [c.text.strip() for c in tbl.rows[0].cells]
                    if "项目职务" in hdr and any("姓" in h for h in hdr):
                        sc = next(i for i, h in enumerate(hdr) if "姓" in h)
                        for ri, row in enumerate(tbl.rows[1:]):
                            if ri < len(staff):
                                cell = row.cells[sc]
                                if cell.text.strip() not in staff:
                                    for r in list(cell.paragraphs[0].runs):
                                        r._r.getparent().remove(r._r)
                                    cell.paragraphs[0].add_run(staff[ri])
                        break
                for (ti, ri, ci), img, skey in CELL_MAP:
                    if img and not fill_img_table_cell(doc, ti, ri, ci, img, skey):
                        missing.append(("资格T%s_%s" % (ti, ri), skey))
                    elif not img:
                        missing.append(("资格T%s_%s" % (ti, ri), "素材清单未指定（披露）"))
                for ti in [25, 29, 33, 37, 52, 55, 56, 57, 58, 59, 60]:
                    add_gap_between_two_img_rows(doc, ti)
        doc.save(str(out / fn))
        stats["文件"].append({"文件": fn, "填充文字": filled, "缺图": [x[0] for x in missing]})
        stats["文字占位填充"] += filled
        stats["缺图"] += missing
        # 残留占位披露（模板空槽/未命中图占位不静默）
        residual = scan_residual_placeholders(doc)
        if residual:
            stats["待补"].append((fn, ["%s：%s" % (kind, key) for kind, key in residual]))

    stats["缺图"] = list(dict.fromkeys(stats["缺图"]))
    # 待补按文件分组（每文件至多一条，键为字符串元组可直接去重）
    seen_todo, todo = set(), []
    for fn, keys in stats["待补"]:
        k = (fn, tuple(keys))
        if k not in seen_todo:
            seen_todo.add(k)
            todo.append((fn, keys))
    stats["待补"] = todo
    _write_reports(out, stats, deadline)
    if register:
        core.write_json(str(out / "生成记录.json"), {
            "id": FILL_ID, "version": FILL_VERSION + "-tpl-v3", "日期": deadline,
            "项目": material.get("project", ""), "模板库": str(src_lib),
            "统计": {k: v for k, v in stats.items() if k != "文件"},
        })
    # 回读
    for f in stats["文件"]:
        core.readback.verify_docx_nonempty(out / f["文件"], label="商务标 docx")
    if register:
        core.readback.verify_json(out / "生成记录.json", required_fields=("项目",), label="生成记录")
    return stats


def _q_first(material, name):
    for it in material.get("qualification_required", []):
        if it.get("name") == name:
            return it.get("path") or ""
    return ""


def scan_residual_placeholders(doc):
    """填充后扫描残留占位：{{ }}（非图片占位文案）与【图片占位：】段，返回去重清单。
    用于待补披露（2026-10-19：模板空槽/未命中占位曾静默残留，补披露）。"""
    import re as _re
    from itertools import chain
    found, seen = [], set()

    def scan_para(para):
        t = para.text or ""
        if not t:
            return
        if "【图片占位：" in t:
            key = ("图", t.strip()[:40])
        elif "{{" in t:
            keys = _re.findall(r"\{\{\s*([^}]+?)\s*\}\}", t)
            key = ("文", "、".join(sorted(set(k.strip() for k in keys))))
        else:
            return
        if key not in seen:
            seen.add(key)
            found.append(key)

    body_paras = chain(doc.paragraphs, iter_textbox_paragraphs(doc))
    for para in body_paras:
        scan_para(para)
    for tbl in doc.tables:
        for row in tbl.rows:
            for cell in row.cells:
                for para in cell.paragraphs:
                    scan_para(para)
    return found


def _fill_kw(doc, kw, paths, spec_key, missing):
    """按关键词匹配图占位段（正文段落+表格+文本框段落），依序填；按所在单元格适配。"""
    ok = 0
    for para in doc.paragraphs:
        if kw in (para.text or "") and "【图片占位：" in (para.text or ""):
            if ok < len(paths):
                mw, mh = 16.0, 24.6
                if insert_img_fit_cell(para, paths[ok], spec_key, mw, mh):
                    ok += 1
    for tbl in doc.tables:
        for row in tbl.rows:
            for cell in row.cells:
                for para in cell.paragraphs:
                    if kw in (para.text or "") and "【图片占位：" in (para.text or ""):
                        if ok < len(paths):
                            mw, mh = cell_box_cm(cell)
                            if insert_img_fit_cell(para, paths[ok], spec_key, mw, mh):
                                ok += 1
    # 文本框内段落（母版图片占位段常见于此）：按页面级上限插图（fit_size 按规格缩放）
    for para in iter_textbox_paragraphs(doc):
        if kw in (para.text or "") and "【图片占位：" in (para.text or ""):
            if ok < len(paths):
                if insert_img_fit_cell(para, paths[ok], spec_key, 16.0, 24.6):
                    ok += 1
    for i in range(ok, len(paths)):
        missing.append(("%s 第%s张" % (kw, i + 1), "未匹配到图占位"))


def copy_lib_to_tpl(ent, proj, agent=None, want="招标式"):
    """兼容别名：copy_lib_to_proj。"""
    return copy_lib_to_proj(ent, proj, agent, want=want)


def _write_reports(out, stats, deadline):
    lines = ["# 缺图清单（商务标生成 %s）" % _fmt_date(deadline), "",
             "以下图片素材缺失或素材清单未指定（不兜底、不生成），补齐/登记后重新生成：", ""]
    for ph, note in stats["缺图"]:
        lines.append("- %s（%s）" % (ph, note))
    if not stats["缺图"]:
        lines.append("- 无")
    (out / "缺图清单.md").write_text("\n".join(lines), encoding="utf-8")
    (out / "待补字段清单.md").write_text(
        "# 待补字段清单（商务标生成 %s）\n\n以下占位未命中素材/未替换，补齐或确认后重新生成：\n" % _fmt_date(deadline)
        + "\n".join("- %s：%s" % (fn, "、".join(keys)) for fn, keys in stats["待补"]) or "- 无\n",
        encoding="utf-8")
    (out / "清单外素材.md").write_text(
        "# 清单外素材（商务标生成 %s）\n\n- 无（白名单：仅素材清单列明素材可入标）\n" % _fmt_date(deadline),
        encoding="utf-8")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="M5 商务标生成：企业模板库深拷贝 → 项目模板 → 填充")
    ap.add_argument("--ent", default=r"E:\监理标书制作\和县建设工程监理有限公司")
    ap.add_argument("--proj", default=r"E:\监理标书制作\和县建设工程监理有限公司\项目级\马鞍山和县化工园尾水水质提升工程（EPC总承包）监理")
    ap.add_argument("--agent", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--skeleton", default="招标式", choices=["招标式", "采购式"])
    args = ap.parse_args()
    s = fill_from_tpl(args.ent, args.proj, out_dir=args.out, agent=args.agent, skeleton=args.skeleton)
    print(json.dumps({k: v for k, v in s.items() if k != "文件"}, ensure_ascii=False, indent=1))
