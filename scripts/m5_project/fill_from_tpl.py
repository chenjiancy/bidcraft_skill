# -*- coding: utf-8 -*-
"""
M5（v2.0 布局样板范式）商务标生成引擎：企业母版（布局样板）深拷贝 → 项目模板 → 类别聚合填充。

用户 2026-10-19 定案（取代 V5 / CELL_MAP 坐标+人名硬编码）：
  1) 深拷贝 企业级模板库/<代理机构>/商务标母版-<骨架>/ → 项目模板/
  2) 模板=版面样板：固定条款照抄、可变文字 {{ 键名 }}、图片【图片占位：类别】、人员/业绩只做样板行/页
  3) 素材清单=数据：personnel/performance/qualification_required/honors/iso_certificates/
     social_security_required 决定放哪些人/证书/多少/顺序；**素材清单未列出的素材商务标不生成**
  4) fill 四步引擎：①占位索引扫描 → ②样板复制（按素材数量深拷贝 XML，保留格式/合并单元格）
     → ③类别聚合填充（图片按类别依序消费；简历组内按人员对象取数、组间不串）
     → ④未列不生成 + 缺图披露
  5) 总监识别=职务字段含「总监」/「总监理工程师」，personnel[0] 仅兜底；
     专业监理工程师/监理员为数据（{{ 人员职务 }} 直填），不参与图片类别识别；
     某人无某类证书 → 该类自动少一张。

模块契约：脚本平台无关（不依赖豆包私有能力）；素材一旦归档受保护，本模块只读。
"""
import json
import re
import shutil
from copy import deepcopy
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
    from docx.table import Table
except Exception:  # pragma: no cover
    Document = Paragraph = Table = None

from .image_spec import fit_size     # noqa: E402
from . import key_alias              # noqa: E402   v2.4：键名规范表/白名单
from .key_alias import ROW_KEYS      # noqa: E402   行级键（与键名规范表同源）

# 模板库 9 件（企业级母版，文件顺序即生成顺序）
TPL_FILES = ["封面.docx", "投标函.docx", "投标函附录.docx", "授权委托书.docx",
             "法定代表人身份证明.docx", "承诺书.docx", "其他.docx",
             "投标单位业绩材料和奖项.docx", "资格证明及辅助资料表.docx"]

# 采购式 6 件（大成·采购式骨架，2026-10-19 定案：以已完标书为准拆分，无附录/承诺书/其他/业绩奖项件）
TPL_FILES_PH = ["封面.docx", "开标一览表.docx", "投标函.docx",
                "法定代表人身份证明.docx", "授权委托书.docx",
                "资格证明及辅助资料表.docx"]

# 行级键（样板行/页复制后按素材对象填值，不做全局替换）——已并入 key_alias 统一管理
# （PERSON_ROW_KEYS ∪ PERF_ROW_KEYS；与键名规范表同源）
# 简历表专属键（含之表格视为简历样板表）
RESUME_ONLY_KEYS = {"人员出生年月", "人员经历时间", "人员经历项目"}
# 业绩明细表专属键（含之表格视为业绩明细样板页）
PERF_DETAIL_KEYS = {"业绩监理服务期", "业绩监理人员数量", "业绩联系人", "业绩联系电话"}

# 简历组内图片类别 → 人员对象字段（组内按人员取数，不参与全局依序消费）
STAFF_IMG_KINDS = {
    "总监注册监理工程师证书": ["注册证书"],
    "高级工程师职称证书": ["职称证书", "职称"],
    "职称证书": ["职称证书", "职称"],
    "岗位证书": ["岗位证书"],
    "身份证": ["身份证"],
}


def _load_material(proj_dir):
    """读素材清单：优先 素材清单.json，回退 素材清单_<项目>.json。"""
    p = Path(proj_dir) / "招标解析"
    for name in ("素材清单.json",):
        f = p / name
        if f.is_file():
            return core.read_json(str(f), None) or {}
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


# ==================== 文本框 / 单元格 基础工具 ====================
def iter_textbox_paragraphs(doc):
    """遍历文档中所有文本框（w:txbxContent）内的段落（python-docx doc.paragraphs 不可见）。"""
    body = doc.element.body
    for txbx in body.iter(qn("w:txbxContent")):
        for p_el in txbx.iter(qn("w:p")):
            yield Paragraph(p_el, doc)


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
    p = re.sub(r"企业级[\\/]+项目级", "项目级", p)
    p = Path(p)
    if p.is_absolute() and p.is_file():
        return str(p)
    cand = proj / p
    return str(cand) if cand.is_file() else str(p)


