# -*- coding: utf-8 -*-
"""恒信腾达·招标式骨架母版占位化脚本（8 件）。

源：%TEMP%\\hxtd_zbs\\（已完标书 .doc 经 LibreOffice 转换的 .docx）
目标：模板库 安徽恒信腾达项目管理咨询有限公司\\商务标母版-招标式\\
1) 文本占位：真实数据 → {{ 变量 }}（段级归一化匹配替换，保留段落格式）
2) 图片占位：含 drawing 的段 → 【图片占位：xxx】文案段（IMG 序号区间 + 前段上下文双保险）
3) 写回 zip（document.xml 替换 + 裁剪未引用 media）

基准：和县2026年老旧小区改造项目（EPC总承包）监理采购（招标式 8 件）
"""
import re
import shutil
import zipfile
from pathlib import Path
from lxml import etree

OUT = Path(r"E:\监理标书制作\和县建设工程监理有限公司\企业级\模板库\安徽恒信腾达项目管理咨询有限公司\商务标母版-招标式")
IN = Path(r"C:\Users\hxjlcj\AppData\Local\Temp\hxtd_zbs")
FILES = ["封面.docx", "开标一览表.docx", "投标函.docx", "投标函附录.docx",
         "法定代表人身份证明.docx", "授权委托书.docx", "承诺书.docx",
         "资格证明及辅助资料表.docx"]

NS_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
NS_WP = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
NS_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
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
GLOBAL_REPS = [
    ("和县2026年老旧小区改造项目（EPC总承包）监理", "{{ project_name }}"),
    ("和县建设工程监理有限公司", "{{ company_name }}"),
    ("和县住房和城乡建设局", "{{ buyer_name }}"),
    ("2026 年 8 月 10 日", "{{ bid_date }}"),
    ("2026年8月10日", "{{ bid_date }}"),
    ("邵章华", "{{ 姓名 }}"),
    ("孙婧", "{{ agent_name }}"),
    ("安徽省马鞍山市和县历阳镇润和国际5号楼201、202及S2-14号商铺", "{{ company_address }}"),
    ("有限责任公司（自然人投资或控股）", "{{ company_nature }}"),
    ("长期", "{{ company_term }}"),
    ("238200", "{{ company_zip }}"),
    ("0555-5328909", "{{ company_phone }}"),
    ("0555-5314808", "{{ company_fax }}"),
    ("13956622973", "{{ legal_phone }}"),
    ("15956544949", "{{ agent_phone }}"),
    ("340204199110051526", "{{ agent_id }}"),
]

FILE_REPS = {
    "封面.docx": [
        # 封面项目名跨两段：段1 长值（去 EPC 后缀）→ 键，段2 "（EPC总承包）监理" 清空
        ("和县2026年老旧小区改造项目", "{{ project_name }}"),
        ("（EPC总承包）监理", ""),
        ("HXTD-2026-018", "{{ project_code }}"),
    ],
    "开标一览表.docx": [
        ("HXTD-2026-018", "{{ project_code }}"),
        ("本项目的监理费用投标报价为156800.00元", "本项目的监理费用投标报价为{{ bid_price_num }}元"),
        ("姓名陈云专业房屋建筑工程", "姓名{{ supervisor_name }}专业{{ supervisor_major }}"),
    ],
    "投标函.docx": [
        ("中国建设银行股份有限公司和县支行", "{{ bank_name }}"),
        ("34001777408053002275", "{{ bank_account }}"),
    ],
    "投标函附录.docx": [],
    "法定代表人身份证明.docx": [
        ("2006   年    11   月   17   日", "{{ company_founded }}"),
        # 地址跨两段：段1 长值 → 键，段2 后缀清空（同封面项目名处理）
        ("安徽省马鞍山市和县历阳镇润和国际5号楼", "{{ company_address }}"),
        ("201、202及S2-14号商铺", ""),
        ("男", "{{ 性别 }}"),
        ("54", "{{ 年龄 }}"),
        ("总经理", "{{ 职务 }}"),
    ],
    "授权委托书.docx": [
        ("授权代理人：孙婧", "授权代理人：{{ agent_name }}"),
        ("性别：女", "性别：{{ agent_gender }}"),
        ("年龄：35", "年龄：{{ agent_age }}"),
        ("职务：职员", "职务：{{ agent_title }}"),
        ("居民身份证号码：340204199110051526", "居民身份证号码：{{ agent_id }}"),
    ],
    "承诺书.docx": [
        ("2026年6月23日", "{{ bid_date }}"),
    ],
    # 资格证明正文段固化不挖；表格内键见 TABLE_REPS
    "资格证明及辅助资料表.docx": [],
}

