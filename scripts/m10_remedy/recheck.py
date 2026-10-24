# -*- coding: utf-8 -*-
"""
bidcraft · M10 T18 补救→重检自动闭环 —— CLI

命令：
  remedy-done  --project <项目> --id <任务ID> [--note <说明>]
               任务单勾选完成（人工确认闸门：用户主动执行命令即确认该任务已整改）。
  remedy-recheck --project <项目> [--check <机器检查json>] [--no-eval]
               补救后重检：已勾选任务自动复核（M7 check-rule 新产物对比检查快照 +
               M8 eval-run 重跑对比失分 gap），输出 补救后重检报告_<项目>.json/.md/.html；
               新问题检查项自动并入任务单（写回回读）。

产物（项目级/<项目>/模拟评标/）：
  补救后重检报告_<项目>.json / .md / .html（人工确认闸门）
"""
import argparse
import datetime as _dt
from pathlib import Path

from _shared import core

from . import remedy, remedy_report
from . import recheck_html

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


def _write_back(path, doc, project):
    core.write_json(str(path), doc)
    back = core.read_json(str(path), None)
    if not back or back.get("project") != project:
        raise core.LibraryError("任务单写后回读失败：%s" % path)


def cmd_remedy_done(args):
    root = Path(args.root)
    ent = args.enterprise
    if not ent:
        raise core.LibraryError("请指定 --enterprise（企业名）")
    proj_dir = _proj_dir(root, ent, args.project)
    out_dir = proj_dir / OUT_DIR_NAME
    path, doc = _task_doc(out_dir, args.project)
    r = remedy.mark_done(doc, args.id, args.note)
    if not r["found"]:
        raise core.LibraryError("任务单中不存在任务 id=%s（可用 id：%s）" % (
            args.id, "、".join(t.get("id", "?") for t in doc.get("tasks") or [])))
    _write_back(path, doc, args.project)
    t = r["task"]
    print("任务 %s 已勾选完成：%s" % (t["id"], t["标题"]))
    print("完成时间 %s；备注：%s" % (t["完成时间"], t["完成备注"]))
    print("下一步：执行 remedy-recheck --project %s 自动复核（M7 check-rule + M8 eval-run）" % args.project)


def cmd_remedy_recheck(args):
    root = Path(args.root)
    ent = args.enterprise
    if not ent:
        raise core.LibraryError("请指定 --enterprise（企业名）")
    proj_dir = _proj_dir(root, ent, args.project)
    out_dir = proj_dir / OUT_DIR_NAME
    path, doc = _task_doc(out_dir, args.project)
    done = [t for t in (doc.get("tasks") or []) if t.get("完成状态") == "已完成"]
    if not done:
        raise core.LibraryError("任务单没有已勾选完成的任务（先执行 remedy-done --id <任务ID>）")

    # 1) M7 重检：机器检查新产物（缺省自动探测 标书检查/机器检查_<项目>_技术标.json，其次 _<项目>.json）
    check_new = None
    if args.check:
        cp = Path(args.check)
        if not cp.is_file():
            raise core.LibraryError("机器检查 json 不存在：%s" % cp)
        check_new = core.read_json(str(cp), None)
        if not check_new:
            raise core.LibraryError("机器检查 json 无法读取：%s" % cp)
    else:
        cands = [proj_dir / "标书检查" / ("机器检查_%s_技术标.json" % args.project),
                 proj_dir / "标书检查" / ("机器检查_%s.json" % args.project)]
        for cp in cands:
            if cp.is_file():
                check_new = core.read_json(str(cp), None)
                if check_new:
                    break
        if check_new is None:
            print("提示：未找到机器检查新产物，跳过 M7 项复核（先执行 check-rule 或 --check 传入）")

    # 2) M8 重检：重跑 eval-run（缺省自动重跑；--no-eval 跳过）
    eval_new = None
    if not args.no_eval:
        try:
            from types import SimpleNamespace
            import m8_eval as E8
            eargs = SimpleNamespace(root=str(root), enterprise=ent, project=args.project,
                                    quote="", tdir="", mat="", bid="", json=False)
            E8.cmd_eval_run(eargs)
            ep = out_dir / ("模拟评标_%s.json" % args.project)
            if ep.is_file():
                eval_new = core.read_json(str(ep), None)
            print("M8 eval-run 已重跑完成（失分 gap 对比基准）")
        except Exception as e:
            print("⚠ 重跑 eval-run 失败（%s）；失分项按需人工核对 eval-report" % e)

    rpt = remedy.recheck_tasks(doc, check_new=check_new, eval_new=eval_new)

    # 3) 写回：新问题任务并入任务单 + 每任务附加重检结果
    merged = doc
    if rpt["new_tasks"]:
        merged["tasks"].extend(rpt["new_tasks"])
        merged["summary"]["任务总数"] = len(merged["tasks"])
        merged["生成依据"] = "%s；补救后重检自动并入新问题任务 %d 条" % (merged["生成依据"], len(rpt["new_tasks"]))
    for r in rpt["results"]:
        for t in merged["tasks"]:
            if t.get("id") == r["id"]:
                t["重检结果"] = {"验证": r["验证"], "证据": r["证据"], "时间": rpt["重检时间"]}
    _write_back(path, merged, args.project)

    # 4) 落盘报告 json/md/html
    out = dict(rpt)
    out["project"] = args.project
    out["生成依据"] = "补救后重检：%d 个已勾选任务自动复核（M7 check-rule + M8 eval-run）；写回任务单见 %s" % (len(done), path)
    base = "补救后重检报告_%s" % args.project
    json_path = out_dir / ("%s.json" % base)
    md_path = out_dir / ("%s.md" % base)
    html_path = out_dir / ("%s.html" % base)
    core.write_json(str(json_path), out)
    md_path.write_text(to_md(out), encoding="utf-8")
    recheck_html.render_recheck_html(args.project, out, html_path)

    back = core.read_json(str(json_path), None)
    if not back or back.get("project") != args.project:
        raise core.LibraryError("重检报告 JSON 写后回读失败：%s" % json_path)
    if not md_path.exists() or not html_path.exists():
        raise core.LibraryError("重检报告落盘不完整（json/md/html）")

    s = out["summary"]
    print("补救后重检报告已生成：%s" % json_path)
    print("HTML 报告：%s（浏览器打开，人工确认闸门）" % html_path)
    print("已勾选 %d ｜ 通过 %d ｜ 未通过 %d ｜ 需人工复核 %d ｜ 新增问题 %d" % (
        s["已勾选任务"], s["验证通过"], s["未通过"], s["需人工复核"], s["新增问题"]))
    print(out["结论"])
    print("下一步：未通过/新增任务继续整改 → remedy-done 勾选 → 再次 remedy-recheck（闭环）")