def insert_img_fit_cell(para, img_path, spec_key, mw, mh):
    """按 max_w/max_h 等比适配插图（水平居中）；插入成功返回 True。

    返回三态：True=成功；False=文件不可读/路径缺失；None=image_spec 未约定该类别尺寸
    （须披露，不得静默插入/静默不插）。"""
    if not img_path or not Path(img_path).is_file():
        return False
    size = fit_size(img_path, spec_key, max_w=mw, max_h=mh)
    if not size:
        return None
    w, h = size
    for r in list(para.runs):
        r._r.getparent().remove(r._r)
    para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    para.add_run().add_picture(str(img_path), width=Cm(w), height=Cm(h))
    return True


def _insert_img_at_para(doc, para, img_path, spec_key):
    """段落级插图：段落位于表格单元格 → 按单元格适配；否则按页面级上限（文本框内段落常见）。"""
    tc = para._p.getparent() if para._p.getparent() is not None else None
    cell_found = False
    while tc is not None and tc.tag != qn("w:tc"):
        tc = tc.getparent()
    if tc is not None and tc.tag == qn("w:tc"):
        try:
            cell = None
            for tbl in doc.tables:
                for row in tbl.rows:
                    for c in row.cells:
                        if c._tc is tc:
                            cell = c
                            break
        except Exception:
            cell = None
        if cell is not None:
            mw, mh = cell_box_cm(cell)
            return insert_img_fit_cell(para, img_path, spec_key, mw, mh)
    return insert_img_fit_cell(para, img_path, spec_key, 16.0, 24.6)


def _repl_para_keys(para, mapping):
    """单段 {{ }} 键替换（保留格式：只改首个 w:t，清空其余 w:t）。"""
    t = para.text or ""
    nt = t
    for k, v in mapping.items():
        nt = nt.replace("{{ " + k + " }}", v).replace("{{" + k + "}}", v)
    if nt != t:
        for r in list(para.runs[1:]):
            r._r.getparent().remove(r._r)
        if para.runs:
            para.runs[0].text = nt


def _repl_tr_text(tr, mapping):
    """表格行级 {{ }} 替换（物理 w:tr 内所有段落；只替换 mapping 中键）。"""
    for p_el in tr.iter(qn("w:p")):
        t = "".join(node.text or "" for node in p_el.iter(qn("w:t")))
        nt = t
        for k, v in mapping.items():
            nt = nt.replace("{{ " + k + " }}", v).replace("{{" + k + "}}", v)
        if nt != t:
            texts = list(p_el.iter(qn("w:t")))
            if texts:
                texts[0].text = nt
                for node in texts[1:]:
                    node.text = ""


# ==================== ① 占位索引扫描 ====================
_BRACE_RE = re.compile(r"\{\{\s*([^}]+?)\s*\}\}")
_IMGPH_RE = re.compile(r"【图片占位：([^】]+)】")


def _para_braces(para):
    return set(k.strip() for k in _BRACE_RE.findall(para.text or ""))


def _para_imgph(para):
    return [c.strip() for c in _IMGPH_RE.findall(para.text or "")]


def scan_placeholder_index(doc):
    """扫描母版占位，返回 dict：
    - generic_keys: {键: count}           通用键（非行级键）
    - row_paras:    {键: [paragraph]}     含行级键的段落（简历锚点等，不做全局替换）
    - img_ph:       [(类别, paragraph)]   全局图片占位序列（出现顺序；不含简历/业绩组内框）
    - row_tables:   {键: [(table, row_idx)]} 行级样板行（人员配备/业绩汇总）
    - detail_tables: [(table, kind)]      整表样板：resume=简历表 / perf=业绩明细表
    """
    idx = {"generic_keys": {}, "row_paras": {}, "img_ph": [], "row_tables": {}, "detail_tables": []}
    excluded = set()  # 组内 body 元素（存元素对象；id() 会因 GC 复用产生假阳性）

    # 先判整表样板（简历/业绩明细），收集其组内段落
    for tbl in doc.tables:
        full = "".join(c.text for c in (c2 for r in tbl.rows for c2 in r.cells))
        if any(k in full for k in RESUME_ONLY_KEYS):
            idx["detail_tables"].append((tbl, "resume"))
            for el in _detail_group_elements(doc, tbl):
                excluded.add(el)
            continue
        if any(k in full for k in PERF_DETAIL_KEYS):
            idx["detail_tables"].append((tbl, "perf"))
            for el in _detail_group_elements(doc, tbl):
                excluded.add(el)
            continue
        for ri, row in enumerate(tbl.rows):
            rowkeys = set()
            for cell in row.cells:
                for para in cell.paragraphs:
                    rowkeys |= collect_para(idx, para)
            if "人员姓名" in rowkeys:
                idx["row_tables"].setdefault("人员配备", []).append((tbl, ri))
            if "业绩业主单位" in rowkeys or "业绩项目名称" in rowkeys:
                idx["row_tables"].setdefault("业绩汇总", []).append((tbl, ri))

    def in_group(para):
        node = para._p
        while node is not None:
            if node in excluded:
                return True
            node = node.getparent()
        return False

    for para in doc.paragraphs:
        collect_para(idx, para, in_group=in_group(para))
    for para in iter_textbox_paragraphs(doc):
        collect_para(idx, para, in_group=in_group(para))
    return idx


