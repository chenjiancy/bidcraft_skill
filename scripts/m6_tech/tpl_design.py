# -*- coding: utf-8 -*-
"""
bidcraft · M6 模板设计器（P0）—— template.json 数据模型、校验、暗标派生与 tpl-design 命令

模板描述文件（template.json）把「文档结构编排 + 样式引用 + 占位符绑定 + 规则」沉淀为
可设计、可校验、可持久化的结构化描述；docx 是渲染产物而非模板本体（"装配单"思想）。

与既有体系的关系（不推翻、只叠加）：
  - styleRef 十五组 id 值域 = 共享级 `共享资源/技术标风格/layout-presets.json`（复用 tech-layout entries）；
  - 暗标派生 = 暗标铁律（font 强制 dark-safe、图片二选一 dark-safe-img/no-source、
    页眉页脚二选一 hf9-dark-none/hf10-dark-page-only、微观六组按招标条款自动注入不开放选择，
    id 以 layout-presets.json 实际预设为准）；
  - M2 商务标母版 docx 可拆解为部件回流复用（P1 部件库）；本文件只负责"描述层"，渲染由 tech-export 承接（P1 模板驱动分支）。

P0 交付：
  - schema `m6.template/v1` 校验器（结构顺序 / 样式值域 / 占位符规范 / 规则值域 / 暗标派生）；
  - tpl-design 子命令：list / show / validate / apply（--confirm 落盘 + 写后回读）/ specimen（P0 以版面范式 preset 驱动出样张，P1 全映射）；
  - 示例模板 `共享资源/技术标风格/模板/示例-标准技术标.json`。

接口：
  python scripts/bidcraft.py tpl-design [--list] [--show <file>] [--validate <file>]
      [--apply <file> --confirm] [--specimen <file>] [--json]
"""
import json
import re
import sys
from pathlib import Path

# 保证 scripts/ 可被导入（与 bidcraft.py 相同的路径处理）
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _shared import core                  # noqa: E402
from . import layout as m6layout          # noqa: E402
from . import rules as m6rules            # noqa: E402
from . import sources                     # noqa: E402

TEMPLATE_SCHEMA = "m6.template/v1"
TEMPLATE_DIR_REL = Path("共享资源") / "技术标风格" / "模板"

# ---- 部件清单（P0）：与版面设计器预览的文档段一一对应 --------------------
PART_IDS = ("cover", "colophon", "toc", "body", "closing")
PART_LABELS = {"cover": "封面", "colophon": "扉页", "toc": "目录",
               "body": "正文", "closing": "结尾"}
PAGE_MODES = ("single", "flow")
REQUIRED_PARTS = ("cover", "body")          # P0：封面与正文必选，其余可选
MAX_ONCE_PARTS = PART_IDS                    # P0：每类部件至多出现一次
# 顺序约束：某部件出现时，其前置部件必须出现在它之前
BEFORE = {"colophon": ("cover",),
          "toc": ("cover", "colophon"),
          "body": ("cover", "colophon", "toc"),
          "closing": ("cover", "colophon", "toc", "body")}

# ---- 占位符规范 -----------------------------------------------------------
RE_PH_KEY = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
RE_PH_TEXT = re.compile(r"^\{\{\s*[a-z][a-z0-9_]{0,31}\s*\}\}$")
RE_PH_IMG = re.compile(r"^【图片占位：\S+】$")

# ---- 暗标铁律（对齐 tech-layout 提示；id 以 layout-presets.json 实际预设为准） --
DARK_FONT_ID = "dark-safe"                            # 暗标 font 强制（fontSchemes）
DARK_IMAGE_RULES = ("dark-safe-img", "no-source")     # 图片二选一：暗标安全 / 无图源
DARK_HEADER_FOOTERS = ("hf9-dark-none", "hf10-dark-page-only")   # 页眉页脚二选一
# 微观六组：暗标下按招标条款自动注入、不开放选择
DARK_INJECTED_GROUPS = ("pageSetup", "headingSystem", "tocStyle",
                        "tableStyle", "captionSystem", "paragraphStyle")

