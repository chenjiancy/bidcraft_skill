# -*- coding: utf-8 -*-
"""
bidcraft · M6 技术标制作 —— 排版预设读取与 tech-layout 命令（T13，契约 §3.2/§7）

预设文件：共享级 `<软件根>/共享资源/技术标风格/layout-presets.json`
  十五组均为数组（可增行表，全部统一为 10 套）：presets / palettes / covers / decorations / fontSchemes / imageRatios / imageRules / imageLayouts / pageSetups / headingSystems / tocStyles / tableStyles / captionSystems / paragraphStyles / headerFooters
缺失时：回退 `rules.DEFAULT_LAYOUT` 内置清单，并在输出中标注「内置兜底」
`--preview`：调用 T10 导出引擎（tech-export）直接渲染样张 docx —— 指定 --project/--enterprise 时走真实项目；否则用内置样例 fixture 渲染并复制到 `./技术标样张_<preset>.docx`
"""
import json
import re

from _shared import core

from . import rules as m6rules
from . import sources

PRESETS_FILE = "layout-presets.json"
PRESETS_SCHEMA = "m6.layout-presets/v1"
GROUPS = (
    ("preset", "版面范式"),
    ("palette", "配色方案"),
    ("cover", "封面版式"),
    ("decoration", "装饰强度"),
    ("font", "字体方案"),
    ("imageRatio", "图文比例"),
    ("imageRule", "配图规则"),
    ("imageLayout", "配图排版"),
    ("pageSetup", "页面设置"),
    ("headingSystem", "标题体系"),
    ("tocStyle", "目录版式"),
    ("tableStyle", "表格样式"),
    ("captionSystem", "图表编号"),
    ("paragraphStyle", "段落样式"),
    ("headerFooter", "页眉页脚"),
)


# ---------------------------------------------------------------------------
# 读取
# ---------------------------------------------------------------------------
def find_presets(args):
    """→ 预设文件路径；共享资源在素材库根或其父目录下均可见（对齐 ctxpack 风格库）。"""
    root = sources.lib_root(args)
    for base in (root / "共享资源" / "技术标风格", root.parent / "共享资源" / "技术标风格"):
        p = base / PRESETS_FILE
        if p.is_file():
            return p
    return None


def load_presets(args):
    """读排版预设 → dict；文件缺失返回 None（调用方回退内置清单）。"""
    p = find_presets(args)
    if p is None:
        return None
    doc = core.read_json(str(p), None)
    if not isinstance(doc, dict):
        raise core.LibraryError("排版预设无法解析为 JSON 对象：%s" % p)
    return doc


def entries(doc, group):
    """某一组预设 → [{id, name, ...}]；兼容数组 / 对象数组 / dict 三写法。"""
    src = doc if isinstance(doc, dict) else {}
    for key in m6rules.LAYOUT_ALIAS_KEYS[group]:
        val = src.get(key)
        out = []
        if isinstance(val, list):
            for v in val:
                if isinstance(v, str):
                    out.append({"id": v, "name": v})
                elif isinstance(v, dict) and isinstance(v.get("id"), str) and v["id"]:
                    out.append(v)
        elif isinstance(val, dict):
            for k, v in val.items():
                if isinstance(k, str) and k:
                    out.append(dict(v, id=k) if isinstance(v, dict) else {"id": k, "name": k})
        if out:
            return out
    return [{"id": i, "name": i} for i in m6rules.DEFAULT_LAYOUT[group]]


def default_entry(doc):
    """十五组默认 id → {preset, palette, cover, decoration, font, imageRatio, imageRule, imageLayout, pageSetup, headingSystem, tocStyle, tableStyle, captionSystem, paragraphStyle, headerFooter}。"""
    out = dict(sources.DEFAULT_LAYOUT)
    src = doc.get("default") if isinstance(doc, dict) else None
    if isinstance(src, dict):
        for g, _ in GROUPS:
            v = src.get(g)
            if isinstance(v, str) and v.strip():
                out[g] = v.strip()
    return out