def collect_para(idx, para, in_group=False):
    """单段收集：{{ }} 键分类 + 【图片占位：类别】序列。组内段图框不入全局。"""
    keys = _para_braces(para)
    row_keys = keys & ROW_KEYS
    if keys:
        for k in keys:
            if k in ROW_KEYS:
                idx["row_paras"].setdefault(k, []).append(para)
            else:
                idx["generic_keys"][k] = idx["generic_keys"].get(k, 0) + 1
    if not in_group:
        for c in _para_imgph(para):
            idx["img_ph"].append((c, para))
    return keys


def _detail_group_elements(doc, tbl):
    """整表样板组：body 级元素列表 = [可选前锚点段（含 {{ 人员姓名 }}）] + 表 + 表后组员段。"""
    elems = []
    prev = tbl._tbl.getprevious()
    if prev is not None and prev.tag == qn("w:p"):
        pp = Paragraph(prev, doc)
        if "人员姓名" in _para_braces(pp):
            elems.append(prev)
    elems.append(tbl._tbl)
    elems += [m._tbl if isinstance(m, Table) else m._p for m in _iter_group_elements(doc, tbl._tbl)]
    return elems


# ==================== ② 样板复制 ====================
def _fit_row_template(doc, tbl, row_idx, n, fill_fn):
    """行样板数量适配：样板行保留，其后同结构行删除；按 n 复制补齐；逐行 fill_fn(i) 填值。
    复制源=原始占位行（deepcopy 于填充前），避免复制已填充行。返回 True=已处理（含 n=0 删除样板行）。"""
    rows = list(tbl.rows)
    total = len(rows)
    for ri in range(total - 1, row_idx, -1):
        tr = rows[ri]._tr
        tr.getparent().remove(tr)
    tmpl_tr = tbl.rows[row_idx]._tr
    if n <= 0:
        tmpl_tr.getparent().remove(tmpl_tr)
        return True
    src_tr = deepcopy(tmpl_tr)      # 原始占位行（未填）
    fill_fn(0, tmpl_tr)             # 样板行填第 1 条
    for i in range(1, n):
        new_tr = deepcopy(src_tr)
        tmpl_tr.addnext(new_tr)
        fill_fn(i, new_tr)
        tmpl_tr = new_tr
    return True


def _fit_table_group(doc, anchor, members, n, fill_fn):
    """整表/整组样板复制：anchor=锚点元素（段落/表格），members=其后组员元素（body 级）。
    n=复制份数；fill_fn(i, el) 对第 i 份逐元素填值。复制源=原始占位副本（填充前深拷贝）。
    n=0 → 删除整组。"""
    if n <= 0:
        for el in [anchor] + list(members):
            el.getparent().remove(el)
        return
    anchor_src = deepcopy(anchor)
    members_src = [deepcopy(m) for m in members]
    fill_fn(0, anchor)
    for el in members:
        fill_fn(0, el)
    # 副本整体追加到原始组之后（last 从组尾开始），保持 组1…组N 顺序
    last = members[-1] if members else anchor
    for i in range(1, n):
        for el in [anchor_src] + members_src:
            new_el = deepcopy(el)
            last.addnext(new_el)
            last = new_el
            fill_fn(i, new_el)


def _iter_group_elements(doc, anchor):
    """返回锚点后的 body 级兄弟元素（段落/表格），直到『组终止点』并停：
    ① 下一个人员锚点（含 {{ 人员姓名 }}）；② 分页符段（w:br type=page / pageBreakBefore）——
    v2.0 约定：简历表后到下一分页符前的图框段归该人。只收图框段（正文/文本框/表格内图框占位）。"""
    members = []
    body = doc.element.body
    node = anchor.getnext()
    while node is not None:
        if node.tag == qn("w:p"):
            para = Paragraph(node, doc)
            if "人员姓名" in _para_braces(para):
                break
            if _has_page_break(para):
                break
            if _para_imgph(para) or _has_textbox_imgph(para):
                members.append(para)
        elif node.tag == qn("w:tbl"):
            full = "".join(c.text for row in Table(node, doc).rows for c in row.cells)
            if "【图片占位：" in full:
                members.append(Table(node, doc))
        node = node.getnext()
    return members


