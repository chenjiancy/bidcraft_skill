# -*- coding: utf-8 -*-
"""⑧ 图片占位规则表 —— 占位生成与填充的**唯一数据源**（L1 重构核心）。

背景（2026-10-17 L1）：
  旧实现有三套并存导致断链：
    1) gen_common.IMAGE_PH_AFTER_TABLE/PARA（静态占位文案，硬编码数量）；
    2) gen_main._dynamic_image_phs（按素材清单动态生成「业绩N-xxx」「姓名-xxx」，但
       与填充解析不一致）；
    3) fill_images.FILL_IMG_MAP + fill_combo._build_combo（硬编码分支解析，
       未覆盖动态占位文案 → 填充时走「未实现组合规则」缺图）。
  本模块收敛为**单一权威**：占位文案、素材路径、尺寸键、位置锚点全部由素材清单
  （material dict）推导；gen 生成什么占位，fill 就解析什么占位（同一函数）。

素材清单结构（proj-mat 导出的 <项目>_素材清单.json）：
  personnel[]: {name, role, 注册证书|岗位证书|职称|简历|毕业证: [abs_path,...]}
  qualification_required[]: {name, path}
  iso_certificates[]: {name, path}
  honors[]: {name, path}            # name ∈ 监理示范工程/先进监理企业/总监荣誉/...
  performance[]: {name, path}       # name ∈ 企业业绩/总监业绩; path 可为文件或目录
  social_security_required[]: {name, path}
  企业基础信息: {法定代表人姓名, 委托代理人姓名}

设计规则（用户 2026-10-17 确认）：
  - 图片素材**以素材清单列明为准**：清单没有的图一律不生成占位（如本项目无
    「先进（优秀）监理企业证书」→ 不生成占位，不再 glob 猜测）；
  - 位置锚点由招标注文/附表驱动（注文只定位置、不定数量）；
  - 总监荣誉在「附表10」与「业绩奖项独立文件」两处都放（用户确认）。
"""
import os
import re

# 图片占位段识别：以「【图片：」开头、以「】」结尾
PH_PREFIX = "【图片："
PH_SUFFIX = "】"

# 占位文案 → 素材清单来源的解析键（人名字段）
_PERSON_KINDS = ("注册证书", "岗位证书", "职称", "简历", "毕业证")


def _norm(p):
    """路径统一正斜杠、去首尾分隔符（用于文件名单词匹配）。"""
    return str(p).replace("\\", "/").strip().strip("/")


def _ph(name, tag=""):
    """生成占位文案：【图片：{tag}{name}】（tag 用于类型前缀/同名序号）。"""
    return "%s%s%s%s" % (PH_PREFIX, tag, name, PH_SUFFIX)


def _list_paths(paths):
    """素材清单字段值 → 绝对路径列表（兼容单路径/列表；目录型 path 展开为目录内图片）。"""
    if not paths:
        return []
    if isinstance(paths, str):
        paths = [paths]
    out = []
    for p in paths:
        if not p:
            continue
        if os.path.isdir(p):
            for f in sorted(os.listdir(p)):
                if f.lower().endswith((".png", ".jpg", ".jpeg", ".bmp", ".gif")):
                    out.append(os.path.join(p, f))
        else:
            out.append(p)
    return out


def _person_images(material, name, kinds):
    """按人员姓名取素材（清单 personnel 中该人员的指定类型路径列表；兼容按目录 glob）。"""
    out = []
    for p in material.get("personnel") or []:
        if (p.get("name") or "").strip() != name:
            continue
        for k in kinds:
            out += _list_paths(p.get(k))
    return out


