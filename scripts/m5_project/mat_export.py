# -*- coding: utf-8 -*-
"""⑦ generator · 素材清单组装导出（M5 前置④，2026-10-10）。

把用户填写完成的 v5.1 素材清单表（xlsm，G 列用户指定素材 + H 列查询结果）
组装为生成器结构素材清单 JSON（含原 M4 需求清单 items，一份文件两用），
落盘 招标解析/素材清单_<项目>.json，供 proj-gen --material 直接引用。

生成器结构（fill_*/gen_tables 依赖）：
  project / 招标代理机构 / 采购方式 / 投标截止日期 / 投标报价 /
  企业基础信息{法定代表人姓名, 委托代理人姓名, 委托代理人手机} /
  监理人员配置口径{项目总监, 专业监理工程师, 监理员} /
  personnel[{name, role, 注册证书[], 职称[], 岗位证书[], 简历[], 毕业证[]}] /
  qualification_required / iso_certificates / honors / performance /
  social_security_required（各含 name + path，path=素材库绝对路径）

映射规则（R 编号 → 生成器字段，agent 可增行维护）：
  R01 营业执照 → qualification_required      R02 企业资质 → qualification_required
  R03 体系认证 → iso_certificates            R08 社保 → social_security_required
  R10/R11 业绩 → performance                 R13/R14 荣誉 → honors
  R04 总监注册 / R05 总监职称 / R06 专监证书 / R07 监理员证书 /
  R09 简历 / R15 其他职称 / R16 毕业证 → personnel 各字段
  R19 委托代理人 → 企业基础信息
"""
import json
import re
from pathlib import Path

from .gen_common import GenError
from _shared import core

__all__ = ["export_material", "PERSON_DEFAULT_ROLE"]

# 本项目人员默认角色（由 R04/R06/R07 人员配备口径推导，agent 维护）
PERSON_DEFAULT_ROLE = {
    "陈云": "项目总监",
    "黄大海": "专业监理工程师",
    "陈阳": "专业监理工程师",
    "裴友谊": "监理员",
    "阮旭": "监理员",
}

# R 编号 → (生成器 section, 名称) ；personnel 类单独处理
SECTION_RULES = [
    ("R01", "qualification_required", "营业执照"),
    ("R02", "qualification_required", "企业资质（房屋建筑工程监理甲级）"),
    ("R03", "iso_certificates", "体系认证"),
    ("R10", "performance", "企业业绩"),
    ("R11", "performance", "总监业绩"),
    ("R13", "honors", "监理示范工程"),
    ("R14", "honors", "总监荣誉"),
]


def _row_values(ws, r):
    """读取一行，合并单元格取左上值（openpyxl 语义）。"""
    out = {}
    for c in range(1, ws.max_column + 1):
        v = ws.cell(row=r, column=c).value
        if v is not None:
            out[c] = str(v).strip()
    return out


def _find_g_values(ws, r_start, r_end):
    """G 列（用户指定素材区）在行范围内的全部值。"""
    vals = []
    for r in range(r_start, r_end + 1):
        v = ws.cell(row=r, column=7).value
        if v is not None and str(v).strip():
            vals.append(str(v).strip())
    return vals