# ---- 示例模板（与 共享资源/技术标风格/模板/示例-标准技术标.json 一致） -------
TEMPLATE_EXAMPLE = {
    "schema": TEMPLATE_SCHEMA,
    "version": "0.1",
    "updated": "2026-10-23",
    "name": "示例：标准技术标",
    "description": "P0 示例模板：封面+扉页+目录+正文+结尾，样式引用默认组合。",
    "structure": [
        {"part": "cover", "pageMode": "single"},
        {"part": "colophon", "pageMode": "single", "optional": True},
        {"part": "toc", "pageMode": "single"},
        {"part": "body", "pageMode": "flow"},
        {"part": "closing", "pageMode": "single", "optional": True},
    ],
    "styleRef": {
        "preset": "single-column", "palette": "deep-indigo", "cover": "full-block",
        "decoration": "standard", "font": "gov-gongwen", "imageRatio": "mid",
        "imageRule": "hybrid", "imageLayout": "split-h",
        "pageSetup": "p1-standard-a4", "headingSystem": "h1-gbt-arabic",
        "tocStyle": "t1-jianyu-auto", "tableStyle": "tb1-three-line",
        "captionSystem": "c2-cy-chapter", "paragraphStyle": "pa7-jianyu-15",
        "headerFooter": "hf1-classic-enterprise",
    },
    "placeholders": {
        "enterprise_name": "{{ enterprise_name }}",
        "project_name": "{{ project_name }}",
        "bid_date": "{{ bid_date }}",
        "site_photo": "【图片占位：施工现场】",
    },
    "rules": {
        "bidMode": "明标",
        "darkFontSafe": True,
    },
    "provenance": {"basedOn": "", "author": "bidcraft", "created": "2026-10-23",
                   "note": "P0 示例，供模板设计器数据模型演示与测试。"},
}


# ---------------------------------------------------------------------------
# 定位与读取
# ---------------------------------------------------------------------------
def find_template_dir(args):
    """→ 模板描述目录（共享资源/技术标风格/模板）；素材库根或其父目录下均可见。"""
    root = sources.lib_root(args)
    for base in (root / "共享资源" / "技术标风格", root.parent / "共享资源" / "技术标风格"):
        d = base / "模板"
        if d.is_dir():
            return d
    return None


def find_templates(args):
    """→ 模板目录内全部 *.json（按文件名排序）；目录缺失返回 []。"""
    d = find_template_dir(args)
    if d is None:
        return []
    return sorted(p for p in d.glob("*.json") if p.is_file())


def resolve_template(args, file):
    """file 可为绝对/相对路径，或模板目录内文件名 → 绝对 Path。"""
    p = Path(file)
    if not p.is_absolute() and p.parent == Path("."):
        d = find_template_dir(args)
        if d is not None:
            cand = d / file
            if cand.is_file():
                return cand
    return p


def load_template(args, file):
    """读模板描述 → dict；缺失/无法解析抛 LibraryError（与 layout.load_presets 一致）。"""
    p = resolve_template(args, file)
    if not p.is_file():
        raise core.LibraryError("模板描述文件不存在：%s（tpl-design --list 查看模板目录）" % p)
    doc = core.read_json(str(p), None)
    if not isinstance(doc, dict):
        raise core.LibraryError("模板描述无法解析为 JSON 对象：%s" % p)
    return p, doc


# ---------------------------------------------------------------------------
# 校验
# ---------------------------------------------------------------------------
def _issue(level, code, msg):
    return {"level": level, "code": code, "msg": msg}