TABLE_REPS = {
    "资格证明及辅助资料表.docx": {
        "company": [
            ("和县建设工程监理有限公司", "{{ company_name }}"),
            ("邵章华", "{{ 姓名 }}"),
            ("2006.11.17", "{{ company_founded }}"),
            ("238200", "{{ company_zip }}"),
            ("0555-5328909", "{{ company_phone }}"),
            ("0555-5314808", "{{ company_fax }}"),
            ("房屋建筑工程监理甲级、市政公用工程监理乙级", "{{ company_qualification }}"),
            ("安徽省马鞍山市和县历阳镇润和国际5号楼201、202及S2-14号商铺", "{{ company_address }}"),
            ("913405237964034373", "{{ license_no }}"),
            ("（国内）17 年（国际）", "{{ 监理经历 }}"),
            ("总人数：62技术人员52管理人员10",
             "总人数：{{ staff_count }}技术人员{{ tech_count }}管理人员{{ mgmt_count }}"),
        ],
        "perf": [
            ("和县和州置业有限责任公司和县重点工程建设管理中心", "{{ 业绩业主单位 }}"),
            ("和县重点工程建设管理中心", "{{ 业绩业主单位 }}"),
            ("马鞍山融金置业有限公司", "{{ 业绩业主单位 }}"),
            ("和县海大生物科技有限公司", "{{ 业绩业主单位 }}"),
            ("和县和州置业有限责任公司", "{{ 业绩业主单位 }}"),
            ("和县城市更新项目一期工程—和县第二中学迁建项目（EPC总承包）监理", "{{ 业绩项目名称 }}"),
            ("和县城市更新项目一期工程一和县第二中学迁建项目EPC总承包）监理", "{{ 业绩项目名称 }}"),
            ("马鞍山汇金华府项目", "{{ 业绩项目名称 }}"),
            ("年产15万吨高档水产饲料斑目", "{{ 业绩项目名称 }}"),
            ("70000万元", "{{ 业绩合同金额 }}"),
            ("70000", "{{ 业绩合同金额 }}"),
            ("12600", "{{ 业绩合同金额 }}"),
            ("16000", "{{ 业绩合同金额 }}"),
            ("2023.12.30-2025.8.28", "{{ 业绩起止时间 }}"),
            ("2022.9.3-2024.6.5", "{{ 业绩起止时间 }}"),
            ("2023.4.21-2024.7.2", "{{ 业绩起止时间 }}"),
            ("2023年12月27日至2025年6月30日", "{{ 业绩起止时间 }}"),
            ("2023年12月27日", "{{ 业绩起止时间 }}"),
            ("2025年6月30日", "{{ 业绩起止时间 }}"),
            ("600天", "{{ 业绩监理服务期 }}"),
            ("8人", "{{ 业绩监理人员数量 }}"),
            ("邵章华", "{{ 姓名 }}"),
            ("阮敏", "{{ 业绩联系人 }}"),
            ("18855321299", "{{ 业绩联系电话 }}"),
        ],
        "staff": [
            ("陈云", "{{ 人员姓名 }}"),
            ("黄大海", "{{ 人员姓名 }}"),
            ("陈阳", "{{ 人员姓名 }}"),
            ("裴友谊", "{{ 人员姓名 }}"),
            ("阮旭", "{{ 人员姓名 }}"),
            ("2006年-至今在和县建设工程监理有限公司担任专监、总监职务", "{{ 人员经历 }}"),
            ("和县建设工程监理有限公司", "{{ company_name }}"),
        ],
        "staff_exact": [
            ("43", "{{ 人员年龄 }}"),
            ("60", "{{ 人员年龄 }}"),
            ("32", "{{ 人员年龄 }}"),
            ("50", "{{ 人员年龄 }}"),
            ("27", "{{ 人员年龄 }}"),
            ("1983.9", "{{ 人员出生年月 }}"),
            ("1966.11", "{{ 人员出生年月 }}"),
            ("专科", "{{ 人员学历 }}"),
            ("大专", "{{ 人员学历 }}"),
            ("房屋建筑工程", "{{ 人员专业 }}"),
            ("高级工程师", "{{ 人员职称 }}"),
            ("工程师", "{{ 人员职称 }}"),
            ("总监理工程师", "{{ 人员职务 }}"),
            ("专业监理工程师", "{{ 人员职务 }}"),
            ("监理员", "{{ 人员职务 }}"),
            ("总监", "{{ 人员职务 }}"),
            ("专监", "{{ 人员职务 }}"),
            ("342626198309180031", "{{ 人员身份证 }}"),
        ],
    },
}