def _has_page_break(para):
    """段首分页（w:br type=page 或 pageBreakBefore）判定——组边界。"""
    if para.paragraph_format.page_break_before:
        return True
    for br in para._p.iter(qn("w:br")):
        if br.get(qn("w:type")) == "page":
            return True
    return False


def _has_textbox_imgph(para):
    """段落内嵌文本框（w:txbxContent）是否含图片占位文案。"""
    for txbx in para._p.iter(qn("w:txbxContent")):
        for p_el in txbx.iter(qn("w:p")):
            if _para_imgph(Paragraph(p_el, para.part)):
                return True
    return False


def _find_person_anchor(doc):
    """人员锚点段：含 {{ 人员姓名 }} 的段落（正文/文本框）；返回首段。"""
    for para in doc.paragraphs:
        if "人员姓名" in _para_braces(para):
            return para
    return None


# ==================== ③ 类别聚合 ====================
def _flat_paths(items):
    out = []
    for it in items or []:
        if isinstance(it, dict):
            if it.get("path"):
                out.append(str(it["path"]))
            for p in it.get("paths") or []:
                if p:
                    out.append(str(p))
    return out


def _find_director(staff):
    """总监识别：职务字段含「总监」/「总监理工程师」→ 总监；personnel[0] 仅兜底。"""
    for p in staff:
        z = str(p.get("职务") or "")
        if "总监" in z or "总监理工程师" in z:
            return p
    return staff[0] if staff else None


def _staff_paths(person, cat):
    for k in STAFF_IMG_KINDS.get(cat, []):
        v = person.get(k) or []
        if v:
            return [str(x) for x in v if x]
    return []


def _q_paths(material, kw):
    """qualification_required 按名称关键词匹配（支持多个关键词，任一命中）。"""
    out = []
    for it in material.get("qualification_required") or []:
        nm = str(it.get("name") or "")
        if kw and any(k in nm for k in (kw if isinstance(kw, (list, tuple)) else [kw])):
            p = it.get("path") or ""
            if p:
                out.append(str(p))
    return out


def aggregate_category(material, cat):
    """按类别聚合素材路径（v2.0 规范 3.3）。类别素材数=0 表示未列 → 不生成。"""
    staff = material.get("personnel") or []
    director = _find_director(staff)
    non_dir = [p for p in staff if p is not director]
    if cat == "总监注册监理工程师证书":
        return _staff_paths(director, cat) if director else []
    if cat == "高级工程师职称证书":
        return _staff_paths(director, cat) if director else []
    if cat == "职称证书":
        out = []
        for p in non_dir:
            out += _staff_paths(p, cat)
        return out
    if cat == "岗位证书":
        out = []
        for p in non_dir:
            out += _staff_paths(p, "岗位证书")
        return out
    if cat == "身份证":
        out = []
        for p in staff:
            out += _staff_paths(p, "身份证")
        return out
    if cat == "社保证明":
        out = []
        for it in material.get("social_security_required") or []:
            for p in it.get("paths") or []:
                if p:
                    out.append(str(p))
        return out
    if cat == "业绩材料":
        out = []
        for it in material.get("performance") or []:
            for p in it.get("paths") or []:
                if p:
                    out.append(str(p))
        return out
    if cat == "企业资质证书":
        return _q_paths(material, "资质")
    if cat == "企业法人营业执照":
        return _q_paths(material, "营业执照")
    if cat == "开户许可证":
        return _q_paths(material, "开户许可")
    if cat == "三体系认证证书":
        return _flat_paths(material.get("iso_certificates"))
    if cat == "先进监理企业证书":
        return _honor_paths(material, ("先进监理企业", "优秀监理企业", "优秀企业"))
    if cat == "监理示范工程":
        return _honor_paths(material, ("监理示范", "示范工程", "安全生产标准化", "黄山杯"))
    if cat == "优秀总监证书":
        return _honor_paths(material, "优秀总监")
    if cat == "法定代表人身份证":
        return _flat_paths(material.get("企业基础信息", {}).get("法定代表人身份证"))
    if cat == "委托代理人身份证":
        return _flat_paths(material.get("企业基础信息", {}).get("委托代理人身份证"))
    return []