def _validate_structure(structure, issues):
    if not isinstance(structure, list) or not structure:
        issues.append(_issue("err", "struct-empty", "structure 必须是非空数组（至少含封面与正文）"))
        return
    order = []
    for i, item in enumerate(structure):
        if not isinstance(item, dict):
            issues.append(_issue("err", "struct-item", "structure[%d] 必须是对象" % i))
            continue
        part = item.get("part")
        if part not in PART_IDS:
            issues.append(_issue("err", "struct-part", "structure[%d] 部件 %r 不在部件清单 %s 内"
                                % (i, part, "/".join(PART_IDS))))
            continue
        pm = item.get("pageMode", "single")
        if pm not in PAGE_MODES:
            issues.append(_issue("err", "struct-pagemode", "%s 的 pageMode %r 非法（允许 %s）"
                                % (part, pm, "/".join(PAGE_MODES))))
        order.append(part)
    # 重复部件（P0：每类至多一次）
    dup = [p for p in PART_IDS if order.count(p) > 1]
    for p in dup:
        issues.append(_issue("err", "struct-dup", "部件 %s 出现多次（P0 每类至多一次）" % p))
    # 必选部件
    for p in REQUIRED_PARTS:
        if p not in order:
            issues.append(_issue("err", "struct-missing", "必选部件 %s（%s）缺失" % (p, PART_LABELS[p])))
    # 顺序约束
    for p in order:
        for need in BEFORE.get(p, ()):
            if need not in order:
                issues.append(_issue("warn", "struct-before-opt",
                                     "%s 的前置部件 %s 未出现（可选时提示）" % (p, need)))
                continue
            if order.index(need) > order.index(p):
                issues.append(_issue("err", "struct-order", "%s 必须出现在 %s 之后" % (need, p)))
    if "cover" in order and order.index("cover") != 0:
        issues.append(_issue("err", "struct-cover-first", "封面 cover 必须作为第一个部件"))


def _validate_style_ref(style_ref, presets_doc, issues):
    if style_ref is None:
        return
    if not isinstance(style_ref, dict):
        issues.append(_issue("err", "style-type", "styleRef 必须是对象"))
        return
    group_ids = {g: [r["id"] for r in m6layout.entries(presets_doc, g)] for g, _ in m6layout.GROUPS}
    for key, val in style_ref.items():
        if key not in group_ids:
            issues.append(_issue("err", "style-key", "styleRef 未知组 %r（允许 %s）"
                                % (key, "/".join(g for g, _ in m6layout.GROUPS))))
            continue
        if not isinstance(val, str) or not val.strip():
            issues.append(_issue("err", "style-val", "styleRef.%s 必须是非空字符串" % key))
            continue
        if val.strip() not in group_ids[key]:
            issues.append(_issue("err", "style-id", "styleRef.%s=%r 不在该组预设内（tech-layout --list 查看）"
                                % (key, val.strip())))


def _validate_placeholders(ph, issues):
    if ph is None:
        return
    if not isinstance(ph, dict):
        issues.append(_issue("err", "ph-type", "placeholders 必须是对象"))
        return
    for key, val in ph.items():
        if not RE_PH_KEY.match(key):
            issues.append(_issue("err", "ph-key", "占位符键 %r 不符合规范（小写字母开头，a-z0-9_，≤32 字符）" % key))
        if isinstance(val, str):
            if not (RE_PH_TEXT.match(val.strip()) or RE_PH_IMG.match(val.strip()) or val.strip() == ""):
                issues.append(_issue("err", "ph-val", "占位符值 %r 不规范（{{ key }} 或 【图片占位：类别】）" % val))
        else:
            issues.append(_issue("err", "ph-val-type", "占位符 %s 的值必须是字符串" % key))


def _validate_rules(rules_doc, issues):
    if rules_doc is None:
        return
    if not isinstance(rules_doc, dict):
        issues.append(_issue("err", "rules-type", "rules 必须是对象"))
        return
    known = {"bidMode", "darkFontSafe", "coverUnderlay", "pageBreak", "tablesOnePage"}
    for key in rules_doc:
        if key not in known:
            issues.append(_issue("warn", "rules-key", "rules 未知键 %r（P0 仅识别 %s）"
                                % (key, "/".join(sorted(known)))))
    bm = rules_doc.get("bidMode")
    if bm is not None and bm not in m6rules.BID_MODES:
        issues.append(_issue("err", "rules-bidmode", "rules.bidMode=%r 非法（允许 %s）"
                            % (bm, "/".join(m6rules.BID_MODES))))