def _group_cert_images(files, spec_map):
    """人员证书按类型生成 (路径, spec键, 换页) 列表：多页(_P0/_P1...)有序、单页在后。"""
    items = []
    seen = set()
    for f in files:
        if f in seen:
            continue
        seen.add(f)
        base = os.path.basename(f)
        if re.search(r"_P\d+\.[^.]+$", base):
            prefix = re.sub(r"_P\d+\.[^.]+$", "", base)
            for sname, skey in spec_map:
                if sname in base or sname in prefix:
                    items.append((f, skey, True))
                    break
            else:
                items.append((f, "职称证", True))
        else:
            for sname, skey in spec_map:
                if sname in base:
                    items.append((f, skey, True))
                    break
            else:
                items.append((f, "职称证", True))
    return items


# ---------------------------------------------------------------------------
# 占位文案 ↔ 素材清单：唯一解析入口
# ---------------------------------------------------------------------------
def build_ph_rules(material):
    """由素材清单构建「文件 → 图片占位规则」树。

    返回 {文件名: [ {ph, anchor, items:[(abs_path, spec_key, need_pagebreak)], group}, ... ]}
    anchor: ("table"|"para", 锚点关键词) —— 供 gen 定位插入位置；
    items:  素材绝对路径 + image_spec 尺寸键 + 是否强制换页；
    group:  分组键（同一组图片排完再插入下一组时另起一页）。
    """
    rules = {}
    biz = material.get("企业基础信息", {}) or {}
    legal = (biz.get("法定代表人姓名") or "").strip()
    agent = (biz.get("委托代理人姓名") or "").strip()
    persons = material.get("personnel") or []
    director = persons[0].get("name", "") if persons else ""

    # ---- 资质组（附表1 组织机构表后）----
    qual = []
    for it in material.get("qualification_required") or []:
        for f in _list_paths(it.get("path")):
            name = (it.get("name") or os.path.basename(f)).strip()
            skey = "营业执照扫描件" if "营业" in name else (
                "资质证书_房屋建筑工程甲级" if "甲级" in name else "资质证书_市政公用工程乙级")
            qual.append((f, skey, True))
    if qual:
        rules.setdefault("资格证明及辅助资料表.docx", []).append({
            "ph": _ph("企业资质证书扫描件"),
            "anchor": ("table", "组织机构"),
            "items": qual, "group": "资质组",
        })

    # ---- 业绩监理合同图（附表3 已完类似工程施工监理项目情况表 实例级）----
    # L4 修复（2026-10-18）：人工标书实证「业绩表后跟业绩图组」（化工园 P21-32）；
    # 生成版此前缺业绩图片占位（资格表只有资质/人员/社保/附表10 图组）。
    # 每业绩一组（素材清单 performance 各 1 张监理合同图），第 i 份附表3 后插第 i 组。
    for perf in material.get("performance") or []:
        items = [(f, "监理合同", True) for f in _list_paths(perf.get("path"))]
        if not items:
            continue
        proj = os.path.basename(os.path.dirname(items[0][0]))   # 素材父目录含项目名
        rules.setdefault("资格证明及辅助资料表.docx", []).append({
            "ph": _ph("%s-监理合同" % proj),
            # 锚点=附表3 表格（标题「已完类似工程监理项目情况表」，无"施工"二字；
            # 附表2 汇总表含"汇总"不匹配）
            "anchor": ("table", "已完类似工程监理项目情况表"),
            "items": items, "group": "业绩组-%s" % proj,
        })

    # ---- 人员证书/职称/简历/毕业证（附表8 简历表备注段后，每人一组）----
    for p in persons:
        name = (p.get("name") or "").strip()
        certs = _list_paths(p.get("注册证书")) + _list_paths(p.get("岗位证书"))
        cert_items = []
        for f in certs:
            base = os.path.basename(f)
            skey = "岗位证书" if "岗位" in base or "监理员" in base else "注册监理工程师证书"
            cert_items.append((f, skey, True))
        zc_items = _group_cert_images(_list_paths(p.get("职称")),
                                      [("高级工程师", "总监高级工程师职称证书"),
                                       ("工程师", "职称证")])
        # 简历
        jl_items = [(f, "职称证", True) for f in _list_paths(p.get("简历"))]
        # 毕业证
        by_items = [(f, "职称证", True) for f in _list_paths(p.get("毕业证"))]
        group = []
        group += cert_items + zc_items + jl_items + by_items
        if group:
            rules.setdefault("资格证明及辅助资料表.docx", []).append({
                "ph": _ph("%s-注册证书、岗位证书、职称、身份证等证明材料" % name),
                # L4 修复（2026-10-18）：人员图组锚点改为表格实例级「拟投入监理人员简历表」——
                # 人工标书为每人简历表后跟该人图组（P35-58）；原 para 锚点把全组集中插在备注段后。
                # 注意：招标原文标题为「表 8  拟投入监理人员简历表」（渲染 OCR 曾误读为"履历表"）。
                "anchor": ("table", "拟投入监理人员简历表"),
                "items": group, "group": "人员组-%s" % name,
            })

    # ---- 社保（附表8 备注段后；清单 social_security_required）----
    ss = []
    for it in material.get("social_security_required") or []:
        for f in _list_paths(it.get("path")):
            ss.append((f, "社保证明", True))
    if ss:
        rules.setdefault("资格证明及辅助资料表.docx", []).append({
            "ph": _ph("拟投入监理人员社保证明"),
            "anchor": ("para", "具体按招标公告和评标办法要求附相应资料"),
            "items": ss, "group": "社保组",
        })

    # ---- 附表10 其他资料表后：三体系/总监职称/其他人员职称/荣誉(示范·先进·总监荣誉) ----
    # 按人工标书实证列表顺序：1三体系 2总监职称 3其他人员职称 4先进(如清单有) 5示范 6总监荣誉
    iso = [(f, "三体系认证证书", True) for it in (material.get("iso_certificates") or [])
           for f in _list_paths(it.get("path"))]
    if iso:
        rules.setdefault("资格证明及辅助资料表.docx", []).append({
            "ph": _ph("三体系认证证书"), "anchor": ("table", "其他资料"),
            "items": iso, "group": "附表10-三体系",
        })
    dir_zc = _person_images(material, director, ("职称",))
    d_items = _group_cert_images(dir_zc, [("高级工程师", "总监高级工程师职称证书"), ("工程师", "职称证")])
    if d_items:
        rules.setdefault("资格证明及辅助资料表.docx", []).append({
            "ph": _ph("总监高级工程师职称证书"), "anchor": ("table", "其他资料"),
            "items": d_items, "group": "附表10-总监职称",
        })
    oth_zc = []
    for p in persons[1:]:
        oth_zc += _group_cert_images(_list_paths(p.get("职称")), [("工程师", "职称证")])
    if oth_zc:
        rules.setdefault("资格证明及辅助资料表.docx", []).append({
            "ph": _ph("其他监理人员职称证书"), "anchor": ("table", "其他资料"),
            "items": oth_zc, "group": "附表10-人员职称",
        })
    # 荣誉组：监理示范工程 / 先进监理企业 / 总监荣誉（清单有则生成，无则跳过）
    honors = material.get("honors") or []
    demo = [(f, "监理示范优质工程", True) for it in honors if "示范" in (it.get("name") or "")
            for f in _list_paths(it.get("path"))]
    if demo:
        rules.setdefault("资格证明及辅助资料表.docx", []).append({
            "ph": _ph("监理示范（优质）工程"), "anchor": ("table", "其他资料"),
            "items": demo, "group": "附表10-示范",
        })
    adv = [(f, "先进优秀监理企业证书", True) for it in honors
           if ("先进" in (it.get("name") or "") or "优秀" in (it.get("name") or ""))
           for f in _list_paths(it.get("path"))]
    if adv:
        rules.setdefault("资格证明及辅助资料表.docx", []).append({
            "ph": _ph("先进（优秀）监理企业证书"), "anchor": ("table", "其他资料"),
            "items": adv, "group": "附表10-先进",
        })
    zjh = [(f, "先进优秀监理企业证书", True) for it in honors
           if "总监" in (it.get("name") or "") and ("荣誉" in (it.get("name") or "") or "优秀" in (it.get("name") or ""))
           for f in _list_paths(it.get("path"))]
    if zjh:
        rules.setdefault("资格证明及辅助资料表.docx", []).append({
            "ph": _ph("总监荣誉"), "anchor": ("table", "其他资料"),
            "items": zjh, "group": "附表10-总监荣誉",
        })

    # ---- 法代/代理身份证（『附：』段后，7.5×4.5 固定框）----
    # L2a（2026-10-17）：素材清单 企业基础信息 新增 法定代表人身份证/委托代理人身份证
    # 字段（mat_export 从 素材库/人员/<姓名>/身份证/ 自动定位，P0/P1 正反面）；
    # 清单无字段时回退按该人员其余素材目录猜「身份证」目录。
    for role, name, anchor_kw, tag in (
            ("法定代表人", legal, "法定代表人有效期内居民身份证", "法代"),
            ("委托代理人", agent, "委托代理人有效期内居民身份证", "代理")):
        if not name:
            continue
        idc = _list_paths((biz.get("%s身份证" % ("法定代表人" if role == "法定代表人" else "委托代理人"))) or [])
        if not idc:
            for p in material.get("personnel") or []:
                if (p.get("name") or "").strip() != name:
                    continue
                for k in _PERSON_KINDS:
                    for f in _list_paths(p.get(k)):
                        d = os.path.dirname(f)
                        if d.rstrip("/\\").endswith("身份证"):
                            for sub in sorted(os.listdir(d)):
                                if sub.lower().endswith((".png", ".jpg", ".jpeg")):
                                    idc.append(os.path.join(d, sub))
        if not idc:
            continue
        fname = "法定代表人身份证明.docx" if role == "法定代表人" else "授权委托书.docx"
        rules.setdefault(fname, []).append({
            "ph": _ph("%s身份证正、反面扫描件" % role),
            "anchor": ("para", anchor_kw),
            "items": [(f, "身份证_法代授权", False) for f in idc],
            "group": "%s身份证" % tag,
        })

    # ---- 投标单位业绩材料和奖项.docx（独立文件，人工标书实证章节顺序）----
    award = {}
    if iso:
        award["一、三体系认证证书"] = iso
    perf = []
    for it in material.get("performance") or []:
        for f in _list_paths(it.get("path")):
            perf.append((f, "职称证", True))
    if perf:
        award["二、业绩"] = perf
    if d_items:
        award["三、拟派本项目总监的工程师职称证书"] = d_items
    if oth_zc:
        award["四、拟派本项目监理人员的中级工程师职称"] = oth_zc
    if adv:
        award["五、先进（优秀）监理企业证书"] = adv
    if demo:
        award["六、监理示范工程"] = demo
    if zjh:
        award["七、拟派本项目总监荣誉"] = zjh
    if award:
        for title, items in award.items():
            rules.setdefault("投标单位业绩材料和奖项.docx", []).append({
                "ph": _ph(title.replace("、", "-")),
                "anchor": ("para", title),
                "items": items, "group": title,
            })

    return rules


def resolve_ph(ph_text, rules):
    """按占位文案在规则树中查 (anchor, items, group)；未命中返回 None。

    fill 引擎与 gen 生成共用：占位文案即索引键（同一份 rules 来源）。
    """
    for fname, phs in (rules or {}).items():
        for r in phs:
            if r["ph"] == ph_text:
                return fname, r["anchor"], r["items"], r["group"]
    return None


def iter_file_rules(rules, fname):
    """按文件取占位规则列表（gen 生成时按 anchor 顺序插入）。"""
    return rules.get(fname, [])
