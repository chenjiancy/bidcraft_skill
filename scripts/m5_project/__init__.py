# -*- coding: utf-8 -*-
"""
bidcraft · M5 项目模板生成器 —— 命令实现 + 子命令注册

用法总览（示例）
----------------
  python bidcraft.py proj-gen --project "示例示例园区尾水水质提升工程（EPC总承包）监理"
      [--contract <格式契约.json>] [--material <素材清单.json>] [--source <招标文件.docx>]
      [--out <输出目录>] [--no-baseline]
"""

import argparse
import json
import os
import sys
from pathlib import Path

from _shared import core            # noqa: E402
from . import generator as gen      # noqa: E402

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


def cmd_proj_gen(args):
    ent = get_ent(args)
    if not gen.HAVE_DOCX:
        print("错误：生成器依赖 python-docx，当前环境未安装（pip install python-docx）")
        raise SystemExit(1)
    res = gen.generate(
        ent, args.project,
        contract_path=args.contract, material_path=args.material,
        source_path=args.source, out_dir=args.out, base_dir=args.base_dir,
        register_baseline=not args.no_baseline,
    )
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return
    print("项目模板已生成：%s" % res["目录"])
    for f in res["文件"]:
        print("  ✓ %-32s 契约项 %-24s 占位符 %d"
              % (f["文件"], ",".join(f["契约项"]), f["占位符数"]))
    for s in res["未生成"]:
        print("  — 未生成 %-10s %s" % (s["契约项"], s["原因"]))
    print("已登记产物基线（fb）")


def register_parser(sub):
    sp = sub.add_parser("proj-gen", help="M5：按格式契约+素材清单动态生成项目模板（docx+占位符）")
    sp.add_argument("--project", required=True, help="项目名（项目级/<项目>）")
    sp.add_argument("--contract", default="", help="格式契约 JSON 路径（默认 招标解析/格式契约/…json）")
    sp.add_argument("--material", default="", help="素材清单 JSON 路径（默认 招标解析/素材清单.json）")
    sp.add_argument("--source", default="", help="招标文件 docx 路径（默认 招标解析/招标文件-*.docx）")
    sp.add_argument("--out", default="", help="输出目录（默认 项目级/<项目>/项目模板）")
    sp.add_argument("--base-dir", default="", help="基础模板目录（企业级/模板库/<代理>/<方式>/，样式参考）")
    sp.add_argument("--no-baseline", action="store_true", help="跳过产物基线登记")
    sp.set_defaults(func=cmd_proj_gen)
