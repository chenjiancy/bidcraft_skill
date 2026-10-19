# -*- coding: utf-8 -*-
"""大成·采购式骨架母版占位化脚本（6 件）。

在拆件产物上执行：
1) 文本占位：真实数据 → {{ 变量 }}（段级归一化匹配替换，保留段落格式）
2) 图片占位：含 drawing 的段 → 【图片占位：xxx】文案段（按前段上下文自动命名）
3) 写回 zip（document.xml 替换 + 裁剪未引用 media）

键名对齐招标式母版实际口径 + 引擎 V 表；引擎暂无键（业绩*/人员* 等）
按披露待补处理（fill-tpl 试跑披露），CELL_MAP 骨架适配下一步做。
"""
import re
import zipfile
from pathlib import Path
from lxml import etree

OUT = Path(r"E:\监理标书制作\和县建设工程监理有限公司\企业级\模板库\大成工程咨询有限公司\商务标母版-采购式")
FILES = ["封面.docx", "开标一览表.docx", "投标函.docx",
         "法定代表人身份证明.docx", "授权委托书.docx", "资格证明及辅助资料表.docx"]

NS_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
NS_WP = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
W_P = f"{{{NS_W}}}p"
W_R = f"{{{NS_W}}}r"
W_T = f"{{{NS_W}}}t"
W_PPR = f"{{{NS_W}}}pPr"
W_TBL = f"{{{NS_W}}}tbl"
W_TC = f"{{{NS_W}}}tc"

ALWAYS_KEEP = {
    "[Content_Types].xml", "_rels/.rels",
    "word/document.xml", "word/styles.xml", "word/settings.xml",
    "word/fontTable.xml", "word/webSettings.xml",
    "docProps/core.xml", "docProps/app.xml", "word/theme/theme1.xml",
}

# ---------- 文本替换表（值 → 键） ----------
# 全局（适用全部 6 件）
GLOBAL_REPS = [
    ("和县垃圾资源化利用综合建设项目-和县建筑垃圾资源化利用中心建设项目（一期）监理", "{{ project_name }}"),
    ("和县建设工程监理有限公司", "{{ company_name }}"),
    ("2026年 7月 13日", "{{ bid_date }}"),
    ("2026 年7月13日", "{{ bid_date }}"),
    ("2026年7月13日", "{{ bid_date }}"),
    ("安徽和州智创产业园发展有限公司", "{{ buyer_name }}"),
    ("邵章华", "{{ 姓名 }}"),
    ("孙婧", "{{ agent_name }}"),
    ("安徽省马鞍山市和县历阳镇润和国际5号楼201、202及S2-14号商铺", "{{ company_address }}"),
    ("有限责任公司（自然人投资或控股）", "{{ company_nature }}"),
    ("长期", "{{ company_term }}"),
    ("13956622973", "{{ legal_phone }}"),
    ("15956544949", "{{ agent_phone }}"),
    ("340204199110051526", "{{ agent_id }}"),
]

FILE_REPS = {
    "封面.docx": [],
    "开标一览表.docx": [
        ("DCZB-2026-026", "{{ project_code }}"),
        ("本项目的监理费用投标报价为456200.00元", "本项目的监理费用投标报价为{{ bid_price_num }}元"),
        ("姓名成建专业房屋建筑工程", "姓名{{ supervisor_name }}专业{{ supervisor_major }}"),
    ],
    "投标函.docx": [],
    "法定代表人身份证明.docx": [
        ("2006年11月17日", "{{ company_founded }}"),
        ("姓名邵章华性别男年龄54职务总经理", "姓名{{ 姓名 }}性别{{ 性别 }}年龄{{ 年龄 }}职务{{ 职务 }}"),
        # 段内冒号/空格分割时整句不匹配，独立值兜底（法代件内唯一）
        ("男", "{{ 性别 }}"),
        ("54", "{{ 年龄 }}"),
        ("总经理", "{{ 职务 }}"),
    ],
    "授权委托书.docx": [
        ("我邵章华系和县建设工程监理有限公司（供应商名称）的法定代表人", "我{{ 姓名 }}系{{ company_name }}（供应商名称）的法定代表人"),
        ("授权代理人：孙婧", "授权代理人：{{ agent_name }}"),
        ("性别：女", "性别：{{ agent_gender }}"),
        ("年龄：35", "年龄：{{ agent_age }}"),
        ("职务：职员", "职务：{{ agent_title }}"),
        ("居民身份证号码：340204199110051526", "居民身份证号码：{{ agent_id }}"),
    ],
    # 资格证明正文段（企业简介/条款/注释/图标题）固化不挖；表格内键见 TABLE_REPS
    "资格证明及辅助资料表.docx": [],
}

