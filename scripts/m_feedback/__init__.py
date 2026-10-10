# -*- coding: utf-8 -*-
"""
bidcraft · 产物反馈机制 —— 模块子包（命令实现 + 子命令注册）

用法总览（示例）
----------------
  # 1) 登记/刷新产物基线（生成器落盘后调用；agent 也可手动登记）
  python bidcraft.py fb-baseline --path "项目级/示例…/项目模板/开标一览表.docx" \
      --level 项目级 --project "示例…" --type 项目模板 --generator m5-project-gen

  # 2) 变更检测（自动：每轮任务开始 --quick；深度：--full）
  python bidcraft.py fb-audit --quick
  python bidcraft.py fb-audit --full --path "项目级/…/项目模板/开标一览表.docx"

  # 3) 生成评估报告（基于最近 full 审计；agent 补充完善点后交付人工确认）
  python bidcraft.py fb-report

  # 4) 状态
  python bidcraft.py fb-status
"""

import argparse
import json
import os
import sys
from pathlib import Path

from _shared import core            # noqa: E402
from . import feedback as fb        # noqa: E402

try:  # Windows 控制台中文输出
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


def lib_root(args):
    root = args.root or os.environ.get("BIDCRAFT_LIB_ROOT") or os.path.join(os.getcwd(), "素材库")
    return Path(root)


def get_ent(args, required=True):
    lib = core.Library(lib_root(args))
    if not required and not lib.enterprises():
        return None
    return lib.resolve(getattr(args, "enterprise", None))


def dump(obj, args, human=""):
    if getattr(args, "json", False):
        print(json.dumps(obj, ensure_ascii=False, indent=2))
    else:
        print(human if human else json.dumps(obj, ensure_ascii=False, indent=2))


def cmd_fb_baseline(args):
    ent = get_ent(args)
    row = fb.register(ent, args.path, level=args.level, project=args.project or "",
                      ptype=args.type or "", generator=args.generator or "",
                      version=args.version, note=args.note)
    dump(row, args, human=(
        "已登记产物基线：%s\n  版本 %s ｜ 生成器 %s ｜ 类型 %s ｜ sha256 %s"
        % (row["相对路径"], row["版本"], row["生成器"] or "-", row["产物类型"] or "-",
           row["sha256"][:12])
    ))


def cmd_fb_audit(args):
    ent = get_ent(args)
    res = fb.audit(ent, full=args.full, path=args.path)
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return
    print("产物基线审计（%s）：检查 %d 条" % (ent.name, res["checked"]))
    print("  未变：%d ｜ 已改：%d ｜ 缺失：%d"
          % (len(res["unchanged"]), len(res["modified"]), len(res["missing"])))
    for r in res["modified"]:
        print("  ✎ 已改 %s（原版本 %s）" % (r["相对路径"], r.get("版本", "")))
    for r in res["missing"]:
        print("  ✗ 缺失 %s（原版本 %s）" % (r["相对路径"], r.get("版本", "")))
    if args.full:
        for rel, d in res["diffs"].items():
            print("  ── 差异（%s）：%d 行" % (rel, len(d)))
            for line in d[:12]:
                print("     " + line.rstrip()[:80])


def cmd_fb_report(args):
    ent = get_ent(args)
    res = fb.audit(ent, full=True, path=args.path)
    path = fb.report(ent, audit_result=res, out=args.out)
    print("评估报告已生成：%s" % path)
    print("（报告为骨架：完善点建议/影响面/风险需 agent 补充，经人工确认后才受控应用）")


def cmd_fb_status(args):
    ent = get_ent(args)
    st = fb.status(ent)
    dump(st, args, human=(
        "产物基线状态：%s\n  基线总数：%d 条\n  按类型：%s\n  基线文件：%s\n  反馈目录：%s"
        % (st["enterprise"], st["baseline_total"],
           "、".join("%s %d" % (t, n) for t, n in sorted(st["by_type"].items())) or "-",
           st["baseline_path"], st["feedback_dir"])
    ))


def register_parser(sub):
    sp = sub.add_parser("fb-baseline", help="产物反馈：登记/刷新单个产物基线（sha256+版本+文本指纹）")
    sp.add_argument("--path", required=True, help="相对企业目录的产物路径，如 项目级/X/项目模板/开标一览表.docx")
    sp.add_argument("--level", choices=["企业级", "项目级"], default="项目级")
    sp.add_argument("--project", default="", help="项目名（项目级时）")
    sp.add_argument("--type", default="", help="产物类型（项目模板/投标要点/素材清单/内容契约/模板文件/商务标…）")
    sp.add_argument("--generator", default="", help="生成器标识，如 m5-project-gen")
    sp.add_argument("--version", default=None, help="显式版本号（缺省自动 bump）")
    sp.add_argument("--note", default="", help="备注")
    sp.set_defaults(func=cmd_fb_baseline)

    sp = sub.add_parser("fb-audit", help="产物反馈：变更检测（未变/已改/缺失；--full 做文本差异）")
    sp.add_argument("--path", default="", help="只审计指定产物（相对路径）")
    sp.add_argument("--full", action="store_true", help="对已改产物做文本级差异（difflib）")
    sp.set_defaults(func=cmd_fb_audit)

    sp = sub.add_parser("fb-report", help="产物反馈：生成《系统功能更新评估报告》md（骨架，待人工确认）")
    sp.add_argument("--path", default="", help="只针对指定产物生成")
    sp.add_argument("--out", default="", help="报告输出路径（默认 产物反馈/评估报告_时间.md）")
    sp.set_defaults(func=cmd_fb_report)

    sp = sub.add_parser("fb-status", help="产物反馈：查看基线状态（总数/按类型）")
    sp.set_defaults(func=cmd_fb_status)
