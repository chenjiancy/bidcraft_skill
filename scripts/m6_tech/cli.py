# -*- coding: utf-8 -*-
"""
bidcraft · M6 技术标制作 —— CLI 首批（T5，契约 §7）

本批 7 条命令：
  tech-init     建目录 + 校验 M4 就绪 + 抽取约束 → 技术标/设置.json
  tech-outline  F1 校验草案 → F3 覆盖矩阵 → 回填系统字段 → F2 落盘（--confirm 记闸门①）
  tech-ctx      闸门①未确认拒绝；逐章生成 m6.ctx/v1 → .meta → CONTEXT_READY
  tech-status   写作状态表（状态/预算字数/实际字数/估算页）
  tech-parse    正文校验 → 自述块拆出 → 落盘回读 → WRITTEN
  tech-check    通道A 六项检查 → 覆盖矩阵 json/md；通过 → CHECKED
  tech-report   闸门② HTML 报告；--confirm 记 confirmLog → CONFIRMED
  tech-layout   列出排版预设（T13；--preview 样张依赖 T10）

其余命令（tech-export/rewrite/diff）不在本批注册。

拆分（500 行红线）：
  sources.py  M4 读取 / 设置推导 / 路径硬校验
  ctxpack.py  上下文包组装（m6.ctx/v1）
  layout.py   排版预设读取与 tech-layout（T13）
"""
import json
import math

from _shared import core
from m8_eval import eval_std

from . import rules as m6rules
from . import store
from . import sources
from . import layout
from . import export
from . import packs
from . import tpl_design
from . import partlib
from .ctxpack import build_context, fill_score_items
from .report import cmd_tech_check, cmd_tech_report
from .writer import cmd_tech_parse
from .rewrite import cmd_tech_rewrite
from .diff import cmd_tech_diff