def palette_colors(doc, palette_id):
    """配色 → {id,name,primary,accent,heading,tableFill,coverBg[,coverBgEnd]}；未命中 None。"""
    for row in entries(doc, "palette"):
        if row.get("id") == palette_id:
            return row
    return None


def _name(doc, group, pid):
    for row in entries(doc, group):
        if row.get("id") == pid:
            return row.get("name") or pid
    return pid


# ---------------------------------------------------------------------------
# tech-layout
# ---------------------------------------------------------------------------
def _print_group(doc, group, label, default):
    rows = entries(doc, group)
    print("\n【%s · %d 种】" % (label, len(rows)))
    for row in rows:
        rid = row.get("id")
        name = row.get("name") or rid
        mark = " [默认]" if rid == default.get(group) else ""
        print("  %-18s %-10s%s" % (rid, name, mark))
        if group == "palette":
            colors = " ".join(row.get(k, "-") for k in
                              ("primary", "accent", "heading", "tableFill", "coverBg"))
            print("  %-18s %s" % ("", colors))
            flags = []
            if row.get("coverBgEnd"):
                flags.append("coverBgEnd=%s（两段近似）" % row["coverBgEnd"])
            if row.get("recommendedFor"):
                flags.append("推荐 %s" % "/".join(row["recommendedFor"]))
            if row.get("note"):
                flags.append(row["note"])
            if flags:
                print("  %-18s %s" % ("", "；".join(flags)))
        elif group == "font":
            parts = []
            for k in ("heading", "body", "western"):
                v = row.get(k)
                if isinstance(v, str) and v:
                    parts.append("%s=%s" % (k, v))
            if row.get("lineSpacing"):
                parts.append("行距%s" % row["lineSpacing"])
            if row.get("system"):
                parts.append(row["system"])
            if row.get("note"):
                parts.append(row["note"])
            if parts:
                print("  %-18s %s" % ("", " · ".join(parts)))
            sizes = row.get("sizes")
            if isinstance(sizes, dict) and sizes:
                print("  %-18s 字号：%s" % ("", " · ".join("%s %s" % (k, v) for k, v in sizes.items())))
        elif group == "cover" and row.get("darkOk") is False:
            print("  %-18s %s" % ("", row.get("note") or "暗标禁用"))
        elif group in ("imageRatio", "imageRule", "imageLayout"):
            flags = []
            if row.get("ratio"):
                flags.append("图:文 %s" % row["ratio"])
            if row.get("source"):
                flags.append("来源 %s" % row["source"])
            if row.get("darkOk") is False:
                flags.append("暗标禁用")
            if row.get("note"):
                flags.append(row["note"])
            print("  %-18s %s" % ("", "；".join(flags)))
        elif group in ("pageSetup", "headingSystem", "tocStyle", "tableStyle",
                       "captionSystem", "paragraphStyle", "headerFooter"):
            flags = []
            for k in ("margin", "gutter", "levels", "numbering", "title", "leading",
                      "lines", "headerFill", "figPos", "tablePos", "indent",
                      "lineSpacing", "align", "header", "footer", "pageMode"):
                v = row.get(k)
                if isinstance(v, str) and v:
                    flags.append(v)
            if row.get("darkOk") is False:
                flags.append("暗标禁用")
            if row.get("note"):
                flags.append(row["note"])
            print("  %-18s %s" % ("", "｜".join(flags)))
        elif row.get("docx"):
            print("  %-18s %s" % ("", row["docx"]))


def _sample_images():
    """→ 样张配图目录（共享资源/技术标风格/样张素材）；cwd 或其父目录下定位，找不到返回 None。"""
    from pathlib import Path

    for base in (Path.cwd(), Path.cwd().parent):
        d = base / "共享资源" / "技术标风格" / "样张素材"
        if d.is_dir():
            return d
    return None


