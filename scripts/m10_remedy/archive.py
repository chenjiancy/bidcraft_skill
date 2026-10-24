# -*- coding: utf-8 -*-
"""
bidcraft · M10 T21 补救→M5 归档自动联动 —— CLI

命令：
  remedy-archive --project <项目> [--task <任务ID>|--all]
               生成归档申请单（素材补齐/证据核验 已完成任务 → 模拟评标/归档申请_<项目>.json/.md/.html）；
               人工确认闸门：申请单等待确认（--task 指定单个任务，--all 全量未申请任务，缺省=全部已完成素材类）。
  remedy-archive --project <项目> --apply --confirm
               确认应用申请单：按建议落点写入 招标解析/素材清单_<项目>.json（M5 归档入口），
               任务单对应任务标记 归档状态=已归档；生成 模拟评标/归档记录_<项目>.json/.md/.html。
               无 --confirm 拒绝应用（人工确认闸门）。

产物：项目级/<项目>/模拟评标/归档申请_<项目>.json/.md/.html + 归档记录_<项目>.json/.md/.html
"""
from pathlib import Path

from _shared import core

from . import remedy

OUT_DIR_NAME = "模拟评标"


def _proj_dir(root, enterprise, project):
    pd = Path(root) / enterprise / "项目级" / project
    if not pd.is_dir():
        raise core.LibraryError("项目目录不存在：%s" % pd)
    return pd


def _task_doc(out_dir, project):
    p = out_dir / ("失分补救任务单_%s.json" % project)
    if not p.is_file():
        raise core.LibraryError("任务单不存在：%s（先执行 remedy-gen）" % p)
    doc = core.read_json(str(p), None)
    if not doc:
        raise core.LibraryError("任务单无法读取：%s" % p)
    return p, doc


def _mat_doc(proj_dir, project):
    p = proj_dir / "招标解析" / ("素材清单_%s.json" % project)
    if not p.is_file():
        raise core.LibraryError("素材清单不存在：%s（先完成 M4 招标解析/素材清单）" % p)
    doc = core.read_json(str(p), None)
    if not doc:
        raise core.LibraryError("素材清单无法读取：%s" % p)
    return p, doc


def _archive_doc(out_dir, project):
    p = out_dir / ("归档申请_%s.json" % project)
    if not p.is_file():
        raise core.LibraryError("归档申请单不存在：%s（先执行 remedy-archive）" % p)
    doc = core.read_json(str(p), None)
    if not doc:
        raise core.LibraryError("归档申请单无法读取：%s" % p)
    return p, doc


def _esc(s):
    if s is None:
        return ""
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _write(path, doc):
    core.write_json(str(path), doc)
    back = core.read_json(str(path), None)
    if not back:
        raise core.LibraryError("写后回读失败：%s" % path)


def cmd_remedy_archive(args):
    root = Path(args.root)
    proj_dir = _proj_dir(root, args.enterprise, args.project)
    out_dir = proj_dir / OUT_DIR_NAME
    tpath, tdoc = _task_doc(out_dir, args.project)

    apath, adoc = None, None
    if out_dir.joinpath("归档申请_%s.json" % args.project).is_file():
        apath, adoc = _archive_doc(out_dir, args.project)

    if args.apply:
        return _cmd_apply(args, proj_dir, out_dir, tpath, tdoc, apath, adoc)

    # —— 生成归档申请单 ——
    # 去重：申请单已收录的任务（无论待确认/已应用）不重复生成
    known = [e["任务ID"] for e in (adoc or {}).get("entries") or []]
    entries = remedy.gen_archive_entries(tdoc, known_task_ids=known)
    if args.task:
        entries = [e for e in entries if e["任务ID"] == args.task]
    if not entries:
        raise core.LibraryError("任务单中无符合归档条件的已完成素材任务"
                                "（类型=素材补齐/证据核验 且 完成状态=已完成%s）" %
                                ("，指定任务 %s 不在此列" % args.task if args.task else ""))

    if adoc is None:
        adoc = {"project": args.project, "生成依据": "M10 补救→M5 归档联动：已完成素材补齐/证据核验任务生成归档申请",
                "entries": []}
    for e in entries:
        adoc["entries"].append(e)
    adoc["生成依据"] = "%s（现有 %d 条）" % (adoc["生成依据"], len(adoc["entries"]))
    _write(apath or out_dir / ("归档申请_%s.json" % args.project), adoc)

    base = "归档申请_%s" % args.project
    json_path = out_dir / ("%s.json" % base)
    md_path = out_dir / ("%s.md" % base)
    html_path = out_dir / ("%s.html" % base)
    core.write_json(str(json_path), adoc)
    md_path.write_text(_to_md(adoc, "apply"), encoding="utf-8")
    _render_html(args.project, adoc, "apply", html_path)
    back = core.read_json(str(json_path), None)
    if not back:
        raise core.LibraryError("归档申请单 JSON 写后回读失败：%s" % json_path)
    if not md_path.exists() or not html_path.exists():
        raise core.LibraryError("归档申请单落盘不完整（json/md/html）")

    print("归档申请单已生成：%s" % json_path)
    print("HTML：%s（浏览器打开，人工确认闸门）" % html_path)
    for e in entries:
        print("- %s｜%s｜%s｜→ %s（待确认）" % (e["任务ID"], e["动作"], e["素材名"], e["建议落点"]))
    print("下一步：人工确认素材名/路径后执行 remedy-archive --project %s --apply --confirm 应用归档" % args.project)