def to_md(out):
    s = out.get("summary", {})
    lines = ["# 补救后重检报告 · %s" % out.get("project", ""), "",
             "重检时间：%s" % out.get("重检时间", ""), "",
             "已勾选任务 **%s** ｜ 验证通过 **%s** ｜ 未通过 **%s** ｜ 需人工复核 **%s** ｜ 新增问题 **%s**" % (
                 s.get("已勾选任务"), s.get("验证通过"), s.get("未通过"), s.get("需人工复核"), s.get("新增问题")), "",
             "> %s" % out.get("结论", ""), "",
             "## 复核明细", "| ID | 标题 | 验证 | 证据 |", "|---|---|---|---|"]
    for r in out.get("results", []):
        color = {"通过": "🟢", "未通过": "🔴", "需人工复核": "🟠", "无法复核": "🟠"}.get(r.get("验证"), "⚪")
        lines.append("| %s | %s | %s %s | %s |" % (
            r.get("id"), r.get("标题", "").replace("|", "／")[:40], color, r.get("验证"), r.get("证据", "")))
    if out.get("new_tasks"):
        lines.append("", "## 新增问题任务（已并入任务单）")
        for t in out["new_tasks"]:
            lines.append("- **%s** %s：%s" % (t["id"], t["动作"], t["标题"]))
            for st in t.get("动作步骤", [])[:3]:
                lines.append("  - %s" % st)
    lines.append("")
    lines.append("> 人工确认闸门：重检为确定性机器复核；语义项（失分原因、主观分）标注需人工核对 eval-report；最终以评标委员会评审为准。")
    return "\n".join(lines)


def register_parser(sub):
    sp = sub.add_parser("remedy-done", help="M10 补救任务单勾选完成（人工确认闸门）：--id <任务ID> 标记已整改，供 remedy-recheck 复核")
    sp.add_argument("--project", required=True, help="项目名")
    sp.add_argument("--id", required=True, help="任务 ID（失分补救任务单 tasks[].id，如 C01/R01）")
    sp.add_argument("--note", default="", help="完成备注（缺省=人工确认完成）")
    sp.set_defaults(func=cmd_remedy_done)

    sp2 = sub.add_parser("remedy-recheck", help="M10 补救后重检（T18 闭环）：已勾选任务自动复核（M7 检查快照对比 + M8 eval-run 重跑 gap 对比）→ 补救后重检报告_<项目>.json/.md/.html；新问题自动并入任务单")
    sp2.add_argument("--project", required=True, help="项目名")
    sp2.add_argument("--check", default="", help="M7 机器检查 json（缺省自动探测 标书检查/机器检查_<项目>_技术标.json）")
    sp2.add_argument("--no-eval", action="store_true", help="跳过 M8 eval-run 重跑（失分项按人工核对）")
    sp2.set_defaults(func=cmd_remedy_recheck)
