# -*- coding: utf-8 -*-
"""
bidcraft · M7 交标前质量检查 —— 命令实现 + 子命令注册

用法：
  python bidcraft.py m7-check --project "马鞍山和县化工园尾水水质提升工程（EPC总承包）监理"
      [--out <商务标目录>] [--tpl <项目模板目录>]
"""

import argparse
import json
import os
import sys
from pathlib import Path

from _shared import core            # noqa: E402
from . import checker as m7        # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


def lib_root(args):
    return Path(args.root or os.environ.get("BIDCRAFT_LIB_ROOT") or os.path.join(os.getcwd(), "素材库"))


def get_ent(args):
    lib = core.Library(lib_root(args))
    return lib.resolve(getattr(args, "enterprise", None))


def cmd_m7_check(args):
    ent = get_ent(args)
    proj = ent / "项目级" / args.project
    if not proj.is_dir():
        print("错误：项目目录不存在：%s" % proj, file=sys.stderr)
        raise SystemExit(1)
    res = m7.run_checks(ent, proj, out_dir=args.out or None, tpl_dir=args.tpl or None)
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return
    print("M7 检查总判定：%s" % ("全部通过 ✓" if res["ok"] else "存在未通过项 ✗"))
    for r in res["检查"]:
        mark = "✓" if r["ok"] else "✗"
        print("  [%s] %s（%s） 问题 %d 条" % (mark, r["name"], r["level"], len(r["issues"])))
        for x in r["issues"][:8]:
            print("      - %s" % x)
        if len(r["issues"]) > 8:
            print("      … 共 %d 条，详见报告" % len(r["issues"]))
    print("报告：%s" % res["目录"])


def register_parser(sub):
    sp = sub.add_parser("m7-check", help="M7：交标前质量检查（格式完整性/占位符清零/敏感残留）")
    sp.add_argument("--project", required=True, help="项目名（项目级/<项目>）")
    sp.add_argument("--out", default="", help="商务标输出目录（默认 项目级/<项目>/商务标）")
    sp.add_argument("--tpl", default="", help="项目模板目录（默认 项目级/<项目>/项目模板）")
    sp.set_defaults(func=cmd_m7_check)
