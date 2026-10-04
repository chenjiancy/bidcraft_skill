# -*- coding: utf-8 -*-
"""⑦ filler 拆包 · 组合图片构建（③ 白名单 + ⑧ 数据驱动）。"""
import re
from pathlib import Path

__all__ = [
    "_CERT_DIRS", "_PROJ_DATA_PREFIX", "_norm_path", "_build_whitelist",
    "_is_whitelisted", "_filter_whitelist", "_omit_zc", "_cert_major",
    "_qual_level_from_mat", "_qual_cert_prefixes", "_honor_paths",
    "_find_person_images", "_is_multi_page", "_group_by_cert",
    "_build_zc_items", "_build_combo",
]

_CERT_DIRS = ("注册证书", "岗位证书")
# 项目资料目录（用户自行上传，如 社保*）——不在素材库，白名单默认放行
_PROJ_DATA_PREFIX = "项目资料/"


def _norm_path(p):
    return str(p).replace("\\", "/").strip().strip("/")


def _build_whitelist(material):
    """从素材清单提取白名单 → (allowed_paths, allowed_person_dirs, allowed_prefixes)。

    数据来源：
      1) 各 section（qualification_required/iso_certificates/honors/performance/
         social_security_required）的 path 字段（精确路径；目录型加前缀；逗号/顿号
         分隔的多文件逐个拆出）；
      2) 人员目录：personnel[].name + 企业基础信息.法定代表人姓名 / 委托代理人姓名
         → "人员/<姓名>" 前缀；
      3) "项目资料/" 固定放行（用户上传目录，不在素材库）。
    返回三元组，供 _is_whitelisted 判定。
    """
    allowed, prefixes, person_names = set(), set(), set()
    sections = ("qualification_required", "iso_certificates", "honors",
                "performance", "social_security_required")
    for section in sections:
        v = material.get(section)
        items = v if isinstance(v, list) else ([v] if isinstance(v, dict) else [])
        for item in items:
            if not isinstance(item, dict):
                continue
            raw = item.get("path", "")
            if not raw:
                continue
            raw = str(raw).replace("\\", "/").strip()
            is_dir = raw.endswith("/")
            parts = [raw]
            for sep in ("、", "，", ","):
                if sep in raw:
                    parts = [x for x in raw.split(sep) if x.strip()]
                    break
            for part in parts:
                part = _norm_path(part)
                if not part:
                    continue
                allowed.add(part)
                if is_dir:
                    prefixes.add(part + "/")
    for person in material.get("personnel", []) or []:
        n = (person.get("name") or "").strip()
        if n:
            person_names.add(n)
    biz = material.get("企业基础信息", {}) or {}
    for k in ("法定代表人姓名", "委托代理人姓名"):
        n = (biz.get(k) or "").strip()
        if n:
            person_names.add(n)
    person_dirs = {"人员/%s" % n for n in person_names}
    prefixes.add(_PROJ_DATA_PREFIX)
    return allowed, person_dirs, prefixes


def _is_whitelisted(rel, whitelist):
    """相对素材库路径是否在清单白名单内（精确路径 / 人员目录前缀 / 前缀 / 项目资料）。"""
    allowed, person_dirs, prefixes = whitelist
    rel = _norm_path(rel)
    if rel in allowed:
        return True
    if any(rel.startswith(p + "/") for p in person_dirs):
        return True
    if any(rel.startswith(p) for p in prefixes):
        return True
    return False


def _filter_whitelist(files, lib_root, whitelist):
    """过滤 glob 结果：清单内返回原路径，清单外返回相对路径列表。"""
    ok, outside = [], []
    lib_root = Path(lib_root)
    for f in files:
        rel = _norm_path(str(Path(f).relative_to(lib_root)))
        if _is_whitelisted(rel, whitelist):
            ok.append(f)
        else:
            outside.append(rel)
    return ok, outside


def _omit_zc(persons):
    """⑧ 动态化 _OMIT_ZC：职称缺口由素材清单 personnel 字段推导（status=职称缺口
    或 title_cert 含「无」），不再硬编码姓名。"""
    out = set()
    for p in persons or []:
        if (p.get("status") or "") == "职称缺口" or "无" in (p.get("title_cert") or ""):
            out.add((p.get("name") or "").strip())
    return out