def _honor_paths(material, kws):
    out = []
    for it in material.get("honors") or []:
        nm = str(it.get("name") or "")
        if isinstance(kws, (list, tuple)):
            hit = any(k in nm for k in kws)
        else:
            hit = kws in nm
        if hit:
            p = it.get("path") or ""
            if p:
                out.append(str(p))
    return out


def _person_map(person):
    return {
        "人员姓名": person.get("name") or "",
        "人员年龄": person.get("年龄") or "",
        "人员出生年月": person.get("出生年月") or "",
        "人员学历": person.get("学历") or "",
        "人员专业": person.get("专业") or "",
        "人员职称": person.get("职称") or "",
        "人员职务": person.get("职务") or "",
        "人员身份证": person.get("身份证号") or person.get("身份证") or "",
    }


def _perf_map(perf):
    return {
        "业绩业主单位": perf.get("业主单位") or "",
        "业绩项目名称": perf.get("name") or "",
        "业绩合同金额": perf.get("合同金额") or "",
        "业绩起止时间": perf.get("起止时间") or "",
        "业绩监理服务期": perf.get("监理服务期") or "",
        "业绩监理人员数量": perf.get("监理人员数量") or "",
        "业绩联系人": perf.get("联系人") or "",
        "业绩联系电话": perf.get("联系电话") or "",
    }


# ==================== 填充引擎 ====================
def fill_generic_text(doc, vmap):
    """通用键直填：跳过含行级键的段落（由样板引擎处理）；含【图片占位：】的段落不做文本替换。"""
    used = 0
    for para in doc.paragraphs:
        full = para.text or ""
        if "{{" in full and "【图片占位：" not in full and not (_para_braces(para) & ROW_KEYS):
            nt = _repl_braces(full, vmap)
            if nt != full:
                _set_para_text(para, nt)
                used += 1
    for tbl in doc.tables:
        for row in tbl.rows:
            for cell in row.cells:
                for para in cell.paragraphs:
                    full = para.text or ""
                    if "{{" in full and "【图片占位：" not in full and not (_para_braces(para) & ROW_KEYS):
                        nt = _repl_braces(full, vmap)
                        if nt != full:
                            _set_para_text(para, nt)
                            used += 1
    for para in iter_textbox_paragraphs(doc):
        full = para.text or ""
        if "{{" in full and "【图片占位：" not in full and not (_para_braces(para) & ROW_KEYS):
            nt = _repl_braces(full, vmap)
            if nt != full:
                _set_para_text(para, nt)
                used += 1
    return used


def _repl_braces(text, vmap):
    def rep(m):
        k = m.group(1).strip()
        return vmap.get(k, m.group(0))
    return _BRACE_RE.sub(rep, text)


def _set_para_text(para, nt):
    for r in list(para.runs[1:]):
        r._r.getparent().remove(r._r)
    if para.runs:
        para.runs[0].text = nt


def fill_row_templates(doc, idx, material, proj):
    """行样板复制+填：人员配备（按 personnel）、业绩汇总（按 performance）。"""
    staff = material.get("personnel") or []
    perf = material.get("performance") or []
    handled = {"人员配备": False, "业绩汇总": False}

    for key, rows in idx.get("row_tables", {}).items():
        if not rows:
            continue
        tbl, row_idx = rows[0]
        if key == "人员配备":
            fill_fn = lambda i, tr: _repl_tr_text(tr, _person_map(staff[i])) if i < len(staff) else None
            if _fit_row_template(doc, tbl, row_idx, len(staff), fill_fn):
                handled["人员配备"] = True
        elif key == "业绩汇总":
            fill_fn = lambda i, tr: _repl_tr_text(tr, _perf_map(perf[i])) if i < len(perf) else None
            if _fit_row_template(doc, tbl, row_idx, len(perf), fill_fn):
                handled["业绩汇总"] = True
    return handled