# 表格内段落专用替换（资格证明：按表格类型分组应用）
# company=企业信息表 / perf=业绩表（附表 2/3/4/5）/ staff=人员表（附表 6/7/8）
TABLE_REPS = {
    "资格证明及辅助资料表.docx": {
        "company": [
            ("和县建设工程监理有限公司", "{{ company_name }}"),
            ("邵章华", "{{ 姓名 }}"),
            ("2006.11.17", "{{ company_founded }}"),
            ("238200", "{{ company_zip }}"),
            ("0555-5314808", "{{ company_phone }}"),
            ("0555－5314808", "{{ company_fax }}"),
        ],
        "perf": [
            ("和县和州置业有限责任公司和县重点工程建设管理中心", "{{ 业绩业主单位 }}"),
            ("和县和州置业有限责任公司和县人力资源和社会保障局", "{{ 业绩业主单位 }}"),
            ("安徽宇邦新型材料有限公司", "{{ 业绩业主单位 }}"),
            ("安徽和州粮食有限公司", "{{ 业绩业主单位 }}"),
            ("和县和州置业有限责任公司", "{{ 业绩业主单位 }}"),
            ("和县重点工程建设管理中心", "{{ 业绩业主单位 }}"),
            ("和县人力资源和社会保障局", "{{ 业绩业主单位 }}"),
            ("安徽宇邦新型材料", "{{ 业绩业主单位 }}"),
            ("安徽和州粮食", "{{ 业绩业主单位 }}"),
            ("和县城市更新项目一期工程一和县第二中学迁建项目EPC总承包）监理", "{{ 业绩项目名称 }}"),
            ("和县职业技术学校西校区建设项目（EPC总承包）项目监理", "{{ 业绩项目名称 }}"),
            ("安徽宇邦新型材料有限公司年产光伏焊带20000吨生产项目", "{{ 业绩项目名称 }}"),
            ("安徽和州粮食有限公司粮食仓储物流能力建设提升项目一石杨粮库功能提升工程、腰埠粮库1.5万吨仓储设施建设工程、储备粮库1万吨仓储设施建设工程监理", "{{ 业绩项目名称 }}"),
            ("70000万元", "{{ 业绩合同金额 }}"),
            ("11850万元", "{{ 业绩合同金额 }}"),
            ("59400万元", "{{ 业绩合同金额 }}"),
            ("3898万元", "{{ 业绩合同金额 }}"),
            ("2023年12月27日至2025年6月30日", "{{ 业绩起止时间 }}"),
            ("2023年07月28日至2025年6月30日", "{{ 业绩起止时间 }}"),
            ("2023年9月10日至2025年8月18日", "{{ 业绩起止时间 }}"),
            ("2023年6月1日至2025年5月20日", "{{ 业绩起止时间 }}"),
            ("2023年12月27日", "{{ 业绩起止时间 }}"),
            ("2023年9月10日", "{{ 业绩起止时间 }}"),
            ("2023年6月1日", "{{ 业绩起止时间 }}"),
            ("600天", "{{ 业绩监理服务期 }}"),
            ("700天", "{{ 业绩监理服务期 }}"),
            # 业绩明细表“总监理工程师姓名”（整本唯一总监=成建）
            ("成建", "{{ 姓名 }}"),
            ("邵章华", "{{ 姓名 }}"),
        ],
        "staff": [
            ("成建", "{{ 人员姓名 }}"),
            ("严超", "{{ 人员姓名 }}"),
            ("尹仁富", "{{ 人员姓名 }}"),
            ("阮旭", "{{ 人员姓名 }}"),
            ("49", "{{ 人员年龄 }}"),
            ("35", "{{ 人员年龄 }}"),
            ("1962.6", "{{ 人员出生年月 }}"),
            ("1999.1", "{{ 人员出生年月 }}"),
            ("本科", "{{ 人员学历 }}"),
            ("大专", "{{ 人员学历 }}"),
            ("房屋建筑工程", "{{ 人员专业 }}"),
            ("自动化", "{{ 人员专业 }}"),
            ("工民建", "{{ 人员专业 }}"),
            ("建筑工程管理", "{{ 人员专业 }}"),
            ("工程师", "{{ 人员职称 }}"),
            ("高级工程师", "{{ 人员职称 }}"),
            ("技术员", "{{ 人员职称 }}"),
            ("总监理工程师", "{{ 人员职务 }}"),
            ("专监", "{{ 人员职务 }}"),
            ("监理员", "{{ 人员职务 }}"),
            ("总监", "{{ 人员职务 }}"),
            # 简历表工程经历（时间+项目名，人员级数据）
            ("2023.10-2024.12安徽宇邦项目", "{{ 人员经历时间 }}{{ 人员经历项目 }}"),
            ("2023.9-2024.12安徽宇邦新型材料有限公司年产光伏焊带20000吨生产项目", "{{ 人员经历时间 }}{{ 人员经历项目 }}"),
            # 简历表任职单位（本公司）
            ("和县建设工程监理有限公司", "{{ company_name }}"),
        ],
    },
}


