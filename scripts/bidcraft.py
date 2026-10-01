#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
bidcraft · 统一命令行入口（薄壳）

职责：只做 argparse 组装与调度，不写业务逻辑。
各模块子命令由对应子包的 register_parser(subparsers) 挂载（当前：m1_assets）。

用法：
  python bidcraft.py [--root <软件根>] [--enterprise <企业>] [--json] <子命令> ...
"""

import argparse
import os
import sys

# 保证 scripts/ 可被导入（不同启动方式下 sys.path[0] 可能不是脚本目录）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import m1_assets                    # noqa: E402
import m4_tender                    # noqa: E402
from _shared import core            # noqa: E402
from _shared import naming as nm    # noqa: E402

try:  # Windows 控制台中文输出
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


def build_parser():
    p = argparse.ArgumentParser(
        prog="bidcraft",
        description="bidcraft · 标书制作 CLI（当前模块：M1 素材库，纯文件系统 + 对话式 agent 驱动）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--root", help="软件根目录（默认：环境变量 BIDCRAFT_LIB_ROOT 或 ./素材库）")
    p.add_argument("--enterprise", help="指定企业目录名（多企业时必填）")
    p.add_argument("--json", action="store_true", help="以 JSON 输出（供 agent 机读）")
    p.add_argument("--trash-days", type=int, default=core.TRASH_RETENTION_DAYS, help="回收站保留天数（默认 30）")

    sub = p.add_subparsers(dest="cmd", required=True)
    m1_assets.register_parser(sub)          # 挂载 M1 素材库全部子命令
    m4_tender.register_parser(sub)          # 挂载 M4 招标解析子命令
    return p


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
    except (core.LibraryError, nm.NamingError) as e:
        print("❌ %s" % e, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