def _cert_major(material):
    """⑧ 总监专业兜底：从 personnel[0].cert 括注中取专业段（如「房建+市政公用」）。"""
    ps = material.get("personnel", []) or []
    if ps:
        cert = ps[0].get("cert", "") or ""
        m = re.search(r"（([^）]*)", cert)
        if m:
            return m.group(1).strip().split("，")[0].strip()
    return ""


def _qual_level_from_mat(material):
    """⑧ 企业资质等级：从素材清单 qualification_required 的 path 文件名推导
    （如 房屋建筑工程监理甲级_20281222_P0.png → 房屋建筑工程监理甲级）。"""
    parts = []
    for item in material.get("qualification_required", []) or []:
        p = (item.get("path") or "").replace("\\", "/").strip()
        base = p.rsplit("/", 1)[-1]
        if "甲级" in base or "乙级" in base:
            prefix = re.sub(r"_\d{8}(_P\d+)?\.[^.]+$", "", base)
            if prefix and prefix not in parts:
                parts.append(prefix)
    parts.sort(key=lambda s: 0 if "甲级" in s else 1)
    return "；".join(parts)


def _qual_cert_prefixes(material):
    """⑧ 资质证书组合 glob 前缀：从清单 qualification_required 路径文件名推导。"""
    out = []
    for item in material.get("qualification_required", []) or []:
        p = (item.get("path") or "").replace("\\", "/").strip()
        base = p.rsplit("/", 1)[-1]
        if "甲级" in base or "乙级" in base:
            prefix = re.sub(r"_\d{8}(_P\d+)?\.[^.]+$", "", base)
            if prefix and prefix not in out:
                out.append(prefix)
    return out


def _honor_paths(material, starts):
    """⑧ 荣誉组合：从清单 honors[].path 直接取文件（文件名前缀匹配 starts）。"""
    out = []
    for item in material.get("honors", []) or []:
        p = (item.get("path") or "").replace("\\", "/").strip()
        if not p:
            continue
        base = p.rsplit("/", 1)[-1]
        if base.startswith(starts) and p not in out:
            out.append(p)
    return out


def _find_person_images(lib_root, name, *kinds):
    """人员子目录按类型收集图片；多页（_P0/_P1...）按页码有序、单页在后。"""
    base = Path(lib_root) / "人员" / name
    files = []
    for kind in kinds:
        d = base / kind
        if d.is_dir():
            files += list(d.glob("*.png")) + list(d.glob("*.jpg")) + list(d.glob("*.jpeg"))
    def _key(f):
        m = re.search(r"_P(\d+)\.[^.]+$", f.name)
        return (0, int(m.group(1))) if m else (1, 0, f.name)
    files.sort(key=_key)
    return files


def _is_multi_page(path):
    return bool(re.search(r"_P\d+\.[^.]+$", Path(path).name))


def _group_by_cert(files):
    """同一证书多页（_P0/_P1...）按文件名前缀分组。"""
    groups = []
    for f in files:
        base = re.sub(r"_P\d+\.[^.]+$", "", f.name)
        if groups and groups[-1][0] == base:
            groups[-1][1].append(f)
        else:
            groups.append((base, [f]))
    return [g[1] for g in groups]


def _build_zc_items(files):
    """职称证书：多页 11×16 每页两张；单页 23×16 占一页。"""
    items = []
    for g in _group_by_cert(files):
        multi = any(_is_multi_page(f) for f in g)
        for i, f in enumerate(g):
            items.append((str(f), "职称证", (i % 2 == 0) if multi else True))
    return items