def _resolve_asset(value, lib_root, ledger):
    """素材值 → 素材库绝对路径。

    规则（2026-10-10 v2）：
      0) 剥离「姓名：」前缀（人员素材 G 值格式），按核心文件名匹配
      1) 台账 rel_path 文件名/目录段匹配（排除 _备份）
      2) 含分隔符（业绩「目录\\子文件」）：lib_root/<值> 或 素材库分类前缀下逐试；
         值是目录名时按台账目录段定位（返回该目录首文件）
      3) glob 兜底（排除 _备份）
    解析失败返回 ""（不阻断，调用方按需降级）。
    """
    value = value.replace("\\", "/").strip("/")
    if not value:
        return ""
    # 剥离「姓名：」前缀 → (姓名, 核心文件名)；无前缀时 name=None
    name, core_name = None, value
    m = re.match(r"^([^：:/]+)[：:]\s*(.+)$", value)
    if m:
        name, core_name = m.group(1).strip(), m.group(2).strip()
    # 1) 台账匹配：优先「人员/<姓名>/」下同文件名，再放宽到同文件名
    if ledger:
        hits = []
        for it in ledger:
            rp = str(it.get("rel_path", "")).replace("\\", "/")
            if "_备份" in rp:
                continue
            if not rp.endswith("/" + core_name):
                continue
            if name and ("人员/" + name + "/") in rp:
                hits.insert(0, it)     # 姓名精确命中排最前
            else:
                hits.append(it)
        if hits:
            p = lib_root / str(hits[0]["rel_path"]).replace("\\", "/")
            return str(p) if p.is_file() else str(p)
        for it in ledger:              # 放宽：核心文件名出现在 rel_path 中
            rp = str(it.get("rel_path", "")).replace("\\", "/")
            if "_备份" in rp or core_name not in rp:
                continue
            if name and ("人员/" + name + "/") in rp:
                p = lib_root / rp
                return str(p) if p.is_file() else str(p)
    # 2) 含分隔符：直接路径 / 分类前缀路径 / 目录段定位
    if "/" in value:
        for base in [lib_root] + [lib_root / c for c in
                                  ("业绩", "荣誉", "资质", "人员", "财务", "企业介绍")]:
            p = base / value
            if p.is_file():
                return str(p)
        d = value.split("/")[0]
        if ledger:
            dhits = [it for it in ledger
                     if "/" + d + "/" in str(it.get("rel_path", "")).replace("\\", "/")
                     and "_备份" not in str(it.get("rel_path", ""))]
            if dhits:
                p = lib_root / str(dhits[0]["rel_path"]).replace("\\", "/")
                return str(p)
    # 3) glob 兜底（排除 _备份）
    cands = [p for p in lib_root.rglob(core_name) if "_备份" not in str(p)]
    if cands:
        return str(cands[0])
    return ""


def _person_name_from_g(gv):
    """G 值形如「姓名：素材名」→ 取姓名；否则 None。"""
    m = re.match(r"^([^：:]+)[：:]\s*(.+)$", gv)
    return m.group(1).strip() if m else None