def validate_template(doc, presets_doc, parts=None):
    """模板描述全量校验 → (ok, issues)。presets_doc 可为 None（回退内置清单）；
    parts 为部件清单 {部件名: part_doc}（None 时不校验 partRef 存在性，仅提示需部件库）。"""
    issues = []
    if not isinstance(doc, dict):
        return False, [_issue("err", "doc-type", "模板描述必须是 JSON 对象")]
    if doc.get("schema") != TEMPLATE_SCHEMA:
        issues.append(_issue("err", "schema", "schema 必须是 %s" % TEMPLATE_SCHEMA))
    if not (doc.get("name") or "").strip():
        issues.append(_issue("err", "name", "name 必填（模板用途说明）"))
    _validate_structure(doc.get("structure"), issues)
    _validate_part_refs(doc.get("structure"), parts, issues)
    _validate_style_ref(doc.get("styleRef"), presets_doc, issues)
    _validate_placeholders(doc.get("placeholders"), issues)
    _validate_rules(doc.get("rules"), issues)
    # 暗标合规：styleRef 的 font/imageRule/headerFooter 是否满足铁律
    rules_doc = doc.get("rules") or {}
    if rules_doc.get("bidMode") == "暗标":
        _check_dark_compliance(doc.get("styleRef") or {}, presets_doc, issues)
    issues.sort(key=lambda i: 0 if i["level"] == "err" else (1 if i["level"] == "warn" else 2))
    ok = not any(i["level"] == "err" for i in issues)
    return ok, issues


def _validate_part_refs(structure, parts, issues):
    """structure 项的 partRef：引用部件必须存在于部件库（tpl-part --list）。"""
    if not isinstance(structure, list):
        return
    for i, item in enumerate(structure):
        if not isinstance(item, dict):
            continue
        ref = item.get("partRef")
        if not ref:
            continue
        if parts is None:
            issues.append(_issue("warn", "part-lib", "structure[%d].partRef=%r 存在，但未提供部件库（tpl-part --list 查看可用部件）"
                                % (i, ref)))
            continue
        key = ref[:-5] if ref.endswith(".json") else ref
        if key not in parts:
            issues.append(_issue("err", "part-ref", "structure[%d].partRef=%r 引用的部件不存在（tpl-part --list 查看部件库）"
                                % (i, ref)))


def _check_dark_compliance(style_ref, presets_doc, issues):
    font_ids = [r["id"] for r in m6layout.entries(presets_doc, "font")]
    img_ids = [r["id"] for r in m6layout.entries(presets_doc, "imageRule")]
    hf_ids = [r["id"] for r in m6layout.entries(presets_doc, "headerFooter")]
    if style_ref.get("font") and style_ref["font"] != DARK_FONT_ID and DARK_FONT_ID in font_ids:
        issues.append(_issue("err", "dark-font", "暗标强制 font=%s（当前 %r）" % (DARK_FONT_ID, style_ref["font"])))
    if style_ref.get("imageRule") and style_ref["imageRule"] not in DARK_IMAGE_RULES:
        if any(i in img_ids for i in DARK_IMAGE_RULES):
            issues.append(_issue("err", "dark-image", "暗标图片二选一：%s（当前 %r）"
                                % (" / ".join(DARK_IMAGE_RULES), style_ref["imageRule"])))
    if style_ref.get("headerFooter") and style_ref["headerFooter"] not in DARK_HEADER_FOOTERS:
        if any(i in hf_ids for i in DARK_HEADER_FOOTERS):
            issues.append(_issue("err", "dark-headerfooter", "暗标页眉页脚二选一：%s（当前 %r）"
                                % (" / ".join(DARK_HEADER_FOOTERS), style_ref["headerFooter"])))
    for g in DARK_INJECTED_GROUPS:
        if style_ref.get(g):
            issues.append(_issue("info", "dark-micro-inject", "%s 暗标下按招标条款自动注入、不开放选择（已忽略 %r）"
                                % (g, style_ref[g])))


