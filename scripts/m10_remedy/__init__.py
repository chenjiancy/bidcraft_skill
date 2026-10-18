# -*- coding: utf-8 -*-
"""
bidcraft · M10 失分补救指引 —— CLI

命令：remedy-gen
  --project  项目名（项目级/<项目>，M8 模拟评标产物所在）
  可选 --sub  主观评审 json（缺省自动探测 模拟评标/主观评审_<项目>.json）

产物（项目级/<项目>/模拟评标/）：
  失分补救任务单_<项目>.json / .md / .html（人工确认闸门）
"""
import argparse
from pathlib import Path

from _shared import core

from . import remedy, remedy_report

OUT_DIR_NAME = "模拟评标"


def task_base(project):
    return "失分补救任务单_%s" % project


def _proj_dir(root, enterprise, project):
    pd = Path(root) / enterprise / "项目级" / project
    if not pd.is_dir():
        raise core.LibraryError("项目目录不存在：%s（M10 依赖 M8 模拟评标产物，先执行 M8 eval-run）" % pd)
    return pd


def cmd_remedy_gen(args):
    root = Path(args.root)
    ent = args.enterprise
    if not ent:
        raise core.LibraryError("请指定 --enterprise（企业名）")
    proj_dir = _proj_dir(root, ent, args.project)
    out_dir = proj_dir / OUT_DIR_NAME

    sim_path = out_dir / ("模拟评标_%s.json" % args.project)
    if not sim_path.is_file():
        raise core.LibraryError("M8 通道A 产物不存在：%s（先执行 eval-run）" % sim_path)
    a = core.read_json(str(sim_path), None)
    if not a:
        raise core.LibraryError("M8 通道A 产物无法读取：%s" % sim_path)

    subjective = None
    if args.sub:
        sp = Path(args.sub)
        if not sp.is_file():
            raise core.LibraryError("主观评审 json 不存在：%s" % sp)
        subjective = core.read_json(str(sp), None)
        if not subjective:
            raise core.LibraryError("主观评审 json 无法读取：%s" % sp)
    else:
        sp = out_dir / ("主观评审_%s.json" % args.project)
        if sp.is_file():
            subjective = core.read_json(str(sp), None)
            if not subjective:
                print("提示：通道B 主观评审 json 为空，仅按通道A 生成任务单")
        else:
            print("提示：通道B 主观评审未产出（%s 不存在），仅按通道A 生成任务单" % sp)

    doc = remedy.gen_tasks(a, subjective)
    base = task_base(args.project)
    json_path = out_dir / ("%s.json" % base)
    md_path = out_dir / ("%s.md" % base)
    html_path = out_dir / ("%s.html" % base)
    core.write_json(str(json_path), doc)
    md_path.write_text(remedy.to_md(doc), encoding="utf-8")
    remedy_report.render_task_html(args.project, doc, html_path)

    back = core.read_json(str(json_path), None)
    if not back or back.get("project") != args.project:
        raise core.LibraryError("任务单 JSON 写后回读失败：%s" % json_path)
    if not md_path.exists() or not html_path.exists():
        raise core.LibraryError("任务单产物落盘不完整（json/md/html）")

    s = doc["summary"]
    print("失分补救任务单已生成：%s" % json_path)
    print("文本版：%s" % md_path)
    print("HTML 报告：%s（浏览器打开，人工确认闸门）" % html_path)
    print("任务总数 %s；可追分合计 %.1f 分（客观 %.1f/%.1f%s）" % (
        s["任务总数"], s["可追分合计"] or 0, s["客观分当前"] or 0, s["客观分满分"] or 0,
        ("；主观 %s" % ("[%s-%s]/%s" % (s["主观分"]["min"], s["主观分"]["max"], s["主观分"]["满分"])) if s.get("主观分") else "；主观未评")))
    print("下一步：按任务单执行（素材补齐走 M5 归档流程；内容/格式/报价按动作步骤修订），完成后重跑 eval-run/eval-report 验证（人工确认闸门）")


def register_parser(sub):
    sp = sub.add_parser("remedy-gen", help="M10 失分补救指引：把 M8 模拟评标失分诊断转成可执行补救任务单（素材补齐/内容补强/格式合规/报价策略）→ 模拟评标/失分补救任务单_<项目>.json/.md/.html")
    sp.add_argument("--project", required=True, help="项目名（项目级/<项目>，M8 模拟评标产物所在）")
    sp.add_argument("--sub", default="", help="通道B 主观评审 json（缺省自动探测 模拟评标/主观评审_<项目>.json）")
    sp.set_defaults(func=cmd_remedy_gen)