def table_kind(tbl):
    """按表格全文特征分类：company / perf / staff / None（证书标题表等不替换）。"""
    text = "".join(t.text or "" for t in tbl.iter(W_T))
    if "出生年月" in text or "简历表" in text or "项目职务" in text or "备 注" in text:
        return "staff"
    if "业主单位" in text or "工程名称" in text or "合同金额" in text or "合同履行" in text:
        return "perf"
    if "企业名称" in text or "注册地址" in text:
        return "company"
    return None

# ---------- 图片占位文案生成（按前段文本分类） ----------
def img_placeholder(prev_text):
    t = prev_text or ""
    if "法定代表人有效期内居民身份证" in t:
        return "【图片占位：附：1、法定代表人有效期内居民身份证】"
    if "委托代理人有效期内居民身份证" in t:
        return "【图片占位：附：1、委托代理人有效期内居民身份证】"
    if "企业资质证书" in t:
        return "【图片占位：企业资质证书】"
    if "营业执照" in t:
        return "【图片占位：企业法人营业执照】"
    if "开户许可证" in t or "开户" in t:
        return "【图片占位：企业基本账户开户许可证】"
    if "总监理工程师注册执业证书" in t:
        return "【图片占位：总监理工程师注册执业证书】"
    if "三体系" in t:
        return "【图片占位：三体系认证证书】"
    if "一级造价" in t:
        return "【图片占位：总监一级造价师证书】"
    if "优秀总监" in t:
        return "【图片占位：拟派项目总监的优秀总监证书】"
    if "专业监理工程师中级职称" in t:
        return "【图片占位：专业监理工程师中级职称】"
    if "优秀监理企业" in t or "先进" in t:
        return "【图片占位：先进（优秀）监理企业证书】"
    if "社保" in t:
        return "【图片占位：社保证明】"
    if "简历表" in t or "身份证" in t or "职称" in t or "注册" in t or "岗位" in t or "备注" in t:
        return "【图片占位：人员证照（身份证/社保证明/职称证书/注册或岗位证书）】"
    if "业绩" in t or "合同" in t or "甲方证明" in t:
        return "【图片占位：业绩材料】"
    return "【图片占位：证明材料】"


def para_text(el):
    return "".join(t.text or "" for t in el.iter(W_T))


def has_drawing(el):
    return el.find(f".//{{{NS_A}}}blip") is not None or \
           el.find(f".//{{{NS_WP}}}inline") is not None or \
           el.find(f".//{{{NS_WP}}}anchor") is not None


def val_to_regex(val):
    """值 → 正则：值内每字符间允许任意空白（匹配『姓    名』等分散 run）。"""
    return r"\s*".join(re.escape(c) for c in val)


def replace_in_para(el, reps_norm):
    """段级正则替换：值（空白变体）→ 键，保留未匹配文本与空格。"""
    full = para_text(el)
    if not full:
        return False
    new = full
    for val, key in reps_norm:
        pat = val_to_regex(val)
        new2 = re.sub(pat, key, new, count=100)
        if new2 != new:
            new = new2
    if new == full:
        return False
    # 重建：保留 pPr，删除全部 run，写回文本
    ppr = el.find(W_PPR)
    for r in list(el):
        if r.tag != W_PPR:
            el.remove(r)
    r = etree.SubElement(el, W_R)
    t = etree.SubElement(r, W_T)
    t.text = new
    if ppr is not None:
        el.insert(0, ppr)
    return True


def img_to_placeholder(el, prev_text):
    """图片段 → 占位文案段（删 drawing/run，保留 pPr）。"""
    ph = img_placeholder(prev_text)
    ppr = el.find(W_PPR)
    for r in list(el):
        if r.tag != W_PPR:
            el.remove(r)
    r = etree.SubElement(el, W_R)
    t = etree.SubElement(r, W_T)
    t.text = ph
    if ppr is not None:
        el.insert(0, ppr)


def in_table_kind(el):
    """段落所在表格的类型（company/perf/staff/None）。"""
    parent = el.getparent()
    while parent is not None:
        if parent.tag == W_TBL:
            return table_kind(parent)
        parent = parent.getparent()
    return None