# ---------------------------------------------------------------------------
# 暗标派生（确定性）
# ---------------------------------------------------------------------------
def dark_derived(doc, presets_doc):
    """按 rules.bidMode 派生最终 15 组 layout → (layout, notes)。

    明标：styleRef 键覆盖默认，缺省键回默认；
    暗标：font 强制 dark-safe、图片二选一（原值不在集合则安全降级 none）、
          页眉页脚二选一（原值不在集合则降级 hf9）、微观六组忽略 styleRef 回默认注入。
    notes：逐条记录派生/降级说明，供 --show / UI 披露。
    """
    style_ref = doc.get("styleRef") or {}
    layout = dict(sources.DEFAULT_LAYOUT)
    if isinstance(style_ref, dict):
        for g, _ in m6layout.GROUPS:
            v = style_ref.get(g)
            if isinstance(v, str) and v.strip():
                layout[g] = v.strip()
    notes = []
    if (doc.get("rules") or {}).get("bidMode") == "暗标":
        font_ids = [r["id"] for r in m6layout.entries(presets_doc, "font")]
        img_ids = [r["id"] for r in m6layout.entries(presets_doc, "imageRule")]
        hf_ids = [r["id"] for r in m6layout.entries(presets_doc, "headerFooter")]
        if DARK_FONT_ID in font_ids and layout["font"] != DARK_FONT_ID:
            notes.append("暗标：font %s → %s（强制）" % (layout["font"], DARK_FONT_ID))
            layout["font"] = DARK_FONT_ID
        if layout["imageRule"] not in DARK_IMAGE_RULES:
            old = layout["imageRule"]
            layout["imageRule"] = "no-source" if any(i in img_ids for i in DARK_IMAGE_RULES) else layout["imageRule"]
            if layout["imageRule"] != old:
                notes.append("暗标：imageRule %s → no-source（图片二选一，安全降级）" % old)
        if layout["headerFooter"] not in DARK_HEADER_FOOTERS:
            old = layout["headerFooter"]
            layout["headerFooter"] = "hf9-dark-none" if any(i in hf_ids for i in DARK_HEADER_FOOTERS) else layout["headerFooter"]
            if layout["headerFooter"] != old:
                notes.append("暗标：headerFooter %s → hf9-dark-none（二选一，安全降级）" % old)
        for g in DARK_INJECTED_GROUPS:
            if style_ref.get(g):
                notes.append("暗标：%s %s 忽略，按招标条款自动注入" % (g, style_ref[g]))
    return layout, notes


def _parts_index(args):
    """部件库索引 {部件名: True}（供 partRef 校验）；部件库缺失返回 None 表示未提供。"""
    from . import partlib
    files = partlib.find_part_files(args)
    return {k: True for k in files} if files else None


# ---------------------------------------------------------------------------
# tpl-design 命令
# ---------------------------------------------------------------------------
def _print_issues(issues, indent="  "):
    for i in issues:
        lv = {"err": "错误", "warn": "提示", "info": "信息"}.get(i["level"], i["level"])
        print("%s[%s] %s" % (indent, lv, i["msg"]))


def _full_layout(doc, presets_doc):
    """模板最终 15 组 layout（含暗标派生），缺省键回默认。"""
    layout, notes = dark_derived(doc, presets_doc)
    return layout, notes


def cmd_tpl_design(args):
    root = getattr(args, "root", None)
    jflag = getattr(args, "json", False)

    if getattr(args, "show", ""):
        return _cmd_show(args, jflag)
    if getattr(args, "validate", ""):
        return _cmd_validate(args, jflag)
    if getattr(args, "apply", ""):
        return _cmd_apply(args, jflag)
    if getattr(args, "specimen", ""):
        return _cmd_specimen(args, jflag)
    return _cmd_list(args, jflag)