def fill_detail_tables(doc, idx, material, proj, missing):
    """整表样板复制+填：简历表（按 personnel 复制，组内文字/图框按人员对象取数）、
    业绩明细表（按 performance 复制，含其后图框段组）。未列（人数/条数为 0）→ 整组删除+披露。"""
    staff = material.get("personnel") or []
    perf = material.get("performance") or []

    def fill_para_group(el, person, cat_paths):
        """组内段落：段落文本键 + 段内文本框图框，全部按 person 取数。"""
        para = Paragraph(el, doc)
        for cat in _para_imgph(para):
            _consume_para_images(doc, para, cat, cat_paths(cat), missing)
        for txbx in para._p.iter(qn("w:txbxContent")):
            for p_el in txbx.iter(qn("w:p")):
                sub = Paragraph(p_el, doc)
                for cat in _para_imgph(sub):
                    _consume_para_images(doc, sub, cat, cat_paths(cat), missing)

    for tbl, kind in idx.get("detail_tables", []):
        elems = _detail_group_elements(doc, tbl)
        if kind == "resume":
            n = len(staff)

            def fn(i, el):
                if el.tag == qn("w:tbl"):
                    t = Table(el, doc)
                    person = staff[i]
                    for tr in t.rows:
                        _repl_tr_text(tr._tr, _person_map(person))
                    exp = person.get("经历") or []
                    cnt_t = cnt_p = 0
                    for tr in t.rows:
                        for p_el in list(tr._tr.iter(qn("w:p"))):
                            txt = "".join(node.text or "" for node in p_el.iter(qn("w:t")))
                            if "人员经历时间" in txt and cnt_t < len(exp):
                                _repl_tr_text(tr._tr, {"人员经历时间": exp[cnt_t].get("时间") or ""})
                                cnt_t += 1
                            if "人员经历项目" in txt and cnt_p < len(exp):
                                _repl_tr_text(tr._tr, {"人员经历项目": exp[cnt_p].get("项目") or ""})
                                cnt_p += 1
                else:
                    if "人员姓名" in _para_braces(Paragraph(el, doc)):
                        _repl_tr_text(el, {"人员姓名": staff[i].get("name") or ""})
                    fill_para_group(el, staff[i], lambda cat: _staff_paths(staff[i], cat))

            _fit_table_group(doc, elems[0], elems[1:], n, fn)
        elif kind == "perf":
            n = len(perf)

            def fn(i, el):
                if el.tag == qn("w:tbl"):
                    t = Table(el, doc)
                    for tr in t.rows:
                        _repl_tr_text(tr._tr, _perf_map(perf[i]))
                else:
                    if "业绩项目名称" in _para_braces(Paragraph(el, doc)):
                        _repl_tr_text(el, {"业绩项目名称": perf[i].get("name") or ""})
                    fill_para_group(el, perf[i], lambda cat: [str(p) for p in (perf[i].get("paths") or []) if p])

            _fit_table_group(doc, elems[0], elems[1:], n, fn)


def _ai_img_paths(proj, section):
    """AI 配图通道（m_img 产物路径解析）。

    **商务标红线（v2.5）**：fill-tpl 为商务标引擎，已禁用 AI 配图，本函数当前不被
    fill_images_by_category 消费；保留供未来非商务标引擎（技术标等）复用。
    """
    """AI 配图通道：读 配图/配图清单_<项目>.json，按 section 匹配 saved 项 → 落盘路径列表。

    与素材通道（aggregate_category）并列：模板中『【图片占位：AI配图-<section>】』
    消费 m_img 管道产物（配图/目录），未 saved / 未匹配 → 不生成（删框+披露）。
    """
    proj = Path(proj)
    cands = sorted((proj / "配图").glob("配图清单_*.json"))
    if not cands:
        return []
    data = core.read_json(str(cands[0]), None) or {}
    items = data.get("items") or []
    return [R(str(it.get("file")), proj) for it in items
            if (it.get("status") == "saved" and it.get("section") == section
                and it.get("file"))]


def fill_images_by_category(doc, idx, material, proj, missing):
    """全局图框类别聚合填充：同类别按占位出现顺序依序消费；素材数=0 → 未列不生成（删框+披露）。

    商务标红线（v2.5）：**商务标一律禁用 AI 配图**——模板中『【图片占位：AI配图-<section>】』
    不做 AI 生成、不消费配图清单；商务标配图必须全部来自素材清单，素材清单未提供 → 删框+披露。
    （m_img 配图管道仅服务于技术标等非商务标场景，fill-tpl 不消费。）
    """
    by_cat = {}
    for cat, para in idx.get("img_ph", []):
        by_cat.setdefault(cat, []).append(para)
    for cat, paras in by_cat.items():
        if cat.startswith("AI配图-"):
            for i, para in enumerate(paras):
                missing.append((cat, "第%d张 商务标禁 AI 配图（素材清单无则不生成）" % (i + 1)))
                _drop_ph_para(para)
            continue
        paths = [R(p, proj) for p in aggregate_category(material, cat)]
        for i, para in enumerate(paras):
            if i < len(paths):
                r = _insert_img_at_para(doc, para, paths[i], _spec_key(cat))
                if r is None:
                    missing.append((cat, "第%d张 image_spec 未约定该类尺寸（已删框）" % (i + 1)))
                    _drop_ph_para(para)
                elif not r:
                    missing.append((cat, "第%d张 插图失败（文件不可读/路径缺失）" % (i + 1)))
            else:
                missing.append((cat, "第%d张 素材不足/素材清单未列（已删框）" % (i + 1)))
                _drop_ph_para(para)
        for i in range(len(paras), len(paths)):
            missing.append((cat, "第%d张 模板无对应图框（素材未用）" % (i + 1)))