def _cmd_apply(args, proj_dir, out_dir, tpath, tdoc, apath, adoc):
    if not args.confirm:
        raise core.LibraryError("应用归档申请须人工确认闸门：remedy-archive --apply --confirm（当前缺少 --confirm，未执行任何写入）")
    if adoc is None:
        raise core.LibraryError("归档申请单不存在：先执行 remedy-archive 生成申请单")

    pending = [e for e in adoc.get("entries") or [] if e.get("状态") not in ("已应用", "已跳过")]
    if not pending:
        raise core.LibraryError("归档申请单已全部应用（无可应用条目）")
    if args.task:
        pending = [e for e in pending if e["任务ID"] == args.task]
        if not pending:
            raise core.LibraryError("指定任务 %s 不在待应用条目中" % args.task)

    mpath, mdoc = _mat_doc(proj_dir, args.project)
    mdoc, applied, skipped = remedy.apply_archive(mdoc, pending)
    _write(mpath, mdoc)

    # 任务单标记 归档状态
    now = __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M")
    for e in pending:
        for t in tdoc.get("tasks") or []:
            if t.get("id") == e["任务ID"]:
                t["归档状态"] = "已归档"
                t["归档时间"] = now
    _write(tpath, tdoc)

    # 申请单条目状态
    applied_ids = {a["任务ID"] for a in applied}
    for e in adoc["entries"]:
        if e["任务ID"] in applied_ids:
            e["状态"] = "已应用"
            e["应用时间"] = now
        elif any(s.get("任务ID") == e["任务ID"] for s in skipped):
            e["状态"] = "已跳过"
            e["应用时间"] = now
    apath = apath or out_dir / ("归档申请_%s.json" % args.project)
    _write(apath, adoc)

    # 归档记录
    rec = {"project": args.project, "生成依据": "M10 补救→M5 归档联动：归档申请应用记录（人工确认闸门）",
           "应用时间": now, "applied": applied, "skipped": skipped,
           "素材清单": str(mpath), "任务单": str(tpath)}
    base = "归档记录_%s" % args.project
    json_path = out_dir / ("%s.json" % base)
    md_path = out_dir / ("%s.md" % base)
    html_path = out_dir / ("%s.html" % base)
    core.write_json(str(json_path), rec)
    md_path.write_text(_to_md(rec, "record"), encoding="utf-8")
    _render_html(args.project, rec, "record", html_path)
    back = core.read_json(str(json_path), None)
    if not back or back.get("project") != args.project:
        raise core.LibraryError("归档记录写后回读失败：%s" % json_path)
    if not md_path.exists() or not html_path.exists():
        raise core.LibraryError("归档记录落盘不完整（json/md/html）")

    print("归档应用完成（人工确认闸门通过）")
    for a in applied:
        print("- %s｜%s｜已写入 素材清单.%s（%s）" % (a["任务ID"], a["类别"], a["落点"], a["素材名"]))
    for s in skipped:
        print("- %s｜%s｜跳过：%s" % (s["任务ID"], s["类别"], s.get("结果")))
    print("素材清单：%s" % mpath)
    print("归档记录：%s" % json_path)
    print("下一步：remedy-recheck 重检（新素材进入重检比对）→ m9-evidence 留痕包索引归档记录")