def table_kind(tbl):
    """按表格全文特征分类：company / perf / staff / None。"""
    text = "".join(t.text or "" for t in tbl.iter(W_T))
    if "出生年月" in text or "简历表" in text or "项目职务" in text or "备 注" in text:
        return "staff"
    if "业主单位" in text or "工程名称" in text or "合同金额" in text or "合同履行" in text:
        return "perf"
    if "企业名称" in text or "注册地址" in text:
        return "company"
    return None


# ---------- 图片占位：IMG 序号区间规则（资格证明基准 135 图段；1 起） ----------
# (start, end, 文案 or None=保留整段)
IMG_RANGES = [
    (1, 5, None),          # 表8标题段/组织机构框图(文本框)/企业简介区域 → 保留
    (6, 8, "【图片占位：企业资质证书】"),
    (9, 10, "【图片占位：企业法人营业执照（副本）】"),
    (11, 11, "【图片占位：总监理工程师注册执业证书】"),
    (12, 13, "【图片占位：企业基本账户开户许可证】"),
    (14, 65, "【图片占位：业绩材料】"),
    (66, 103, "【图片占位：人员证照（身份证/社保证明/职称证书/注册或岗位证书）】"),
    (104, 110, "【图片占位：三体系认证证书】"),
    (111, 112, "【图片占位：拟派总监高级工程师职称证书】"),
    (113, 118, "【图片占位：其他监理人员中级职称证书】"),
    (119, 125, "【图片占位：先进（优秀）监理企业证书】"),
    (126, 130, "【图片占位：监理示范（优质）工程】"),
    (131, 133, "【图片占位：拟派总监优秀总监证书】"),
    (134, 135, None),      # 承诺函文本段/签章区 → 保留
]


def img_ph_by_index(idx):
    """命中区间返回 (文案 or None=保留, True)；未命中返回 (None, False)。"""
    for start, end, text in IMG_RANGES:
        if start <= idx <= end:
            return text, True
    return None, False


def img_placeholder(prev_text):
    """邻近文本兜底规则（IMG 序号区间未覆盖时）。"""
    t = prev_text or ""
    if "法定代表人有效期内居民身份证" in t:
        return "【图片占位：附：1、法定代表人有效期内居民身份证】"
    if "委托代理人有效期内居民身份证" in t:
        return "【图片占位：附：1、委托代理人有效期内居民身份证】"
    if "企业法人营业执照" in t:
        return "【图片占位：企业法人营业执照（副本）】"
    if "企业资质证书" in t:
        return "【图片占位：企业资质证书】"
    if "营业执照" in t:
        return "【图片占位：企业法人营业执照】"
    if "开户许可证" in t or "开户" in t:
        return "【图片占位：企业基本账户开户许可证】"
    if "总监理工程师注册执业证书" in t:
        return "【图片占位：总监理工程师注册执业证书】"
    if "质量管理体系" in t or "环境管理体系" in t or "职业健康" in t or "三体系" in t:
        return "【图片占位：三体系认证证书】"
    if "拟派总监" in t and ("高级工程师" in t or "职称" in t):
        return "【图片占位：拟派总监高级工程师职称证书】"
    if "中级职称" in t:
        return "【图片占位：其他监理人员中级职称证书】"
    if "先进" in t or "优秀监理企业" in t:
        return "【图片占位：先进（优秀）监理企业证书】"
    if "监理示范" in t or "优质" in t:
        return "【图片占位：监理示范（优质）工程】"
    if "优秀总监" in t:
        return "【图片占位：拟派总监优秀总监证书】"
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
    return r"\s*".join(re.escape(c) for c in val)