def _spec_key(cat):
    # 尺寸规格键：与 image_spec 对齐
    if cat.startswith("AI配图-"):
        return "AI配图"
    return {
        "企业法人营业执照": "营业执照扫描件",
        "开户许可证": "开户许可证扫描件",
        "三体系认证证书": "三体系认证证书",
        "企业资质证书": "资质证书",
        "社保证明": "社保证明",
        "身份证": "身份证",
        "职称证书": "职称证",
        "岗位证书": "岗位证书",
        "总监注册监理工程师证书": "注册监理工程师证书",
        "高级工程师职称证书": "总监高级工程师职称证书",
        "业绩材料": "业绩合同验收报告_竖版",
        "先进监理企业证书": "先进优秀监理企业证书",
        "监理示范工程": "监理示范优质工程",
        "优秀总监证书": "优秀总监证书",
        "法定代表人身份证": "身份证_法代授权",
        "委托代理人身份证": "身份证_法代授权",
    }.get(cat, "通用图片")


def _consume_para_images(doc, para, cat, paths, missing):
    """组内图框：单段多框逐个消费。"""
    if not paths:
        missing.append((cat, "素材清单未列/该人员无此证书（已删框）"))
        _drop_ph_para(para)
        return
    r = _insert_img_at_para(doc, para, paths[0], _spec_key(cat))
    if r is None:
        missing.append((cat, "image_spec 未约定该类尺寸（已删框）"))
        _drop_ph_para(para)
    elif not r:
        missing.append((cat, "插图失败（文件不可读/路径缺失）"))
        _drop_ph_para(para)
    else:
        _drop_ph_text(para)


def _drop_ph_para(para):
    """删除图片占位段落（未列不生成：图框段落整体移除）。"""
    p_el = para._p
    p_el.getparent().remove(p_el)


def _drop_ph_text(para):
    """清除占位文案：仅删除不含 drawing 的 run（保留已插入图片的 run）。"""
    for r in list(para.runs):
        if len(list(r._r.iter(qn("w:drawing")))) == 0:
            r._r.getparent().remove(r._r)


def R(p, proj):
    return _resolve(p, proj)


# ==================== 深拷贝模板库 → 项目模板 ====================
def _find_master_dir(src, want="招标式"):
    """在代理机构目录下定位母版目录：优先『商务标母版-<want>』子目录；退化 src 本身。

    v2.4 分批制作：母版目录按批次逐步补齐，定位门槛为「目录内至少存在 1 件
    TPL 文件」而非要求首件（封面）必须存在，避免分批期间模板库无法被 fill 定位。
    """
    files = TPL_FILES_PH if want == "采购式" else TPL_FILES
    if any((src / fn).is_file() for fn in files):
        return src
    for d in sorted(src.iterdir()):
        if d.is_dir() and "商务标母版" in d.name and want in d.name and any((d / fn).is_file() for fn in files):
            return d
    return src


def copy_lib_to_proj(ent_dir, proj_dir, agent=None, want="招标式"):
    """深拷贝企业级模板库对应代理机构母版到项目模板/。返回拷贝件数。"""
    ent = Path(ent_dir)
    proj = Path(proj_dir)
    lib_dir = ent / "企业级" / "模板库"
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