def _to_md(doc, kind):
    lines = ["# %s · %s" % ("归档申请单" if kind == "apply" else "归档记录", doc.get("project", "")), "",
             "> %s" % doc.get("生成依据", ""), ""]
    if kind == "apply":
        lines += ["## 待确认归档条目（人工确认闸门）", "| 任务ID | 动作 | 类别 | 素材名 | 建议落点 | 状态 |", "|---|---|---|---|---|---|"]
        for e in doc.get("entries", []):
            lines.append("| %s | %s | %s | %s | %s | %s |" % (
                e.get("任务ID"), e.get("动作"), e.get("类别"), e.get("素材名"),
                e.get("建议落点"), e.get("状态")))
        lines.append("")
        lines.append("> 人工确认闸门：确认素材名与路径后执行 `remedy-archive --project <项目> --apply --confirm` 应用归档；")
        lines.append("  未确认不写入素材清单；应用后素材以「待归档」标记，真实扫描件路径由人工/M1 素材库归档流程补充。")
    else:
        lines += ["应用时间：%s" % doc.get("应用时间", ""), "",
                  "## 已应用", "| 任务ID | 类别 | 素材名 | 落点 |", "|---|---|---|---|"]
        for a in doc.get("applied", []):
            lines.append("| %s | %s | %s | %s |" % (a["任务ID"], a["类别"], a["素材名"], a["落点"]))
        if doc.get("skipped"):
            lines += ["", "## 已跳过（去重）", "| 任务ID | 类别 | 素材名 | 结果 |", "|---|---|---|---|"]
            for s in doc.get("skipped", []):
                lines.append("| %s | %s | %s | %s |" % (s["任务ID"], s["类别"], s["素材名"], s.get("结果")))
    lines.append("")
    lines.append("> 人工确认闸门：归档为 M5 素材归档流程入口（素材清单 items/分键增条）；真实扫描件归档由 M1 素材库流程完成；最终以评标委员会评审为准。")
    return "\n".join(lines)


def _render_html(project, doc, kind, html_path):
    title = "归档申请单" if kind == "apply" else "归档记录"
    rows = []
    if kind == "apply":
        for e in doc.get("entries", []):
            rows.append("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
                e.get("任务ID"), _esc(e.get("动作")), e.get("类别"), _esc(e.get("素材名")),
                e.get("建议落点"), e.get("状态")))
        table = ("<table><tr style='background:#f1f3f4'><th>任务ID</th><th>动作</th><th>类别</th>"
                 "<th>素材名</th><th>建议落点</th><th>状态</th></tr>%s</table>" % "".join(rows))
        foot = "人工确认闸门：确认素材名与路径后执行 remedy-archive --project &lt;项目&gt; --apply --confirm 应用归档；未确认不写入素材清单。"
    else:
        rows = ["<tr style='background:#f1f3f4'><th>任务ID</th><th>类别</th><th>素材名</th><th>落点</th></tr>"]
        for a in doc.get("applied", []):
            rows.append("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
                a["任务ID"], a["类别"], _esc(a["素材名"]), a["落点"]))
        if doc.get("skipped"):
            rows.append("<tr style='background:#f1f3f4'><th>任务ID</th><th>类别</th><th>素材名</th><th>结果</th></tr>")
            for s in doc.get("skipped", []):
                rows.append("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
                    s["任务ID"], s["类别"], _esc(s["素材名"]), s.get("结果")))
        table = "<table>%s</table>" % "".join(rows)
        foot = "归档为 M5 素材归档流程入口；真实扫描件路径由人工/M1 素材库归档流程补充。"
    html = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>%s · %s</title>