def _cmd_list(args, jflag):
    presets_doc = m6layout.load_presets(args)
    paths = find_templates(args)
    if jflag:
        print(json.dumps({
            "ok": True, "schema": TEMPLATE_SCHEMA,
            "dir": str(find_template_dir(args)) if find_template_dir(args) else "",
            "templates": [{"name": p.stem, "file": p.name, "path": str(p)} for p in paths],
        }, ensure_ascii=False, indent=2))
        return 0
    d = find_template_dir(args)
    print("模板描述 · %s" % (d if d else "未找到 %s（首次使用时创建）" % TEMPLATE_DIR_REL))
    print("schema：%s ｜ 部件：%s ｜ 暗标：font=%s、图片二选一、页眉页脚二选一" %
          (TEMPLATE_SCHEMA, "/".join(PART_LABELS[p] for p in PART_IDS), DARK_FONT_ID))
    if not paths:
        print("（空——可用 --apply <template.json> --confirm 落盘首个模板）")
        return 0
    print("\n模板清单（%d 个）：" % len(paths))
    for p in paths:
        try:
            doc = core.read_json(str(p), None) or {}
        except Exception:  # noqa: BLE001
            doc = {}
        ok, issues = validate_template(doc, presets_doc, _parts_index(args)) if isinstance(doc, dict) else (False, [])
        errs = sum(1 for i in issues if i["level"] == "err")
        print("  %-28s %s（错误 %d / 提示 %d）" % (p.name, "通过" if ok else "不通过", errs,
                                              sum(1 for i in issues if i["level"] != "err")))
    return 0


def _cmd_show(args, jflag):
    presets_doc = m6layout.load_presets(args)
    try:
        p, doc = load_template(args, args.show)
    except core.LibraryError as e:
        print(str(e))
        return 1
    ok, issues = validate_template(doc, presets_doc, _parts_index(args))
    layout, notes = _full_layout(doc, presets_doc)
    if jflag:
        print(json.dumps({
            "ok": ok, "path": str(p), "name": doc.get("name", ""),
            "description": doc.get("description", ""),
            "structure": doc.get("structure", []),
            "styleRef": doc.get("styleRef", {}),
            "layout": layout, "darkNotes": notes,
            "placeholders": doc.get("placeholders", {}),
            "rules": doc.get("rules", {}),
            "issues": issues,
        }, ensure_ascii=False, indent=2))
        return 0
    print("模板：%s（%s）" % (doc.get("name", ""), p))
    print("描述：%s" % (doc.get("description") or "—"))
    print("结构：")
    for item in doc.get("structure", []):
        mark = "（可选）" if item.get("optional") else ""
        print("  · %s %s%s" % (PART_LABELS.get(item.get("part"), item.get("part")),
                               item.get("pageMode", "single"), mark))
    print("最终样式（暗标派生后）：%s" % " → ".join("%s=%s" % (g, layout[g]) for g, _ in m6layout.GROUPS))
    for n in notes:
        print("  · %s" % n)
    if issues:
        print("校验：%s" % ("通过" if ok else "不通过"))
        _print_issues(issues)
    else:
        print("校验：通过（无问题）")
    return 0 if ok else 1


def _cmd_validate(args, jflag):
    presets_doc = m6layout.load_presets(args)
    try:
        p, doc = load_template(args, args.validate)
    except core.LibraryError as e:
        print(str(e))
        return 1
    ok, issues = validate_template(doc, presets_doc, _parts_index(args))
    if jflag:
        print(json.dumps({"ok": ok, "path": str(p), "issues": issues}, ensure_ascii=False, indent=2))
        return 0 if ok else 1
    print("校验 %s：%s" % (p, "通过" if ok else "不通过"))
    _print_issues(issues)
    return 0 if ok else 1


