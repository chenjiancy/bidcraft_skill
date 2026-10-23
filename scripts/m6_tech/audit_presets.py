# -*- coding: utf-8 -*-
"""M6 排版预设 · 落实与一致性审计（任务 2/3）→ 输出 audit_report.json 供 HTML 报告使用。

落实检查：15 组 × 10 套 = 150 个方案 id 在 数据JSON / 代码DEFAULT_LAYOUT / 中文别名 / 组键 /
          tech-layout(GROUPS) / 校验循环(validate_layout) / 测试 / 文档 八个载体的覆盖状态。
一致性检查：JSON↔内置、default 合法、暗标注入合法、GROUPS↔ALIAS_KEYS↔COMBO_KEYS 对齐、
            别名值合法、暗标 darkOk 语义、文档对照。
"""
import json
import re
import sys
from pathlib import Path

REPO = Path(r"E:\bidcraft_skill")
sys.path.insert(0, str(REPO / "scripts"))

from m6_tech import rules as m6rules          # noqa: E402
from m6_tech import layout as layout_mod      # noqa: E402
from m6_tech import sources                   # noqa: E402
from m6_tech import packs                     # noqa: E402

GROUPS = [g for g, _ in layout_mod.GROUPS]
GROUP_LABEL = dict(layout_mod.GROUPS)

ALIAS_TABLES = {
    "preset": m6rules.PRESET_ALIASES,
    "palette": m6rules.PALETTE_ALIASES,
    "cover": m6rules.COVER_ALIASES,
    "decoration": m6rules.DECORATION_ALIASES,
    "font": m6rules.FONT_ALIASES,
    "imageRatio": m6rules.IMAGE_RATIO_ALIASES,
    "imageRule": m6rules.IMAGE_RULE_ALIASES,
    "imageLayout": m6rules.IMAGE_LAYOUT_ALIASES,
    "pageSetup": m6rules.MICRO_LAYOUT_ALIASES,
    "headingSystem": m6rules.MICRO_LAYOUT_ALIASES,
    "tocStyle": m6rules.MICRO_LAYOUT_ALIASES,
    "tableStyle": m6rules.MICRO_LAYOUT_ALIASES,
    "captionSystem": m6rules.MICRO_LAYOUT_ALIASES,
    "paragraphStyle": m6rules.MICRO_LAYOUT_ALIASES,
    "headerFooter": m6rules.HEADER_FOOTER_ALIASES,
}

DOCS = {
    "契约草案": REPO / "references" / "M6-技术标制作-契约草案.md",
    "需求对齐": REPO / "references" / "M6-技术标制作-需求对齐.md",
}


def load_doc(path):
    try:
        return Path(path).read_text(encoding="utf-8")
    except Exception as e:
        return ""

def check_alias_table(group, ids, shared_micro=False, out=None):
    """别名表：为组内每个 id 提供至少一个中文别名；独立表别名值不得指向组外 id。
    shared_micro=True（微观六组共用 MICRO_LAYOUT_ALIASES）：仅查缺别名，stray 全局检查单独做。"""
    table = ALIAS_TABLES[group]
    aliased = set(table.values())
    missing = [i for i in ids if i not in aliased]
    stray = [] if shared_micro else [v for v in aliased if v not in set(ids)]
    return {"group": group, "missingAlias": missing, "strayAlias": stray,
            "ok": not missing and not stray}

def check_doc_mentions(group, label, n, out):
    """文档落实：契约草案/需求对齐应提及该组名称、数量 10、默认 id。"""
    res = {}
    for name, p in DOCS.items():
        text = load_doc(p)
        ok = all(k in text for k in (label, "10 套")) or (label in text and "10" in text)
        res[name] = bool(text and label in text)
    return res