def replace_in_para(el, reps_norm):
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


def img_to_placeholder(el, ph):
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
    parent = el.getparent()
    while parent is not None:
        if parent.tag == W_TBL:
            return table_kind(parent)
        parent = parent.getparent()
    return None


def replace_in_tc(tc, reps, exact_reps=None):
    if has_drawing(tc):
        return False
    full = "".join(t.text or "" for t in tc.iter(W_T))
    if not full:
        return False
    new = full
    # 先整单元格精确匹配（防证书号/身份证/证书名内短数字误伤）
    if exact_reps:
        stripped = re.sub(r"\s+", "", full)
        for val, key in exact_reps:
            if stripped == re.sub(r"\s+", "", val):
                new = key
                break
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


def process_doc(doc_xml, reps_norm, table_reps, use_img_ranges, file_img_ph=None):
    root = etree.fromstring(doc_xml)
    body = root.find(f"{{{NS_W}}}body")
    # 第一遍：表格内单元格级替换
    for tbl in body.iter(W_TBL):
        kind = table_kind(tbl)
        if kind and kind in table_reps:
            exact = table_reps.get(kind + "_exact")
            for tc in tbl.iter(W_TC):
                replace_in_tc(tc, table_reps[kind], exact)
    # 第二遍：正文段级替换 + 图片占位（IMG 序号区间仅资格证明件启用）
    prev_text = ""
    img_idx = 0
    for el in body.iter(W_P):
        if el.tag != W_P:
            continue
        if has_drawing(el):
            img_idx += 1
            if el.find(f".//{{{NS_W}}}txbxContent") is not None:
                prev_text = para_text(el)
            else:
                if file_img_ph is not None:
                    ph = file_img_ph
                elif use_img_ranges:
                    ph, hit = img_ph_by_index(img_idx)
                    if not hit:
                        ph = img_placeholder(prev_text)
                else:
                    ph = img_placeholder(prev_text)
                img_to_placeholder(el, ph)
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
    OUT.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        src = IN / name
        dst = OUT / name
        if not src.exists():
            print(f"[缺源] {name}")
            continue
        shutil.copy2(src, dst)
        reps = list(FILE_REPS[name]) + list(GLOBAL_REPS)
        reps_norm = sorted(((v, k) for v, k in reps), key=lambda vk: -len(vk[0]))
        table_reps = {}
        for kind, vals in TABLE_REPS.get(name, {}).items():
            if kind.endswith("_exact"):
                table_reps[kind] = vals
            else:
                table_reps[kind] = sorted(((v, k) for v, k in vals), key=lambda vk: -len(vk[0]))
        zin = zipfile.ZipFile(dst, "r")
        doc_xml = zin.read("word/document.xml")
        zin.close()
        file_img_ph = {
            "法定代表人身份证明.docx": "【图片占位：法定代表人有效期内居民身份证】",
            "授权委托书.docx": "【图片占位：委托代理人有效期内居民身份证】",
            "承诺书.docx": "【图片占位：账户开户许可证】",
        }.get(name)
        new_doc_xml = process_doc(doc_xml, reps_norm, table_reps,
                                  name == "资格证明及辅助资料表.docx", file_img_ph)
        write_back(dst, new_doc_xml)
        print(f"{name} 占位化完成 ({dst.stat().st_size / 1024 / 1024:.2f} MB)")
    print("恒信腾达·招标式 8 件占位化全部完成")


if __name__ == "__main__":
    main()