def copy_lib_to_tpl(ent, proj, agent=None, want="招标式"):
    """兼容别名：copy_lib_to_proj。"""
    return copy_lib_to_proj(ent, proj, agent, want=want)


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

    # 2) 素材清单 + 通用键字典
    material = _load_material(proj)
    biz = material.get("企业基础信息", {}) or {}
    deadline = material.get("投标截止日期", "") or "2026-10-09"
    agent = material.get("招标代理机构", "") or agent or ""

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
        st = material.get("personnel") or []
        V["supervisor_name"] = st[0].get("name", "") if st else ""
        V["supervisor_major"] = st[0].get("专业", "") if st else ""
        V["bid_price_num"] = material.get("投标报价", "") or ""

    # v2.4：键名规范表补中文别名条目（模板写机器键或中文别名均解析）
    for _mk, _spec in key_alias.KEY_SPEC.items():
        _al = _spec.get("别名")
        if _al and _mk in V:
            V.setdefault(_al, V[_mk])

    stats = {"文件": [], "缺图": [], "待补": [], "清单外": [], "未知键": [], "文字占位填充": 0}
    tpl_dir = proj / "项目模板"
    for fn in files:
        src = tpl_dir / fn
        if not src.is_file():
            continue
        doc = Document(str(src))
        missing = []
        # ① 占位索引
        idx = scan_placeholder_index(doc)
        # 通用键直填
        filled = fill_generic_text(doc, V)
        # ② 样板复制：行样板（人员配备/业绩汇总）
        fill_row_templates(doc, idx, material, proj)
        # ② 整表样板：简历表/业绩明细表（含其后组内图框段）
        fill_detail_tables(doc, idx, material, proj, missing)
        # ③ 全局图框类别聚合
        fill_images_by_category(doc, idx, material, proj, missing)
        doc.save(str(out / fn))
        stats["文件"].append({"文件": fn, "填充文字": filled, "缺图": [x[0] for x in missing]})
        stats["文字占位填充"] += filled
        stats["缺图"] += missing
        residual = scan_residual_placeholders(doc)
        if residual:
            stats["待补"].append((fn, ["%s：%s" % (kind, key) for kind, key in residual]))
        # v2.4 键名白名单校验：未知键披露（不静默）
        unk = scan_unknown_keys(doc, key_alias.registered_keys())
        if unk:
            stats["未知键"].append((fn, unk))

    stats["缺图"] = list(dict.fromkeys(stats["缺图"]))
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
            "id": FILL_ID, "version": FILL_VERSION + "-tpl-v2", "日期": deadline,
            "项目": material.get("project", ""), "模板库": str(src_lib),
            "统计": {k: v for k, v in stats.items() if k != "文件"},
        })
    for f in stats["文件"]:
        core.readback.verify_docx_nonempty(out / f["文件"], label="商务标 docx")
    if register:
        core.readback.verify_json(out / "生成记录.json", required_fields=("项目",), label="生成记录")
    return stats


def scan_residual_placeholders(doc):
    """填充后扫描残留占位：{{ }}（非图片占位文案）与【图片占位：】段，返回去重清单。"""
    found, seen = [], set()

    def scan_para(para):
        t = para.text or ""
        if not t:
            return
        if "【图片占位：" in t:
            key = ("图", t.strip()[:40])
        elif "{{" in t:
            keys = _BRACE_RE.findall(t)
            key = ("文", "、".join(sorted(set(k.strip() for k in keys))))
        else:
            return
        if key not in seen:
            seen.add(key)
            found.append(key)

    from itertools import chain
    for para in chain(doc.paragraphs, iter_textbox_paragraphs(doc)):
        scan_para(para)
    for tbl in doc.tables:
        for row in tbl.rows:
            for cell in row.cells:
                for para in cell.paragraphs:
                    scan_para(para)
    return found


def scan_unknown_keys(doc, valid_keys):
    """v2.4 键名白名单校验：扫描全文所有 {{ }} 键，返回不在合法键集（机器键∪别名∪行级键）的未知键。

    用于防模板键拼写错误/未登记键静默残留——未知键一律披露（不静默）。"""
    seen = set()

    def scan_para(para):
        t = para.text or ""
        if "{{" in t:
            for k in _BRACE_RE.findall(t):
                seen.add(k.strip())

    from itertools import chain
    for para in chain(doc.paragraphs, iter_textbox_paragraphs(doc)):
        scan_para(para)
    for tbl in doc.tables:
        for row in tbl.rows:
            for cell in row.cells:
                for para in cell.paragraphs:
                    scan_para(para)
    return sorted(k for k in seen if k not in valid_keys)


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
    ap = argparse.ArgumentParser(description="M5 商务标生成（v2.0 布局样板范式）：企业母版 → 项目模板 → 类别聚合填充")
    ap.add_argument("--ent", default=r"E:\监理标书制作\和县建设工程监理有限公司")
    ap.add_argument("--proj", default=r"E:\监理标书制作\和县建设工程监理有限公司\项目级\马鞍山和县化工园尾水水质提升工程（EPC总承包）监理")
    ap.add_argument("--agent", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--skeleton", default="招标式", choices=["招标式", "采购式"])
    args = ap.parse_args()
    s = fill_from_tpl(args.ent, args.proj, out_dir=args.out, agent=args.agent, skeleton=args.skeleton)
    print(json.dumps({k: v for k, v in s.items() if k != "文件"}, ensure_ascii=False, indent=1))