def _builtin_preview_fixture(root, grid_pair=False):
    """内置样张 fixture：共享资源预设 + 预览企业/项目级/预览项目/技术标（3 章精简正文）。
    grid_pair=True 时在第一章插入连续两张照片引用（触发 grid 图组并排渲染）。"""
    import shutil
    import tempfile
    from pathlib import Path
    from types import SimpleNamespace

    shared = Path(root) / "共享资源" / "技术标风格"
    shared.mkdir(parents=True, exist_ok=True)
    preset_src = find_presets(SimpleNamespace(root=str(root)))
    if preset_src is None:
        # fixture 根是临时目录：回溯调用方项目（cwd 或其父目录）的共享资源
        for base in (Path.cwd(), Path.cwd().parent):
            p = base / "共享资源" / "技术标风格" / PRESETS_FILE
            if p.is_file():
                preset_src = p
                break
    if preset_src:
        shutil.copyfile(str(preset_src), str(shared / PRESETS_FILE))
    ent = Path(root) / "预览企业"
    tech = ent / "项目级" / "预览项目" / "技术标"
    for d in ("章节", "章节/.meta", "检查", "产出", "源文件"):
        (tech / d).mkdir(parents=True, exist_ok=True)
    for cid in ("ch-01", "ch-02", "ch-03"):
        (tech / "章节" / cid).mkdir(parents=True, exist_ok=True)
    tree = {
        "schema": "m6.tree/v1", "project": "预览项目", "confirmed": True,
        "layout": dict(sources.DEFAULT_LAYOUT),
        "chapters": [{"id": cid, "title": t, "status": "WRITTEN",
                      "files": {"body": "章节/%s/正文.md" % cid}}
                     for cid, t in (
                         ("ch-01", "第一章 工程概况与监理工作范围"),
                         ("ch-02", "第二章 监理工作依据、目标与内容"),
                         ("ch-03", "第三章 项目监理机构及人员配备"))],
    }
    (tech / "章节树.json").write_text(json.dumps(tree, ensure_ascii=False), encoding="utf-8")
    img_dir = _sample_images()
    img = {}
    if img_dir is not None:
        for key, fname in (
            ("site", "样张_施工现场全景.jpg"),
            ("survey", "样张_水准测量放线.jpg"),
            ("meeting", "样张_图纸会审.jpg"),
            ("flow_program", "样张_监理工作程序流程图.png"),
            ("flow_quality", "样张_质量控制程序流程图.png"),
        ):
            p = img_dir / fname
            if p.is_file():
                img[key] = str(p)
    def _fig(key, cap):
        if key not in img:
            return ""
        return "![%s](%s)\n" % (cap, img[key])
    bodies = {
        "ch-01": (
            "# 一、工程概况\n"
            "预览项目为框架剪力墙结构公共建筑，总建筑面积约 8.6 万平方米，地上十层、地下两层。\n"
            "## （一）项目理解\n"
            "本项目监理工作覆盖质量、进度、投资、安全环保与合同信息管理五大目标。\n"
            "- 质量控制：材料进场验收与旁站监理\n"
            "- 进度控制：总控计划动态纠偏\n"
            "| 序号 | 控制目标 | 主要措施 |\n"
            "| --- | --- | --- |\n"
            "| 1 | 质量目标 | 三检制、样板引路 |\n"
            "| 2 | 进度目标 | 关键线路周报纠偏 |\n"
            + _fig("site", "施工现场全景")
            + "现场主体结构已施工至十层，安全防护与绿色施工措施同步落实。\n"
            + (_fig("survey", "现场水准测量放线") + _fig("meeting", "监理例会图纸会审")
               + "现场水准测量放线与监理例会图纸会审工作对照如下，实测实量数据实时录入监理台账。\n" if grid_pair else "")
            + _fig("flow_quality", "质量控制验收程序流程图")
            + "质量控制执行报验制与旁站制，不合格项限期整改后重新报验，合格后方可进入下道工序。\n"
            "### 1. 监理工作范围\n"
            "施工阶段监理，含土建、安装、装饰、智能化、室外工程等全部专业。\n"),
        "ch-02": (
            "# 一、监理工作依据\n"
            "- 国家和地方有关工程建设的法律、法规与规章；\n"
            "- 《建设工程监理规范》GB/T 50319-2013。\n"
            + _fig("survey", "现场水准测量")
            + "现场监理人员正在开展水准测量放线复核，实测实量数据同步录入监理台账。\n"
            + _fig("flow_program", "监理工作程序流程图")
            + "项目监理机构按照既定工作程序有序推进三控两管一协调，竣工验收合格后签发工程移交证书。\n"
            "## （一）监理工作目标\n"
            "质量达到一次性验收合格标准；进度满足合同节点要求；投资控制在批准概算内。\n"
            "### 1. 监理工作制度\n"
            "建立监理例会、旁站监理、见证取样、巡视检查、资料管理制度。\n"),
        "ch-03": (
            "# 一、项目监理机构\n"
            "实行总监理工程师负责制，设总监理工程师 1 名、专业监理工程师 5 名、监理员 4 名。\n"
            "## （一）人员配备\n"
            "| 岗位 | 人数 | 资格要求 |\n"
            "| --- | --- | --- |\n"
            "| 总监理工程师 | 1 | 注册监理工程师、高级职称 |\n"
            "| 专业监理工程师 | 5 | 中级及以上职称 |\n"
            "### 1. 仪器设备配置\n"
            "配备全站仪、水准仪、回弹仪等常规检测仪器及监理信息化管理平台。\n"
            "- 全站仪、水准仪、回弹仪等常规检测仪器\n"
            "- 监理信息化管理平台\n"
            + _fig("meeting", "监理例会图纸会审")
            + "监理例会与图纸会审制度保障参建各方信息畅通，重大问题及时协调解决。\n"),
    }
    for cid, body in bodies.items():
        (tech / "章节" / cid / "正文.md").write_text(body, encoding="utf-8")
        (tech / "章节" / ".meta" / (cid + ".json")).write_text(
            json.dumps({"schema": "m6.ctx/v1", "chapter": cid, "project": "预览项目",
                        "context": {"tender_points": [], "pageBudget": 900}},
                       ensure_ascii=False), encoding="utf-8")
    return ent