def _cmd_apply(args, jflag):
    """--apply <file> --confirm：校验 → 落盘登记到模板目录 → 写后回读校验。"""
    presets_doc = m6layout.load_presets(args)
    try:
        p, doc = load_template(args, args.apply)
    except core.LibraryError as e:
        print(str(e))
        return 1
    ok, issues = validate_template(doc, presets_doc, _parts_index(args))
    if not ok:
        if jflag:
            print(json.dumps({"ok": False, "issues": issues}, ensure_ascii=False, indent=2))
        else:
            print("校验未通过，拒绝落盘：")
            _print_issues(issues)
        return 1
    if not getattr(args, "confirm", False):
        print("未带 --confirm：仅 dry-run（校验通过，未写盘）。确认落盘请加 --confirm。")
        return 0
    d = find_template_dir(args)
    if d is None:
        # 模板目录不存在 → 创建（素材库根/共享资源/技术标风格/模板）
        root = sources.lib_root(args)
        d = root / "共享资源" / "技术标风格" / "模板"
        d.mkdir(parents=True, exist_ok=True)
    target = d / p.name
    if target.resolve() == p.resolve():
        action = "登记（已在模板目录内，回读校验）"
    else:
        if target.exists():
            raise core.LibraryError("目标已存在，防覆盖：%s（换名或人工处理）" % target)
        target.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
        action = "落盘"
    # 写后回读校验
    back, doc2 = load_template(args, str(target))
    ok2, issues2 = validate_template(doc2, presets_doc)
    if not ok2:
        raise core.LibraryError("写后回读校验未通过：%s（%s）" % (back, issues2[0]["msg"] if issues2 else "未知"))
    if jflag:
        print(json.dumps({"ok": True, "action": action, "path": str(back),
                          "name": doc.get("name", ""), "issues": issues2}, ensure_ascii=False, indent=2))
    else:
        print("模板%s：%s（回读校验通过）" % (action, back))
    return 0


def _cmd_specimen(args, jflag):
    """--specimen <file>：按模板全映射生成样张 docx（P1）。

    模板驱动导出：structure 决定部件渲染（封面/扉页/目录/正文/结尾）、styleRef 十五组生效、
    placeholders 由 --fill 填充、rules.bidMode 暗标铁律派生——真实项目或内置样例正文。
    """
    presets_doc = m6layout.load_presets(args)
    try:
        p, doc = load_template(args, args.specimen)
    except core.LibraryError as e:
        print(str(e))
        return 1
    ok, issues = validate_template(doc, presets_doc, _parts_index(args))
    if not ok:
        print("校验未通过，拒绝出样张：")
        _print_issues(issues)
        return 1
    from . import export as _export
    from .layout import _builtin_preview_fixture
    import shutil
    import tempfile
    from types import SimpleNamespace

    project = getattr(args, "project", "") or "预览项目"
    fill = getattr(args, "fill", "") or ""
    if getattr(args, "project", ""):
        # 真实项目：模板全映射导出成稿（企业名取 --enterprise）
        enterprise = getattr(args, "enterprise", "") or "安徽安硕工程咨询有限公司"
        _export.cmd_tech_export(SimpleNamespace(
            root=getattr(args, "root", None), enterprise=enterprise, project=project,
            template=str(p), fill=fill, override="", bid_mode="", out="", force=True))
        msg = ("项目 %s 已按模板「%s」导出（全映射：structure/styleRef/placeholders/暗标）："
               "技术标/产出/技术标_%s.docx" % (project, doc.get("name", ""), project))
        if jflag:
            print(json.dumps({"ok": True, "template": p.name, "project": project}, ensure_ascii=False, indent=2))
        else:
            print(msg)
        return 0
    tmp = tempfile.TemporaryDirectory()
    try:
        ent = _builtin_preview_fixture(tmp.name)
        out_dir = ent / "项目级" / "预览项目" / "技术标" / "产出"
        # fixture 分支：企业/项目固定为预览企业/预览项目（与 tech-layout --preview 同规）
        _export.cmd_tech_export(SimpleNamespace(
            root=tmp.name, enterprise="预览企业", project="预览项目",
            template=str(p), fill=fill, override="", bid_mode="", out=str(out_dir), force=True))
        target = Path.cwd() / ("技术标样张_%s.docx" % p.stem)
        shutil.copyfile(str(out_dir / ("技术标_%s.docx" % project)), str(target))
        if jflag:
            print(json.dumps({"ok": True, "template": p.name, "preset": (doc.get("styleRef") or {}).get("preset", ""),
                              "note": "P1 模板全映射：structure/styleRef/placeholders/暗标派生均生效"},
                             ensure_ascii=False, indent=2))
        else:
            print("按模板「%s」生成样张（模板全映射：structure/styleRef/placeholders/暗标派生均生效）：%s"
                  % (doc.get("name", ""), target))
            print("      打开 Word 目视排版；暗标条款样式由模板 rules.bidMode 派生。")
    finally:
        tmp.cleanup()
    return 0