def export_material(ent, project, xlsm_path=None, ledger=None, social_path=""):
    """组装生成器结构素材清单（保留 M4 items）。返回 dict。"""
    proj_dir = Path(ent) / "项目级" / project
    if not proj_dir.is_dir():
        raise GenError("项目目录不存在：项目级/%s" % project)
    if not xlsm_path:
        cands = [p for p in proj_dir.glob("招标解析/素材清单_空白表_v5*.xlsm") if p.is_file()]
        if not cands:
            raise GenError("未找到 v5 素材清单空白表（招标解析/素材清单_空白表_v5*.xlsm）")
        xlsm_path = max(cands, key=lambda p: p.stat().st_mtime)   # 按修改时间取最新（v5.1 晚于 v5）
    xlsm = Path(xlsm_path)
    if not xlsm.is_file():
        raise GenError("素材清单表不存在：%s" % xlsm)

    import openpyxl
    wb = openpyxl.load_workbook(xlsm, keep_vba=False, data_only=False)
    if "素材清单" not in wb.sheetnames:
        raise GenError("表内无「素材清单」sheet：%s" % xlsm)
    ws = wb["素材清单"]

    lib_root = Path(ent) / "企业级" / "素材库"
    ledger_items = ledger or core.read_json(Path(ent) / "企业级" / "素材库" / "素材台账.json", [])

    # 1) 行区间：A 列需求编号 → 行范围（合并单元格：A 列仅左上角有值）
    row_spans = []                       # [(R编号, 起行, 止行)]
    rows = []
    for r in range(3, ws.max_row + 1):
        rid = ws.cell(row=r, column=1).value
        rows.append((r, rid))
    cur = None
    for r, rid in rows:
        if rid and str(rid).startswith("R"):
            if cur:
                cur[2] = r - 1
            cur = [str(rid), r, r]
            row_spans.append(cur)
        elif cur:
            cur[2] = r
    if cur:
        cur[2] = ws.max_row

    # 2) sections 组装
    sections = {k: [] for k in ("qualification_required", "iso_certificates",
                                "honors", "performance", "social_security_required")}
    for rid, r0, r1 in row_spans:
        gvals = _find_g_values(ws, r0, r1)
        for s_rule in SECTION_RULES:
            if rid != s_rule[0]:
                continue
            sec, name = s_rule[1], s_rule[2]
            for gv in gvals:
                path = _resolve_asset(gv, lib_root, ledger_items)
                if not path and rid == "R08":
                    continue            # 社保在项目资料，单独处理
                # R02 企业资质：名称按文件名等级区分（甲级/乙级）
                if rid == "R02":
                    lv = "甲级" if "甲级" in gv else ("乙级" if "乙级" in gv else "资质")
                    name = "企业资质（房屋建筑工程监理%s）" % lv
                sections[sec].append({"name": name, "path": path or ""})
    # R08 社保：项目资料（用户上传）
    if social_path:
        sections["social_security_required"].append(
            {"name": "社保单位参保证明", "path": social_path})

    # 3) personnel 组装：姓名从 R04/R06/R07/R09/R15/R16 行 G 列「姓名：素材」前缀动态收集
    P_KEY = {"R04": "注册证书", "R05": "职称", "R06": "注册证书", "R07": "岗位证书",
             "R09": "简历", "R15": "职称", "R16": "毕业证"}
    persons = {}
    for rid, r0, r1 in row_spans:
        if rid not in P_KEY:
            continue
        for gv in _find_g_values(ws, r0, r1):
            pname = _person_name_from_g(gv)
            if pname and pname not in persons:
                persons[pname] = {"name": pname,
                                   "role": PERSON_DEFAULT_ROLE.get(pname, "")}
    if not persons:
        # 旧表无姓名前缀时回退默认人员（agent 维护）
        persons = {name: {"name": name, "role": role}
                   for name, role in PERSON_DEFAULT_ROLE.items()}
    for rid, r0, r1 in row_spans:
        key = P_KEY.get(rid)
        if not key:
            continue
        for gv in _find_g_values(ws, r0, r1):
            pname = _person_name_from_g(gv)
            if pname and pname in persons:
                path = _resolve_asset(gv, lib_root, ledger_items)
                persons[pname].setdefault(key, []).append(path or gv)
            elif not pname:
                # 无姓名前缀（如 R16 毕业证 G36=陈阳：毕业证_工程造价.png 有前缀；兜底）
                if rid == "R16" and "陈阳" in gv:
                    path = _resolve_asset(gv, lib_root, ledger_items)
                    persons["陈阳"].setdefault(key, []).append(path or gv)

    # 4) 企业基础信息 + 配置口径
    biz = {"法定代表人姓名": "邵章华"}        # 台账营业执照 note 可核，agent 维护
    for rid, r0, r1 in row_spans:
        if rid != "R19":
            continue
        for r in range(r0, r1 + 1):
            row = _row_values(ws, r)
            g = row.get(7, "")
            h = row.get(8, "")
            if "姓名" in g and h:
                biz["委托代理人姓名"] = h
            elif "手机" in g and h:
                biz["委托代理人手机"] = h
            elif "邮箱" in g and h:
                biz["委托代理人邮箱"] = h

    # 5) 项目元数据（招标解析 basic 模块可核，agent 维护）
    meta = {
        "project": project,
        "招标代理机构": "安徽恒信腾达项目管理咨询有限公司",
        "采购方式": "投标",
        "投标截止日期": "2026-08-10 14:00",
        "投标报价": "388600.00",
        "投标资格专业": "房屋建筑工程",
        "监理人员配置口径": {"项目总监": 1, "专业监理工程师": 2, "监理员": 2},
    }

    # 6) 保留 M4 需求清单（items），一份文件两用
    m4 = core.read_json(proj_dir / "招标解析" / ("素材清单_%s.json" % project), None)
    items = m4.get("items", []) if isinstance(m4, dict) else []

    out = {
        **meta,
        "企业基础信息": biz,
        "personnel": list(persons.values()),
        **sections,
        "items": items,
        "素材清单来源": str(xlsm),
    }
    return out


def write_material(ent, project, material, out_path=None):
    """落盘 招标解析/素材清单_<项目>.json（生成器结构 + M4 items）。"""
    proj_dir = Path(ent) / "项目级" / project
    p = Path(out_path) if out_path else \
        proj_dir / "招标解析" / ("素材清单_%s.json" % project)
    core.write_json(p, material)
    return p