def _render_preview(args, preset_id):
    """--preview <preset>：调 T10 tech-export 渲染样张（真实项目或内置 fixture）。"""
    from . import export

    doc = load_presets(args)
    if not any(r.get("id") == preset_id for r in entries(doc, "preset")):
        raise core.LibraryError("版面范式不存在：%s（tech-layout --list 查看全部）" % preset_id)
    project = getattr(args, "project", "") or "预览项目"
    enterprise = getattr(args, "enterprise", "") or "预览企业"
    if getattr(args, "project", ""):
        # 真实项目：直接调导出引擎（override 仅换版面范式，其余取项目默认）
        from types import SimpleNamespace

        export.cmd_tech_export(SimpleNamespace(
            root=args.root, enterprise=enterprise, project=project,
            override="preset=%s" % preset_id, bid_mode="", out="", force=True))
        return "项目 %s 已按 %s 导出：技术标/产出/技术标_%s.docx" % (project, preset_id, project)

    import shutil
    import tempfile
    from pathlib import Path
    from types import SimpleNamespace

    tmp = tempfile.TemporaryDirectory()
    try:
        ent = _builtin_preview_fixture(tmp.name)
        from types import SimpleNamespace

        out_dir = ent / "项目级" / "预览项目" / "技术标" / "产出"
        export.cmd_tech_export(SimpleNamespace(
            root=tmp.name, enterprise=enterprise, project=project,
            override="preset=%s" % preset_id, bid_mode="", out=str(out_dir), force=True))
        target = Path.cwd() / ("技术标样张_%s.docx" % preset_id)
        shutil.copyfile(str(out_dir / ("技术标_%s.docx" % project)), str(target))
        return "样张已生成（内置样例正文）：%s\n      打开 Word 目视排版；如需暗标条款样式请用 tech-export --bid-mode。" % target
    finally:
        tmp.cleanup()