def _print_json(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------------------
# tech-init
# ---------------------------------------------------------------------------
def cmd_tech_init(args):
    ent = sources.get_ent(args)
    proj = sources.proj_dir(ent, args.project)
    tdir = sources.tdir(args, proj)
    points = sources.load_points(tdir, args.project)      # 缺 scoring 在此硬失败
    sources.scoring_items(points)
    tech = store.ensure_tech_dir(ent, args.project)

    settings = sources.build_settings(args.project, points, tdir,
                                      bid_mode=getattr(args, "bid_mode", None),
                                      pages=getattr(args, "pages", None))
    presets_doc = layout.load_presets(args)
    if presets_doc is not None:
        settings["layout"] = layout.default_entry(presets_doc)
        if settings["bidMode"] == "暗标":
            for k, v in sources.DARK_LAYOUT_INJECT.items():
                settings["layout"][k] = v
            settings["notes"].append("暗标：排版预设默认被暗标条款覆盖（字体/图文/微观六组/页眉页脚），具体以招标原文为准")
    tree_exists = store.tree_path(tech).is_file()
    if tree_exists:
        settings["notes"].append("已存在章节树，设置.json 未覆写（章节树为权威）")
    else:
        store.write_json_inside(tech, sources.SETTINGS_FILE, settings)

    if getattr(args, "json", False):
        _print_json(settings)
        return 0
    print("技术标目录已就绪：%s" % tech)
    print("  bidMode：%s" % settings["bidMode"])
    pc = settings["pageConstraint"]
    print("  页数约束：不超过 %d 页（来源：%s）" % (pc["max"], pc["source"]))
    print("  拟派人员：%d 人（来源：素材清单）" % len(settings["personnel"]))
    print("  风格：%s %s；排版：%s/%s/%s/%s；字体：%s；图文：%s+%s+%s；微观：%s/%s/%s/%s/%s/%s" % (
        settings["style"]["id"], settings["style"]["name"],
        settings["layout"]["preset"], settings["layout"]["palette"],
        settings["layout"]["cover"], settings["layout"]["decoration"],
        settings["layout"].get("font", "gov-gongwen"),
        settings["layout"].get("imageRatio", "mid"),
        settings["layout"].get("imageRule", "hybrid"),
        settings["layout"].get("imageLayout", "split-h"),
        settings["layout"].get("pageSetup", "p1-standard-a4"),
        settings["layout"].get("headingSystem", "h1-gbt-arabic"),
        settings["layout"].get("tocStyle", "t1-jianyu-auto"),
        settings["layout"].get("tableStyle", "tb1-three-line"),
        settings["layout"].get("captionSystem", "c2-cy-chapter"),
        settings["layout"].get("paragraphStyle", "pa7-jianyu-15")))
    for n in settings["notes"]:
        print("  ⚠ %s" % n)
    print("下一步：agent 按 P2 产出章节树草案 → tech-outline")
    return 0


# ---------------------------------------------------------------------------
# tech-outline
# ---------------------------------------------------------------------------
def _assemble_tree(project, draft, settings):
    pc = dict(settings.get("pageConstraint") or {})
    chapters = []
    total = 0
    for ch in draft["chapters"]:
        cid = ch["id"]
        total += ch["wordCnt"]
        chapters.append({
            "id": cid, "no": ch["no"], "title": ch["title"].strip(),
            "level": ch["level"],
            "scoreRefs": ch["scoreRefs"],
            "keyPoints": [k.strip() for k in ch["keyPoints"]],
            "wordCnt": ch["wordCnt"],
            "dependsOnMaterials": ch.get("dependsOnMaterials") or [],
            "status": "PENDING",
            "files": {"body": "章节/%s.md" % cid, "meta": "章节/.meta/%s.json" % cid},
        })
    cpp = int(pc.get("charsPerPage") or sources.DEFAULT_CHARS_PER_PAGE)
    return {
        "schema": m6rules.SCHEMA_ID,
        "project": project,
        "bidMode": settings["bidMode"],
        "pageConstraint": {
            "max": int(pc["max"]),
            "estimate": int(math.ceil(total / float(cpp))) if total else 0,
            "charsPerPage": cpp,
            "source": str(pc.get("source") or ""),
        },
        "style": dict(settings["style"]),
        "layout": dict(settings["layout"]),
        "terminology": dict(settings["terminology"]),
        "personnel": list(settings.get("personnel") or []),
        "chapters": chapters,
    }


def _issue_text(issues):
    return "\n".join("[%s] %s" % (i["code"], i["message"]) for i in issues)


def cmd_tech_outline(args):
    ent = sources.get_ent(args)
    proj = sources.proj_dir(ent, args.project)
    tech = sources.tech_dir(ent, args.project)
    tdir = sources.tdir(args, proj)
    points = sources.load_points(tdir, args.project)
    raw_items = sources.scoring_items(points)

    pack = None
    if getattr(args, "expert_pack", ""):
        pack = packs.load_pack(args, args.expert_pack)   # 缺失/非法即报错（不静默兜底）

    draft_path = sources.ensure_inside("章节树草案", args.file, proj)
    draft = core.read_json(str(draft_path), None)
    if not isinstance(draft, dict):
        raise core.LibraryError("章节树草案无法读取或不是 JSON 对象：%s" % draft_path)

    ok, issues = m6rules.validate_chapters_draft(draft, raw_items)
    if not ok:
        raise core.LibraryError("章节树草案校验失败，未落盘：\n%s" % _issue_text(issues))

    existing = store.read_tree(tech) if store.tree_path(tech).is_file() else None
    if existing and store.outline_confirmed(existing):
        raise core.LibraryError("章节树已确认（闸门①已过），拒绝覆盖；如需重编请先人工归档")

    settings = sources.read_settings(tech, args.project)
    if settings is None:
        settings = sources.build_settings(args.project, points, tdir)
    tree = _assemble_tree(args.project, draft, settings)
    if pack is not None:
        tree["expertPack"] = packs.tree_entry(pack["manifest"])
        # 专家包 layoutCombo → 落盘 layout（版式组合随包切换；暗标时暗标注入覆盖微观组/页眉页脚，纪律不变）
        combo = pack["manifest"].get("layoutCombo")
        if isinstance(combo, dict) and combo:
            tree["layout"] = dict(combo)
            if tree.get("bidMode") == "暗标":
                for k, v in sources.DARK_LAYOUT_INJECT.items():
                    tree["layout"][k] = v

    parsed = [eval_std.parse_score_item(it, i) for i, it in enumerate(raw_items)]
    coverage = m6rules.build_coverage(parsed, tree["chapters"])
    pages = m6rules.judge_pages(tree["pageConstraint"]["estimate"], tree["pageConstraint"])
    blockers = []
    if not coverage["ok"]:
        blockers.append("评分点未覆盖 idx：%s" % ", ".join(str(i) for i in coverage["missing"]))
    if pages and pages.get("level") == "error":
        blockers.append(pages["message"])
    if getattr(args, "confirm", False) and blockers:
        raise core.LibraryError("拒绝确认闸门①：\n%s" % "\n".join(blockers))

    presets = layout.load_presets(args)
    store.write_tree(tech, tree, presets)
    if getattr(args, "confirm", False):
        store.confirm_gate(tech, "outline", note="tech-outline --confirm", presets=presets)

    if getattr(args, "json", False):
        _print_json({"tree": tree, "coverage": coverage, "issues": issues,
                     "confirm": bool(getattr(args, "confirm", False)),
                     "pageIssue": pages})
    else:
        pc = tree["pageConstraint"]
        print("章节树已落盘：%s" % store.tree_path(tech))
        print("  %d 章，预算 %d 字 ≈ %d 页 / 上限 %d 页" % (
            len(tree["chapters"]), sum(c["wordCnt"] for c in tree["chapters"]),
            pc["estimate"], pc["max"]))
        if pack is not None:
            print("  专家包 %s「%s」已绑定（taxonomy %d 类可作兜底骨架，tech-ctx 时注入）"
                  % (pack["manifest"]["id"], pack["manifest"].get("name") or "",
                     len(pack["taxonomy"]["classes"])))
            for n in pack["notes"]:
                print("  ⚠ %s" % n)
        for w in issues:
            print("  ⚠ [%s] %s" % (w["code"], w["message"]))
        if coverage["missing"]:
            print("  ✗ 未覆盖评分项 idx：%s" % ", ".join(str(i) for i in coverage["missing"]))
        if coverage["weak"]:
            print("  ⚠ 弱覆盖评分项 idx：%s" % ", ".join(str(i) for i in coverage["weak"]))
        if pages:
            print("  %s %s" % ("✗" if pages["level"] == "error" else "⚠", pages["message"]))
        print("  闸门①：%s" % ("已确认（confirmLog 已记录）"
                              if getattr(args, "confirm", False)
                              else "未确认（--confirm 后 tech-ctx 才可用）"))
    return 0 if coverage["ok"] else 1


# ---------------------------------------------------------------------------
# tech-ctx
# ---------------------------------------------------------------------------
def cmd_tech_ctx(args):
    ent = sources.get_ent(args)
    proj = sources.proj_dir(ent, args.project)
    tech = sources.tech_dir(ent, args.project)
    tree = store.read_tree(tech)
    if not store.outline_confirmed(tree):
        raise core.LibraryError("闸门①未确认：章节树需先 tech-outline --confirm，禁止 tech-ctx")
    if getattr(args, "all", False):
        chapters = store.list_chapters(tree)
    elif args.chapter:
        chapters = [store.find_chapter(tree, args.chapter)]
    else:
        raise core.LibraryError("请指定 --chapter ch-01 或 --all")

    tdir = sources.tdir(args, proj)
    points = sources.load_points(tdir, args.project)
    raw_items = sources.scoring_items(points)
    material = sources.load_material(tdir, args.project) or {}

    rows, skipped = [], []
    presets = layout.load_presets(args)
    ep = tree.get("expertPack") or None
    ep_data = packs.load_pack(args, ep["id"]) if ep else None   # 包被删/非法即报错（不静默兜底）
    matched, unmatched = 0, []
    for ch in chapters:
        if ch.get("status") == "CONFIRMED":
            skipped.append({"id": ch.get("id"), "reason": "CONFIRMED 章不再重建上下文包"})
            continue
        ctx = fill_score_items(build_context(tree, ch, material, args, points), raw_items)
        if ep_data is not None and packs.attach_context(ctx, ep_data["manifest"], ep_data["taxonomy"], ch):
            matched += 1
        else:
            unmatched.append(ch.get("title") or ch.get("id"))
        store.write_context_pack(tech, ch["id"], ctx)
        cur = ch.get("status") or "PENDING"
        advanced = cur in ("PENDING", "FAILED")
        if advanced:
            store.advance_chapter(tech, ch["id"], "CONTEXT_READY", presets)
        rows.append({"id": ch["id"], "status": "CONTEXT_READY" if advanced else cur,
                     "pack": "章节/.meta/%s.json" % ch["id"], "advanced": advanced})

    if getattr(args, "json", False):
        _print_json({"project": args.project, "chapters": rows, "skipped": skipped,
                     "expertPack": ({"id": ep["id"], "matched": matched, "unmatched": unmatched}
                                    if ep_data is not None else None)})
    else:
        for r in rows:
            print("%s 上下文包已生成（%s）%s" % (
                r["id"], r["status"], " → CONTEXT_READY" if r["advanced"] else ""))
        for s in skipped:
            print("  ⚠ %s 跳过：%s" % (s["id"], s["reason"]))
        if ep_data is not None:
            print("  专家包 %s「%s」：%d/%d 章命中 taxonomy 类目（description 已注入 .meta）"
                  % (ep["id"], ep.get("name") or "", matched, len(rows)))
            for t in unmatched:
                print("  ⚠ 未命中 taxonomy 类目（仅兜底骨架来源，不阻断）：%s" % t)
            for n in ep_data["notes"]:
                print("  ⚠ %s" % n)
        print("下一步：agent 按 P3 逐章写作 → tech-parse（下一批命令）")
    return 0


# ---------------------------------------------------------------------------
# tech-status
# ---------------------------------------------------------------------------
def cmd_tech_status(args):
    ent = sources.get_ent(args)
    sources.proj_dir(ent, args.project)
    tech = sources.tech_dir(ent, args.project)
    tree = store.read_tree(tech)
    pc = tree.get("pageConstraint") or {}
    cpp = int(pc.get("charsPerPage") or sources.DEFAULT_CHARS_PER_PAGE)
    rows, total_pages = [], 0
    for ch in store.list_chapters(tree):
        actual, pages, body_ok = 0, 0, False
        try:
            text = store.read_chapter_body(tech, ch)
            counts = m6rules.count_chars(text)
            actual = counts["body_chars"] + counts["table_chars"]
            pages = m6rules.estimate_pages(counts["body_chars"], counts["table_chars"],
                                           {"charsPerPage": cpp})["pages"]
            body_ok = True
        except core.LibraryError:
            pass
        total_pages += pages
        rows.append({"id": ch.get("id"), "no": ch.get("no"), "title": ch.get("title"),
                     "status": ch.get("status"), "wordCnt": ch.get("wordCnt"),
                     "actualChars": actual if body_ok else None,
                     "pages": pages if body_ok else None})
    summary = {"chapters": len(rows), "estimatedPages": total_pages,
               "maxPages": pc.get("max"),
               "overPages": bool(pc.get("max") and total_pages > pc["max"]),
               "confirmed": store.outline_confirmed(tree)}
    if getattr(args, "json", False):
        _print_json({"project": args.project, "bidMode": tree.get("bidMode"),
                     "summary": summary, "chapters": rows})
        return 0
    print("技术标状态 · %s（%s）" % (args.project, tree.get("bidMode")))
    print("  %-8s %-6s %-12s %-14s %8s %8s %6s" %
          ("id", "no", "状态", "标题", "预算字数", "实际字数", "估算页"))
    for r in rows:
        print("  %-8s %-6s %-12s %-14s %8s %8s %6s" % (
            r["id"], r["no"], r["status"], (r["title"] or "")[:14],
            r["wordCnt"], "-" if r["actualChars"] is None else r["actualChars"],
            "-" if r["pages"] is None else r["pages"]))
    print("  合计估算 %d 页 / 上限 %s 页%s" % (
        total_pages, pc.get("max"), "（超限）" if summary["overPages"] else ""))
    print("  闸门①：%s" % ("已确认" if summary["confirmed"] else "未确认"))
    return 0


# ---------------------------------------------------------------------------
# 注册
# ---------------------------------------------------------------------------
def register_parser(sub):
    sp = sub.add_parser("tech-init", help="M6：建技术标目录骨架 + 校验 M4 产物 + 抽取页数/暗标并落设置")
    sp.add_argument("--project", required=True, help="项目名（项目级/<项目>）")
    sp.add_argument("--tdir", default="", help="招标解析目录（默认 项目级/<项目>/招标解析）")
    sp.add_argument("--bid-mode", choices=m6rules.BID_MODES, default=None,
                    help="标书模式（默认按投标要点文本含「暗标」判定）")
    sp.add_argument("--pages", type=int, default=None, help="页数上限覆盖（默认从招标文件抽取）")
    sp.set_defaults(func=cmd_tech_init)

    sp = sub.add_parser("tech-outline", help="M6：校验 agent 章节树草案 → 回填系统字段 → 覆盖矩阵 → 落盘")
    sp.add_argument("--project", required=True, help="项目名（项目级/<项目>）")
    sp.add_argument("--file", required=True, help="章节树草案 JSON（须位于本项目目录内）")
    sp.add_argument("--tdir", default="", help="招标解析目录（默认 项目级/<项目>/招标解析）")
    sp.add_argument("--expert-pack", dest="expert_pack", default="",
                    help="绑定专家包 id（共享级 共享资源/技术标风格/专家包/<id>/；"
                         "其 taxonomy 作 P2-R3 兜底骨架来源，tech-ctx 时注入类目要点）")
    sp.add_argument("--confirm", action="store_true", help="确认闸门①（存在未覆盖/页数超限则拒绝）")
    sp.set_defaults(func=cmd_tech_outline)

    sp = sub.add_parser("tech-ctx", help="M6：逐章生成 m6.ctx/v1 上下文包（闸门①未确认拒绝）")
    sp.add_argument("--project", required=True, help="项目名（项目级/<项目>）")
    sp.add_argument("--tdir", default="", help="招标解析目录（默认 项目级/<项目>/招标解析）")
    sp.add_argument("--chapter", default="", help="单章 id（如 ch-01）")
    sp.add_argument("--all", action="store_true", help="全部章节（跳过 CONFIRMED）")
    sp.set_defaults(func=cmd_tech_ctx)

    sp = sub.add_parser("tech-status", help="M6：写作状态表（状态/预算字数/实际字数/估算页）")
    sp.add_argument("--project", required=True, help="项目名（项目级/<项目>）")
    sp.set_defaults(func=cmd_tech_status)

    sp = sub.add_parser("tech-parse", help="M6：正文校验（非空/字数/占位/敏感词）→ 自述块 → 落盘回读 → WRITTEN")
    sp.add_argument("--project", required=True, help="项目名（项目级/<项目>）")
    sp.add_argument("--chapter", required=True, help="章节 id（如 ch-01）")
    sp.add_argument("--file", required=True, help="agent 产出的章节 md（须位于本项目目录内）")
    sp.set_defaults(func=cmd_tech_parse)

    sp = sub.add_parser("tech-check", help="M6：通道A 六项检查（覆盖/结构/篇幅/敏感词/一致性/占位）")
    sp.add_argument("--project", required=True, help="项目名（项目级/<项目>）")
    sp.add_argument("--tdir", default="", help="招标解析目录（默认 项目级/<项目>/招标解析）")
    sp.add_argument("--chapter", default="", help="只判定并推进单章（默认全量）")
    sp.set_defaults(func=cmd_tech_check)

    sp = sub.add_parser("tech-report", help="M6：闸门② HTML 检查报告；--confirm 记 confirmLog → CONFIRMED")
    sp.add_argument("--project", required=True, help="项目名（项目级/<项目>）")
    sp.add_argument("--confirm", action="store_true", help="确认闸门②（有 error 时需 --force）")
    sp.add_argument("--force", action="store_true", help="存在 error 仍确认（记入备注）")
    sp.add_argument("--note", default="", help="闸门②确认备注（写入 confirmLog）")
    sp.set_defaults(func=cmd_tech_report)

    sp = sub.add_parser("tech-layout", help="M6：列出排版预设（版面/配色/封面/装饰）；--preview 调 T10 直出样张 docx")
    sp.add_argument("--list", action="store_true", help="列出全部预设（默认行为）")
    sp.add_argument("--preview", default="", help="用 T10 导出引擎生成样张 docx（无 --project 时用内置样例正文）")
    sp.add_argument("--project", default="", help="指定项目（--preview 走真实项目导出）")
    sp.add_argument("--enterprise", default="", help="企业名（--preview 真实项目时必填）")
    sp.add_argument("--apply-combo", default="", help="应用组合补丁 json → 生成专家包（版面设计器「存组合」闭环；默认 dry-run 不写盘）")
    sp.add_argument("--pack-id", default="", help="新专家包 id（默认 custom-<preset>-<palette>）")
    sp.add_argument("--confirm", action="store_true", help="配合 --apply-combo：确认落盘（写后回读校验）")
    sp.set_defaults(func=layout.cmd_tech_layout)

    sp = sub.add_parser("tech-rewrite", help="M6·T11 精修回路：修订稿校验（非空/字数/占位/敏感词）→ M6-REVISE 变更块 → 行级 diff 披露 → 旧稿 .rewrite-trash 备份 → 回写回读 → WRITTEN")
    sp.add_argument("--project", required=True, help="项目名（项目级/<项目>）")
    sp.add_argument("--chapter", required=True, help="章节 id（如 ch-01）")
    sp.add_argument("--file", required=True, help="agent 精修产出的章节 md（须位于本项目目录内）")
    sp.set_defaults(func=cmd_tech_rewrite)

    sp = sub.add_parser("tech-diff", help="M6·T12 双通道差异比对：tech-check 机器结论 vs agent 自述（M6-COVERAGE）→ 四类差异落盘；--verdict <json> --confirm 逐项裁决写 confirmLog（V12 不静默）")
    sp.add_argument("--project", required=True, help="项目名（项目级/<项目>）")
    sp.add_argument("--verdict", default="", help="逐项裁决 JSON（{\"diffs\":[{\"idx\":0,\"verdict\":\"accept|reject|note\",\"note\":\"\"}]}，须位于本项目目录内）")
    sp.add_argument("--confirm", action="store_true", help="配合 --verdict：确认裁决并写入 confirmLog（gate=diff）")
    sp.set_defaults(func=cmd_tech_diff)

    sp = sub.add_parser("tpl-design",
                        help="M6·模板设计器（P0）：模板描述文件（template.json，schema m6.template/v1）校验/落盘/样张；"
                             "描述层=文档结构编排+样式引用+占位符绑定，docx 只是渲染产物")
    sp.add_argument("--list", action="store_true", help="列出模板目录模板与校验状态（默认行为）")
    sp.add_argument("--show", default="", help="展示模板概览 + 校验结果 + 暗标派生（文件路径或模板目录内文件名）")
    sp.add_argument("--validate", default="", help="只校验并输出问题清单（--json 输出结构化）")
    sp.add_argument("--apply", default="", help="校验通过后落盘登记模板到 模板/ 目录（需 --confirm；已在目录内则登记回读）")
    sp.add_argument("--specimen", default="", help="按模板样式引用生成样张 docx（P0 以版面范式 preset 驱动，其余组样式见 --show；P1 全映射）")
    sp.add_argument("--project", default="", help="配合 --specimen：走真实项目导出（否则内置样例正文）")
    sp.add_argument("--fill", default="", help="配合 --specimen：占位符填充 'key=值;key2=值2'（enterprise_name/project_name/bid_date 缺省自动注入）")
    sp.add_argument("--confirm", action="store_true", help="配合 --apply：确认落盘（写后回读校验）")
    sp.set_defaults(func=tpl_design.cmd_tpl_design)

    sp = sub.add_parser("tpl-part",
                        help="M6·模板部件库（P2）：docx 母版拆解回流——识别封面/目录/正文样式/结尾 → 部件 JSON（schema m6.part/v1），模板 structure 用 partRef 引用")
    sp.add_argument("--list", action="store_true", help="列出部件库（默认行为）")
    sp.add_argument("--scan", default="", help="拆解 docx 母版 → 部件描述（dry-run 预览；--confirm 落盘部件库，防覆盖）")
    sp.add_argument("--show", default="", help="展示部件内容（部件名或部件文件名）")
    sp.add_argument("--project", default="", help="配合 --scan：参数化项目名（匹配文本替换为 {{ project_name }}）")
    sp.add_argument("--confirm", action="store_true", help="配合 --scan：确认落盘部件库（写后回读校验）")
    sp.set_defaults(func=partlib.cmd_tpl_part)

    export.add_sub(sub)