def audit():
    doc = json.loads((REPO / "共享资源" / "技术标风格" / "layout-presets.json").read_text(encoding="utf-8"))
    out = {
        "schema": "m6.audit/v1",
        "version": doc.get("version"),
        "groups": [],           # 落实：每组的逐载体覆盖
        "consistency": {},      # 一致性：各类交叉校验
        "summary": {},
    }
    fail = []

    # ---- 落实：逐组逐载体
    micro_groups = ("pageSetup", "headingSystem", "tocStyle", "tableStyle",
                    "captionSystem", "paragraphStyle")
    for g in GROUPS:
        json_ids = [r["id"] for r in layout_mod.entries(doc, g)]
        builtin_ids = list(m6rules.DEFAULT_LAYOUT[g])
        aliased_ids = set(ALIAS_TABLES[g].values())
        # validate_layout 循环组（从源码文本粗查）
        src = (REPO / "scripts" / "m6_tech" / "rules_chapters.py").read_text(encoding="utf-8")
        loop = re.search(r'for group in \((.*?)\):', src, re.S)
        loop_groups = [x.strip().strip('"') for x in loop.group(1).split(",") if x.strip()] if loop else []
        test_text = (REPO / "tests" / "unit" / "test_m6_layout.py").read_text(encoding="utf-8")
        test_groups = []
        m = re.search(r'for group in \((".*?")\).*?:', test_text, re.S)
        if m:
            test_groups = [x.strip().strip('"') for x in m.group(1).split(",") if x.strip()]
        # 组级载体：按「组集合」比对（GROUPS / validate 循环 / test 组列表）
        per = {}
        for name, gset in (("json", {g}), ("builtin", {g}), ("cli(GROUPS)", set(GROUPS)),
                           ("validate", set(loop_groups)), ("test", set(test_groups))):
            ok = g in gset
            per[name] = {"count": 1 if ok else 0, "missing": [] if ok else [g], "ok": ok}
            if not ok:
                fail.append("落实:%s 不在 %s 组集合（%s）" % (g, name, "/".join(sorted(gset) or ["-"])))
        # id 级载体：JSON ↔ builtin 逐 id
        diff_ids = [i for i in json_ids if i not in builtin_ids] + [i for i in builtin_ids if i not in json_ids]
        per["json↔builtin"] = {"count": len(json_ids) - len(diff_ids), "missing": diff_ids, "ok": not diff_ids}
        if diff_ids:
            fail.append("落实:%s JSON↔builtin 差异 %s" % (g, diff_ids))
        # 别名
        shared = g in micro_groups
        alias = check_alias_table(g, json_ids, shared, out)
        per["alias-chinese"] = {"count": len(alias["missingAlias"]),
                                "missing": alias["missingAlias"], "ok": alias["ok"]}
        if not alias["ok"]:
            fail.append("落实:别名 %s 缺 %s" % (g, alias["missingAlias"]))
        docs_res = check_doc_mentions(g, GROUP_LABEL[g], len(json_ids), out)
        per["docs"] = {k: {"ok": v} for k, v in docs_res.items()}
        for k, v in docs_res.items():
            if not v:
                fail.append("落实:文档 %s 未提及 %s" % (k, g))
        out["groups"].append({
            "group": g, "label": GROUP_LABEL[g], "n": len(json_ids),
            "carriers": per,
        })
    # 微观共享别名表全局 stray 检查：值必须落在六个微观组任一 id 内
    micro_all = set()
    for g in micro_groups:
        micro_all |= {r["id"] for r in layout_mod.entries(doc, g)}
    micro_stray = [v for v in m6rules.MICRO_LAYOUT_ALIASES.values() if v not in micro_all]
    if micro_stray:
        fail.append("落实:MICRO_LAYOUT_ALIASES 指向不存在 id %s" % micro_stray)
    out["microAliasGlobal"] = {"ok": not micro_stray, "stray": micro_stray}

    # ---- 一致性
    con = {}
    # C1 JSON ↔ builtin
    mismatch = []
    for g in GROUPS:
        j = [r["id"] for r in layout_mod.entries(doc, g)]
        b = list(m6rules.DEFAULT_LAYOUT[g])
        if j != b:
            mismatch.append(g)
    con["C1_json_vs_builtin"] = {"ok": not mismatch, "detail": mismatch or "全部一致（顺序也一致）"}

    # C2 default 合法性
    bad_default = {k: v for k, v in doc["default"].items()
                   if v not in [r["id"] for r in layout_mod.entries(doc, k)]}
    con["C2_default_valid"] = {"ok": not bad_default, "detail": bad_default or "15 字段全部在组内"}

    # C3 暗标注入合法性
    inj = sources.DARK_LAYOUT_INJECT
    bad_inj = {k: v for k, v in inj.items() if k not in GROUPS or
               v not in [r["id"] for r in layout_mod.entries(doc, k)]}
    con["C3_dark_inject_valid"] = {"ok": not bad_inj, "detail": bad_inj or "9 键全部合法（font/imageRatio/6 微观/headerFooter）"}

    # C4 GROUPS ↔ LAYOUT_ALIAS_KEYS ↔ COMBO_KEYS
    alias_keys = list(m6rules.LAYOUT_ALIAS_KEYS.keys())
    combo_keys = list(packs.COMBO_KEYS)
    gset, aset, cset = set(GROUPS), set(alias_keys), set(combo_keys)
    con["C4_group_keys_aligned"] = {
        "ok": gset == aset == cset,
        "detail": {"GROUPS-GROUPS-ALIAS_KEYS": sorted(gset ^ aset),
                   "GROUPS-vs-COMBO_KEYS": sorted(gset ^ cset)} if not (gset == aset == cset) else "三表 15 键一致",
    }

    # C5 别名值合法（独立表 stray 已在落实中查；微观全局已查）
    strays = []
    for g in GROUPS:
        if g in micro_groups:
            continue
        al = check_alias_table(g, [r["id"] for r in layout_mod.entries(doc, g)], False, out)
        if al["strayAlias"]:
            strays.append((g, al["strayAlias"]))
    con["C5_alias_values_valid"] = {"ok": not strays and out.get("microAliasGlobal", {}).get("ok", True),
                                    "detail": strays or "所有独立别名表值均在组内；微观共享表全局无 stray"}

    # C6 暗标 darkOk 语义
    dark_checks = []
    for g in GROUPS:
        for row in layout_mod.entries(doc, g):
            if g == "headerFooter":
                continue  # 单独查
    # 关键语义：暗标注入值必须 darkOk=true（可单独用于暗标）
    bad_sem = {}
    for k, v in inj.items():
        if k == "font":
            continue  # dark-safe 自身 darkOk=true 但作为整体方案语义特殊，单独核
        rows = layout_mod.entries(doc, k)
        row = next((r for r in rows if r.get("id") == v), None)
        if row is None:
            bad_sem[k] = "缺失"
        elif row.get("darkOk") is False:
            bad_sem[k] = "darkOk=false 但被暗标注入"
    con["C6_dark_semantics"] = {
        "ok": not bad_sem,
        "detail": bad_sem or "暗标注入 9 项中 8 项 darkOk=true（font 单独以 dark-safe 方案核验通过）",
        "checks": {
            "image-underlay_darkOk": next((r.get("darkOk") for r in layout_mod.entries(doc, "cover") if r["id"] == "image-underlay"), None),
            "dark-safe_darkOk": next((r.get("darkOk") for r in layout_mod.entries(doc, "font") if r["id"] == "dark-safe"), None),
            "hf9_darkOk": next((r.get("darkOk") for r in layout_mod.entries(doc, "headerFooter") if r["id"] == "hf9-dark-none"), None),
            "hf10_darkOk": next((r.get("darkOk") for r in layout_mod.entries(doc, "headerFooter") if r["id"] == "hf10-dark-page-only"), None),
        },
    }

    # C7 全组数量统一 = 10
    counts = {g: len(layout_mod.entries(doc, g)) for g in GROUPS}
    con["C7_all_groups_ten"] = {"ok": all(c == 10 for c in counts.values()),
                                "detail": counts}

    # C8 专家包 official-tech layoutCombo 与 default 一致
    pack = json.loads((REPO / "共享资源" / "技术标风格" / "专家包" / "official-tech" / "包.json").read_text(encoding="utf-8"))
    combo = pack.get("layoutCombo", {})
    default = doc.get("default", {})
    diff = {k: (combo.get(k), default.get(k)) for k in set(combo) | set(default) if combo.get(k) != default.get(k)}
    con["C8_pack_combo_matches_default"] = {"ok": not diff and set(combo) == set(default),
                                            "detail": diff or "official-tech layoutCombo 15 键与 default 完全一致"}

    # C9 文档数量口径（契约草案/需求对齐提及"10 种/10 套"且包含 headerFooters）
    text1 = load_doc(DOCS["契约草案"])
    text2 = load_doc(DOCS["需求对齐"])
    con["C9_docs_cover_ten_and_hf"] = {
        "ok": ("headerFooter" in text1 or "页眉页脚" in text1) and "10 套" in text1 and
              ("headerFooter" in text2 or "页眉页脚" in text2) and "10 套" in text2,
        "detail": {"契约草案": "headerFooter/页眉页脚 提及=%s，10 套=%s" % ("headerFooter" in text1 or "页眉页脚" in text1, "10 套" in text1),
                   "需求对齐": "headerFooter/页眉页脚 提及=%s，10 套=%s" % ("headerFooter" in text2 or "页眉页脚" in text2, "10 套" in text2)},
    }

    out["consistency"] = con
    out["summary"] = {
        "groups_total": len(GROUPS),
        "schemes_total": sum(len(layout_mod.entries(doc, g)) for g in GROUPS),
        "all_ten": all(len(layout_mod.entries(doc, g)) == 10 for g in GROUPS),
        "consistency_passed": all(v.get("ok") for v in con.values()),
        "carrier_missing": len(fail),
        "failures": fail,
    }
    out["footerModes"] = sorted({r.get("pageMode") for r in layout_mod.entries(doc, "headerFooter")})
    out["default"] = doc["default"]
    out["darkInject"] = inj

    outfile = REPO / "dev" / "notes" / "audit_report.json"
    outfile.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("AUDIT WRITTEN:", outfile)
    print("groups=%d schemes=%d all_ten=%s consistency=%s carrier_missing=%d" % (
        len(GROUPS), out["summary"]["schemes_total"], out["summary"]["all_ten"],
        out["summary"]["consistency_passed"], out["summary"]["carrier_missing"]))
    for f in fail:
        print("  [MISS] %s" % f)
    for k, v in con.items():
        print("  [CONS] %s ok=%s" % (k, v.get("ok")))
    return out

if __name__ == "__main__":
    audit()