def cmd_tech_layout(args):
    if getattr(args, "apply_combo", ""):
        return apply_combo(args)
    if getattr(args, "preview", ""):
        print(_render_preview(args, args.preview))
        return 0
    path = find_presets(args)
    doc = load_presets(args)
    fallback = doc is None
    default = default_entry(doc)

    if getattr(args, "json", False):
        print(json.dumps({
            "source": str(path) if path else "",
            "fallback": fallback,
            "default": default,
            "groups": {g: entries(doc, g) for g, _ in GROUPS},
        }, ensure_ascii=False, indent=2))
        return 0

    if fallback:
        print("⚠ 未找到共享级排版预设（%s），已回退内置清单" % PRESETS_FILE)
    else:
        print("排版预设 · %s" % path)
    print("默认：%s %s / %s %s / %s %s / %s %s / 图文 %s(%s)：%s + %s + %s / 微观 %s(%s) %s(%s) %s(%s) %s(%s) %s(%s) %s(%s) / 页眉页脚 %s(%s)" % (
        default["preset"], _name(doc, "preset", default["preset"]),
        default["palette"], _name(doc, "palette", default["palette"]),
        default["cover"], _name(doc, "cover", default["cover"]),
        default["decoration"], _name(doc, "decoration", default["decoration"]),
        default.get("font", "gov-gongwen"), _name(doc, "font", default.get("font", "gov-gongwen")),
        _name(doc, "imageRatio", default.get("imageRatio", "mid")),
        _name(doc, "imageRule", default.get("imageRule", "hybrid")),
        _name(doc, "imageLayout", default.get("imageLayout", "split-h")),
        default.get("pageSetup", "p1-standard-a4"), _name(doc, "pageSetup", default.get("pageSetup", "p1-standard-a4")),
        default.get("headingSystem", "h1-gbt-arabic"), _name(doc, "headingSystem", default.get("headingSystem", "h1-gbt-arabic")),
        default.get("tocStyle", "t1-jianyu-auto"), _name(doc, "tocStyle", default.get("tocStyle", "t1-jianyu-auto")),
        default.get("tableStyle", "tb1-three-line"), _name(doc, "tableStyle", default.get("tableStyle", "tb1-three-line")),
        default.get("captionSystem", "c2-cy-chapter"), _name(doc, "captionSystem", default.get("captionSystem", "c2-cy-chapter")),
        default.get("paragraphStyle", "pa7-jianyu-15"), _name(doc, "paragraphStyle", default.get("paragraphStyle", "pa7-jianyu-15")),
        default.get("headerFooter", "hf1-classic-enterprise"), _name(doc, "headerFooter", default.get("headerFooter", "hf1-classic-enterprise"))))
    for group, label in GROUPS:
        _print_group(doc, group, label, default)
    print("\n提示：暗标禁用 cover=image-underlay；渐变蓝青在 docx 中以两段色块近似。")
    print("      章节树 layout 十五组 id 须在上表内（tech-outline 落盘前校验；暗标强制 font=dark-safe、图片二选一：none 或 dark-safe-img+appendix、页眉页脚二选一：hf9/hf10；微观六组按招标条款自动注入、不开放选择）。")
    return 0