def _build_combo(key, lib_root, proj_dir, material, whitelist=None):
    """组合图片占位 → (items, missing明细, outside清单外)。
    ③白名单：whitelist=None 时不做过滤（兼容旧调用）；否则每个 glob 结果
    必须命中清单白名单，未列明的素材记入 outside 且不插入。
    ⑧数据驱动：总监/法代/代理人姓名与资质/荣誉文件均从素材清单取，无硬编码姓名。"""
    items, missing, outside = [], [], []
    base = Path(lib_root)
    persons = material.get("personnel", []) or []
    biz = material.get("企业基础信息", {}) or {}
    director = persons[0].get("name", "") if persons else ""
    legal = (biz.get("法定代表人姓名") or "").strip()
    agent = (biz.get("委托代理人姓名") or "").strip()
    omit = _omit_zc(persons)

    def _take(fs):
        """过滤 glob 结果并收集清单外。"""
        if whitelist is None:
            return fs, []
        return _filter_whitelist(fs, base, whitelist)

    if "企业资质证书扫描件" in key:
        prefixes = _qual_cert_prefixes(material) or ["房屋建筑工程监理甲级", "市政公用工程监理乙级"]
        for prefix in prefixes:
            skey = "资质证书_房屋建筑工程甲级" if "甲级" in prefix else "资质证书_市政公用工程乙级"
            fs, out = _take(sorted((base / "资质").glob(prefix + "*.png")))
            outside += out
            for f in fs:
                items.append((str(f), skey, True))
        if not items:
            missing.append("企业资质证书素材缺失")
    elif "拟派监理人员注册证书" in key:
        for p in persons:
            name = p.get("name", "")
            certs, out = _take(_find_person_images(base, name, "注册证书", "岗位证书"))
            outside += out
            if not certs:
                missing.append("拟派人员[%s]注册/岗位证书" % name)
            for c in certs:
                skey = "岗位证书" if c.parent.name == "岗位证书" else "注册监理工程师证书"
                items.append((str(c), skey, True))
            zc, out = _take(_find_person_images(base, name, "职称证书"))
            outside += out
            if not zc and name not in omit:
                missing.append("拟派人员[%s]职称证书" % name)
            items.extend(_build_zc_items(zc))
            idc, out = _take(_find_person_images(base, name, "身份证"))
            outside += out
            if not idc:
                missing.append("拟派人员[%s]身份证" % name)
            for i, f in enumerate(idc):
                items.append((str(f), "身份证", i == 0))
    elif "社保证明" in key:
        d = Path(proj_dir) / "项目资料"
        fs = [f for f in d.glob("社保*")] if d.is_dir() else []
        for f in sorted(fs):
            items.append((str(f), "社保证明", True))
        if not items:
            missing.append("6人社保证明待出具（项目资料/社保* 待上传）")
    elif "三体系认证证书" in key:
        fs, out = _take(sorted((base / "资质").glob("ISO*.png")))
        outside += out
        for f in fs:
            items.append((str(f), "三体系认证证书", True))
        if not items:
            missing.append("三体系证书素材缺失")
    elif "总监高级工程师职称证书" in key:
        files, out = _take(_find_person_images(base, director, "职称证书"))
        outside += out
        items.extend(_build_zc_items(files))
        if not items:
            missing.append("%s职称证书素材缺失" % director)
    elif "其他监理人员职称证书" in key:
        for p in persons[1:]:
            name = p.get("name", "")
            files, out = _take(_find_person_images(base, name, "职称证书"))
            outside += out
            if not files:
                if name not in omit:
                    missing.append("其他监理人员[%s]职称证书" % name)
                continue
            items.extend(_build_zc_items(files))
    elif "先进（优秀）监理企业证书" in key:
        rels = _honor_paths(material, ("先进", "优秀"))
        if rels:
            fs = [Path(lib_root) / r for r in rels]
        else:
            fs = sorted((base / "荣誉").glob("先进监理企业*.png")) + \
                sorted((base / "荣誉").glob("优秀监理企业*.png"))
        fs, out = _take(fs)
        outside += out
        for f in fs:
            items.append((str(f), "先进优秀监理企业证书", True))
        if not items:
            missing.append("先进/优秀监理企业证书素材缺失")
    elif "监理示范（优质）工程" in key:
        rels = _honor_paths(material, ("监理示范",))
        if rels:
            fs = [Path(lib_root) / r for r in rels]
        else:
            fs = sorted((base / "荣誉").glob("监理示范工程*.png"))
        fs, out = _take(fs)
        outside += out
        for f in fs:
            items.append((str(f), "监理示范优质工程", True))
        if not items:
            missing.append("监理示范工程证书素材缺失")
    elif "法定代表人身份证正、反面" in key:
        if legal:
            idc, out = _take(_find_person_images(base, legal, "身份证"))
            outside += out
            for i, f in enumerate(idc):
                items.append((str(f), "身份证", i == 0))
        if not items:
            missing.append("法定代表人[%s]身份证素材缺失" % (legal or "未配置"))
    elif "委托代理人身份证正、反面" in key:
        if agent:
            idc, out = _take(_find_person_images(base, agent, "身份证"))
            outside += out
            for i, f in enumerate(idc):
                items.append((str(f), "身份证", i == 0))
        if not items:
            missing.append("委托代理人[%s]身份证素材缺失" % (agent or "未配置"))
    else:
        missing.append("未实现组合规则")
    return items, missing, outside