<style>
 body{font-family:SimSun,serif;color:#222;margin:24px auto;max-width:920px;padding:0 16px}
 h1{font-size:20px;text-align:center;margin:8px 0}
 .meta{text-align:center;color:#666;font-size:13px;margin-bottom:14px}
 table{width:100%%;border-collapse:collapse;font-size:13px;margin-bottom:14px}
 th,td{border:1px solid #d0d7de;padding:6px 8px;text-align:left;vertical-align:top}
 .foot{margin-top:16px;font-size:12px;color:#666;border-top:1px solid #e1e4e8;padding-top:8px}
</style></head><body>
<h1>%s · %s</h1>
<div class="meta">%s</div>
%s
<div class="foot">%s</div>
</body></html>""" % (
        title, _esc(project), title, _esc(project), _esc(doc.get("生成依据", "")), table, foot)
    html_path.write_text(html, encoding="utf-8")


def register_parser(sub):
    sp = sub.add_parser("remedy-archive", help="M10 补救→M5 归档联动：已完成素材补齐/证据核验任务 → 归档申请单（模拟评标/归档申请_<项目>.json/.md/.html，人工确认闸门）；--apply --confirm 确认应用写入素材清单（招标解析/素材清单_<项目>.json）→ 归档记录")
    sp.add_argument("--project", required=True, help="项目名")
    sp.add_argument("--task", default="", help="指定任务 ID（缺省=全部符合条件的已完成素材任务）")
    sp.add_argument("--apply", action="store_true", help="应用归档申请（须配 --confirm）")
    sp.add_argument("--confirm", action="store_true", help="人工确认闸门：确认后执行写入")
    sp.set_defaults(func=cmd_remedy_archive)

    # T22：补救素材 → 企业素材库（M1）入库申请（跨项目复用）
    sp2 = sub.add_parser("assets-archive", help="T22 补救素材→企业素材库入库申请：已归档（归档状态=已归档）的素材补齐/证据核验任务 → 企业素材库入库申请单（企业级/素材库/收件箱/补救入库申请_<项目>_<时间戳>.json/.md/.html，M1 台账去重）；正式入库走 M1 现有 open-inbox/upload/propose/apply 人工确认链")
    sp2.add_argument("--project", required=True, help="项目名（项目级/<项目>，读取已归档任务）")
    sp2.add_argument("--task", default="", help="指定任务 ID（缺省=全部已归档素材任务）")
    sp2.set_defaults(func=cmd_assets_archive)


_M1_CATEGORY = {"业绩": "业绩", "人员": "人员", "荣誉": "荣誉", "体系认证": "资质"}


def _archived_entries(tdoc, task_id=""):
    """已归档（归档状态=已归档）且 涉及素材 非空 的任务 → 入库申请源条目。"""
    out = []
    for t in tdoc.get("tasks") or []:
        if t.get("归档状态") != "已归档":
            continue
        if task_id and t.get("id") != task_id:
            continue
        mat = t.get("涉及素材") or {}
        if not mat:
            continue
        out.append({
            "任务ID": t.get("id"), "动作": t.get("动作", ""),
            "类别": mat.get("category", ""), "素材名": mat.get("subtype") or mat.get("category") or "待归档素材",
            "来源": t.get("来源", ""),
        })
    return out


def cmd_assets_archive(args):
    """T22：已归档补救素材 → 企业素材库入库申请单（M1 台账去重 + 引导）。"""
    import datetime as _dt
    root = Path(args.root)
    ent_dir = core.Library(root).resolve(args.enterprise)
    lib = core.lib_root(ent_dir)
    proj_dir = _proj_dir(root, args.enterprise, args.project)
    out_dir = proj_dir / OUT_DIR_NAME
    _, tdoc = _task_doc(out_dir, args.project)

    entries = _archived_entries(tdoc, args.task)
    if not entries:
        raise core.LibraryError("任务单中无已归档（归档状态=已归档）的素材任务%s"
                                % ("（指定任务 %s 未归档）" % args.task if args.task else "（先执行 remedy-archive --apply --confirm）"))

    dedup = []
    for e in entries:
        cat = _M1_CATEGORY.get(e["类别"], "未分类")
        sub = e["素材名"]
        hits = core.query(ent_dir, category=cat, subtype="", keyword=sub)
        d = dict(e)
        d["企业类别"] = cat
        d["状态"] = "已在库（可复用，跳过入库）" if hits else "待入库"
        d["台账命中"] = [h.get("rel_path") for h in hits[:3]]
        dedup.append(d)
    ready = [d for d in dedup if d["状态"] == "待入库"]
    reuse = [d for d in dedup if d["状态"] != "待入库"]
    ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    base = "补救入库申请_%s_%s" % (args.project, ts)
    doc = {
        "project": args.project, "enterprise": args.enterprise,
        "生成依据": "T22 M10 补救→M1 企业素材库：已归档补救素材生成入库申请（台账去重 + 引导现有 M1 归档命令）",
        "生成时间": _dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "summary": {"申请条数": len(dedup), "待入库": len(ready), "已在库（可复用）": len(reuse)},
        "entries": dedup,
    }
    inbox_dir = lib / "收件箱"
    json_path = inbox_dir / ("%s.json" % base)
    md_path = inbox_dir / ("%s.md" % base)
    html_path = inbox_dir / ("%s.html" % base)
    core.write_json(str(json_path), doc)
    md_path.write_text(_to_md_assets(doc), encoding="utf-8")
    _render_assets_html(args.enterprise, doc, html_path)
    back = core.read_json(str(json_path), None)
    if not back or back.get("project") != args.project:
        raise core.LibraryError("入库申请单 JSON 写后回读失败：%s" % json_path)
    if not md_path.exists() or not html_path.exists():
        raise core.LibraryError("入库申请单落盘不完整（json/md/html）")

    print("企业素材库入库申请单已生成：%s" % json_path)
    print("HTML：%s" % html_path)
    for d in dedup:
        print("- %s｜%s｜%s｜企业类别=%s｜%s" % (
            d["任务ID"], d["动作"], d["素材名"], d["企业类别"],
            d["状态"] + ("（命中：%s）" % "、".join(d["台账命中"]) if d["台账命中"] else "")))
    print("入库引导（人工确认闸门，走 M1 现有命令）：")
    print("  1) 把真实扫描件放入素材库收件箱：open-inbox / upload --file …（或拷入后 sync-inbox）")
    print("  2) 生成归档提案：propose --out 归档提案_%s.json（人工核对归类/关键字）" % args.project)
    print("  3) 执行归档：apply --proposal 归档提案_%s.json（素材正式入企业素材库台账，跨项目可复用）" % args.project)


def _to_md_assets(doc):
    lines = ["# 企业素材库入库申请单 · %s（%s）" % (doc.get("project", ""), doc.get("enterprise", "")), "",
             "> %s" % doc.get("生成依据", ""), "",
             "申请 %d 条 ｜ 待入库 %d ｜ 已在库（可复用）%d" % (
                 doc.get("summary", {}).get("申请条数"), doc.get("summary", {}).get("待入库"),
                 doc.get("summary", {}).get("已在库（可复用）")), "",
             "## 入库申请条目", "| 任务ID | 动作 | 类别 | 素材名 | 企业类别 | 状态 |", "|---|---|---|---|---|---|"]
    for d in doc.get("entries", []):
        hit = ("（命中：%s）" % "、".join(d.get("台账命中") or [])) if d.get("台账命中") else ""
        lines.append("| %s | %s | %s | %s | %s | %s |" % (
            d.get("任务ID"), d.get("动作"), d.get("类别"), d.get("素材名"),
            d.get("企业类别"), d.get("状态") + hit))
    lines.append("")
    lines.append("> 人工确认闸门：本申请单只做去重与引导，不写入企业素材库；正式入库必须走 M1 现有命令：")
    lines.append("> open-inbox / upload（或 sync-inbox）→ propose --out 归档提案_<项目>.json（人工核对）→ apply --proposal 归档提案_<项目>.json。")
    return "\n".join(lines)


def _render_assets_html(enterprise, doc, html_path):
    rows = []
    for d in doc.get("entries", []):
        hit = ("（命中：%s）" % "、".join(d.get("台账命中") or [])) if d.get("台账命中") else ""
        rows.append("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
            d.get("任务ID"), _esc(d.get("动作")), d.get("类别"), _esc(d.get("素材名")),
            d.get("企业类别"), _esc(d.get("状态") + hit)))
    s = doc.get("summary", {})
    table = ("<table><tr style='background:#f1f3f4'><th>任务ID</th><th>动作</th><th>类别</th>"
             "<th>素材名</th><th>企业类别</th><th>状态</th></tr>%s</table>" % "".join(rows))
    kpi = ("申请 %d 条 ｜ 待入库 %d ｜ 已在库（可复用）%d" % (s.get("申请条数"), s.get("待入库"), s.get("已在库（可复用）")))
    html = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>企业素材库入库申请单 · %s</title>
<style>
 body{font-family:SimSun,serif;color:#222;margin:24px auto;max-width:920px;padding:0 16px}
 h1{font-size:20px;text-align:center;margin:8px 0}
 .meta{text-align:center;color:#666;font-size:13px;margin-bottom:14px}
 .kpi{margin:12px 0;padding:10px 14px;background:#f6f8fa;border:1px solid #d0d7de;border-radius:4px;font-size:14px}
 table{width:100%%;border-collapse:collapse;font-size:13px;margin-bottom:14px}
 th,td{border:1px solid #d0d7de;padding:6px 8px;text-align:left;vertical-align:top}
 .foot{margin-top:16px;font-size:12px;color:#666;border-top:1px solid #e1e4e8;padding-top:8px}
</style></head><body>
<h1>企业素材库入库申请单 · %s</h1>
<div class="meta">企业：%s ｜ %s</div>
<div class="kpi">%s</div>
%s
<div class="foot">人工确认闸门：本申请单只做去重与引导，不写入企业素材库；正式入库必须走 M1 现有命令：open-inbox / upload（或 sync-inbox）→ propose（人工核对）→ apply --proposal。素材入库后跨项目可复用。</div>
</body></html>""" % (
        _esc(doc.get("project", "")), _esc(doc.get("project", "")), _esc(enterprise),
        _esc(doc.get("生成时间", "")), kpi, table)
    html_path.write_text(html, encoding="utf-8")