# ---------------------------------------------------------------------------
# tech-layout --apply-combo：组合补丁 → 专家包（版面设计器「存组合」闭环）
# ---------------------------------------------------------------------------
def apply_combo(args):
    """组合补丁 json → 十五组 id 校验 → 生成专家包。

    补丁来源：`dev/prototypes/版面设计器-工作台V1.html` 「存组合」导出
    （m6.layout-designer/v1.x，含 layout 十五组 id；导出 JSON v1.1 同样兼容）。
    校验：每组 id 须在排版预设清单内（缺失键回退 preset `default`）；非法即报错。
    落盘：默认 **dry-run 不写**；`--confirm` 才在
    `<素材库根>/共享资源/技术标风格/专家包/<pack-id>/` 生成
    `包.json`（layoutCombo=组合）+ `taxonomy.json`（复制 official-tech 并改写 pack 字段）；
    写后经 `packs.load_pack` 全量回读（id/schema/taxonomy/layoutCombo/F11）——失败即报错。
    """
    import datetime
    from pathlib import Path

    from . import packs  # 函数内导入，避免模块加载期循环依赖（packs 依赖 layout）

    patch_path = Path(str(getattr(args, "apply_combo", "") or "").strip())
    if not patch_path.is_file():
        raise core.LibraryError("组合补丁不存在：%s" % patch_path)
    doc = load_presets(args)
    if doc is None:
        raise core.LibraryError("排版预设文件缺失，无法校验组合：共享资源/技术标风格/layout-presets.json 须就位")
    patch = core.read_json(str(patch_path), None)
    if not isinstance(patch, dict) or not isinstance(patch.get("layout"), dict):
        raise core.LibraryError("组合补丁缺少 layout（十五组 id）：%s（请由版面设计器「存组合」导出）" % patch_path)

    defaults = default_entry(doc)
    combo, bad = {}, []
    for g, label in GROUPS:
        vid = patch["layout"].get(g)
        if not (isinstance(vid, str) and vid.strip()):
            vid = defaults.get(g, "")
        vid = str(vid).strip()
        if not any(str(r.get("id")) == vid for r in entries(doc, g)):
            bad.append("%s=%s（不在预设清单）" % (label, vid))
        combo[g] = vid
    if bad:
        raise core.LibraryError("组合校验未通过：" + "；".join(bad))

    bid_mode = str(patch.get("bidMode") or "").strip() or \
        ("暗标" if (patch.get("dark") or combo.get("font") == "dark-safe") else "明标")
    name = str(patch.get("name") or "").strip() or "自定义组合"
    pack_id = str(getattr(args, "pack_id", "") or "").strip()
    if not pack_id:
        pack_id = "custom-%s-%s" % (combo["preset"], combo["palette"])
    if not re.match(r"^[A-Za-z0-9][A-Za-z0-9_-]*$", pack_id):
        raise core.LibraryError("专家包 id 非法（须为字母数字开头，含 -/_）：%r" % pack_id)

    root = sources.lib_root(args)
    pack_base = root / "共享资源" / "技术标风格" / "专家包"
    pdir = pack_base / pack_id
    if pdir.is_dir():
        raise core.LibraryError("专家包已存在：%s（换 --pack-id，或人工确认后处理既有包）" % pdir)

    print("组合补丁：%s（%s）" % (patch_path, bid_mode))
    print("组合名称：%s → 专家包 id：%s" % (name, pack_id))
    for g, label in GROUPS:
        print("  %-10s %s" % (label, combo[g]))
    if not getattr(args, "confirm", False):
        print("\n[DRY-RUN] 未写盘。确认后执行：tech-layout --apply-combo <json> --pack-id %s --confirm" % pack_id)
        return 0

    tax_src = pack_base / "official-tech" / packs.TAXONOMY_FILE
    if not tax_src.is_file():
        raise core.LibraryError("模板 taxonomy 缺失（无法生成专家包）：%s" % tax_src)
    try:
        tax = json.loads(tax_src.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise core.LibraryError("模板 taxonomy 无法解析：%s（%s）" % (tax_src, e))

    manifest = {
        "schema": packs.PACK_SCHEMA,
        "id": pack_id,
        "name": name,
        "description": "由版面设计器「存组合」导出（%s）；layoutCombo 十五组 id 已校验（F11）。" % bid_mode,
        "tags": ["custom"],
        "bidType": [],
        "docType": "ENGINEERING",
        "taxonomy": packs.TAXONOMY_FILE,
        "layoutCombo": combo,
        "source": {"kind": "layout-designer", "patch": str(patch_path),
                   "capturedAt": datetime.date.today().isoformat()},
    }
    pdir.mkdir(parents=True, exist_ok=True)
    try:
        (pdir / packs.MANIFEST_FILE).write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        tax["pack"] = pack_id
        (pdir / packs.TAXONOMY_FILE).write_text(json.dumps(tax, ensure_ascii=False, indent=2), encoding="utf-8")
        packs.load_pack(args, pack_id)   # 写后回读：缺/非法即报错（fail fast）
    except BaseException:
        # 写失败不留下半成品：删除刚创建的包目录
        import shutil
        if pdir.is_dir():
            shutil.rmtree(str(pdir))
        raise
    print("\n已生成专家包：%s（写后回读通过）" % pdir)
    print("使用：tech-init ... --expert-pack %s（tech-outline 落盘 layout 十五组即套用）" % pack_id)
    print("预览：tech-layout --preview <preset> 可对照正文版式；色值见 色卡预览.html")
    return 0