def replace_in_tc(tc, reps):
    """单元格级替换：tc 全文本拼接后替换，重写 tc 内第一个段的首 run，清空其余段文本。"""
    if tc.find(f".//{{{NS_A}}}blip") is not None or \
       tc.find(f".//{{{NS_WP}}}inline") is not None or \
       tc.find(f".//{{{NS_WP}}}anchor") is not None:
        return False
    full = "".join(t.text or "" for t in tc.iter(W_T))
    if not full:
        return False
    new = full
    for val, key in reps:
        new = re.sub(val_to_regex(val), key, new, count=100)
    if new == full:
        return False
    p = tc.find(W_P)
    if p is None:
        return False
    ppr = p.find(W_PPR)
    for r in list(p):
        if r.tag != W_PPR:
            p.remove(r)
    r = etree.SubElement(p, W_R)
    t = etree.SubElement(r, W_T)
    t.text = new
    if ppr is not None:
        p.insert(0, ppr)
    for p2 in list(tc):
        if p2.tag == W_P and p2 is not p:
            for r2 in list(p2):
                if r2.tag != W_PPR:
                    p2.remove(r2)
    return True


def process_doc(doc_xml, reps_norm, table_reps):
    root = etree.fromstring(doc_xml)
    body = root.find(f"{{{NS_W}}}body")
    # 第一遍：表格内按单元格级替换（tc 文本可跨段拼接，解决公司名/日期拆段）
    for tbl in body.iter(W_TBL):
        kind = table_kind(tbl)
        if kind and kind in table_reps:
            for tc in tbl.iter(W_TC):
                replace_in_tc(tc, table_reps[kind])
    # 第二遍：正文段级替换 + 图片占位（含文本框的 drawing 段为固定内容，不占位化）
    prev_text = ""
    for el in list(body.iter(W_P)):
        if el.tag == W_P:
            if has_drawing(el):
                if el.find(f".//{{{NS_W}}}txbxContent") is not None:
                    prev_text = para_text(el)
                else:
                    img_to_placeholder(el, prev_text)
                    prev_text = para_text(el)
            else:
                t = para_text(el)
                if t:
                    prev_text = t
                if in_table_kind(el) is None:
                    replace_in_para(el, reps_norm)
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def collect_r_ids(xml_bytes):
    root = etree.fromstring(xml_bytes)
    ids = set()
    for el in root.iter():
        for attr, val in el.attrib.items():
            if not val:
                continue
            local = attr.split("}")[-1] if attr.startswith("{") else attr
            if local in ("embed", "link", "id", "relid"):
                ids.add(val)
        if el.tag.endswith("Reference") or el.tag.endswith("hyperlink"):
            rid = el.get(f"{{{NS_R}}}id")
            if rid:
                ids.add(rid)
    return ids


NS_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def write_back(path, new_doc_xml):
    zin = zipfile.ZipFile(path, "r")
    names = zin.namelist()
    used_ids = collect_r_ids(new_doc_xml)
    rels_name = "word/_rels/document.xml.rels"
    rels_root = etree.fromstring(zin.read(rels_name))
    used_targets = set()
    for rel in list(rels_root):
        if rel.get("Id") in used_ids:
            used_targets.add(rel.get("Target"))
    for rel in list(rels_root):
        if rel.get("Id") not in used_ids:
            rels_root.remove(rel)
    new_rels = etree.tostring(rels_root, xml_declaration=True, encoding="UTF-8", standalone=True)
    keep = set(ALWAYS_KEEP)
    keep.add(rels_name)
    for t in used_targets:
        if t.startswith(("media/", "embeddings/", "charts/")):
            keep.add("word/" + t)
        elif t.startswith("/"):
            keep.add(t.lstrip("/"))
        else:
            keep.add("word/" + t)
    tmp = path.with_suffix(".ph.tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for n in names:
            if n == "word/document.xml":
                zout.writestr(n, new_doc_xml)
            elif n == rels_name:
                zout.writestr(n, new_rels)
            elif n in keep:
                zout.writestr(n, zin.read(n))
    zin.close()
    tmp.replace(path)


def main():
    for name in FILES:
        path = OUT / name
        # 长值（文件级）先替换，全局短值后替换，避免互相吞并
        reps = list(FILE_REPS[name]) + list(GLOBAL_REPS)
        # 长值先替换、短值后替换，避免短值破坏长值（如“工程师”先吞“总监理工程师”）
        reps_norm = sorted(((v, k) for v, k in reps), key=lambda vk: -len(vk[0]))
        table_reps = {kind: sorted(((v, k) for v, k in vals), key=lambda vk: -len(vk[0]))
                      for kind, vals in TABLE_REPS.get(name, {}).items()}
        zin = zipfile.ZipFile(path, "r")
        doc_xml = zin.read("word/document.xml")
        zin.close()
        new_doc_xml = process_doc(doc_xml, reps_norm, table_reps)
        write_back(path, new_doc_xml)
        print(f"{name} 占位化完成 ({path.stat().st_size / 1024 / 1024:.2f} MB)")
    print("占位化全部完成")


if __name__ == "__main__":
    main()
