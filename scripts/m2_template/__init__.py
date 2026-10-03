# -*- coding: utf-8 -*-
"""
bidcraft · M2 模板库 —— 模块子包（命令实现 + 子命令注册）

用法总览（示例）
----------------
  # 1) 初始化模板库台账（幂等）
  python bidcraft.py tpl-init

  # 2) 导入一个模板文件（复制到 模板库/<代理机构>/<方式>/ 并登记台账）
  python bidcraft.py tpl-import --file "D:/模板/开标一览表.docx" --agency 大成工程咨询有限公司 --mode 投标

  # 3) 检索 / 列表 / 概览 / 对账 / 登记清单
  python bidcraft.py tpl-list --agency 大成工程咨询有限公司 --mode 投标
  python bidcraft.py tpl-query --keyword 开标一览表
  python bidcraft.py tpl-overview
  python bidcraft.py tpl-sync
  python bidcraft.py tpl-registry --agency 大成工程咨询有限公司 --mode 投标

模板库根目录（软件根）优先级：--root 参数 > 环境变量 BIDCRAFT_LIB_ROOT > 当前目录下的「素材库/」。
"""

import argparse
import json
import os
import sys
from pathlib import Path

from _shared import core            # noqa: E402
from . import template_lib as tl     # noqa: E402

try:  # Windows 控制台中文输出
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


# --------------------------------------------------------------------------
# 公共（CLI 辅助）
# --------------------------------------------------------------------------
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


def table(rows, headers):
    """极简等宽表（中文按 2 列宽估算，与 m1_assets 一致）。"""
    def w(s):
        s = str(s)
        return sum(2 if ord(c) > 127 else 1 for c in s)

    widths = [w(h) for h in headers]
    for r in rows:
        for i, c in enumerate(r):
            widths[i] = max(widths[i], w(c))
    line = "  ".join(h + " " * (widths[i] - w(h)) for i, h in enumerate(headers))
    out = [line, "-" * w(line)]
    for r in rows:
        out.append("  ".join(str(c) + " " * (widths[i] - w(str(c))) for i, c in enumerate(r)))
    return "\n".join(out)


def _tpl_rows(rows):
    return [[r.get("代理机构", ""), r.get("方式", ""), r.get("文件", ""),
             r.get("占位符数", ""), r.get("图片占位符数", ""), r.get("备注", "")]
            for r in rows]


# --------------------------------------------------------------------------
# 命令实现
# --------------------------------------------------------------------------
def cmd_tpl_init(args):
    ent = get_ent(args)
    existed, rows = tl.init_ledger(ent, force=args.force)
    dump({"ok": True, "ledger_total": len(rows),
          "path": str(tl.template_root(ent)), "was_existed": existed}, args, human=(
        ("台账已存在，已复用（%d 条）：%s" % (len(rows), tl.template_root(ent))
         if existed else
         "已初始化模板台账：%s" % tl.template_root(ent))
        + "\n台账文件：%s / %s" % (tl.LEDGER_CSV, tl.LEDGER_JSON)
        + "\n目录：模板库\\<招标代理机构>\\{投标,采购,询比价}"
        + ("" if not args.force else "\n（--force：已重建为空台账）")
    ))


def cmd_tpl_import(args):
    ent = get_ent(args)
    row = tl.import_template(ent, args.agency, args.mode, args.file,
                             note=args.note, placeholders=args.placeholders,
                             img_placeholders=args.img_placeholders,
                             in_place=args.in_place)
    dump(row, args, human=(
        "已%s模板：%s\\%s\\%s"
        % ("登记" if args.in_place else "导入", args.agency, args.mode, row["文件"])
        + "\n占位符：%s 个（其中图片占位 %s 个）" % (row["占位符数"], row["图片占位符数"])
        + "\n登记清单：%s" % row["登记清单"]
    ))


def cmd_tpl_list(args):
    ent = get_ent(args)
    rows = tl.list_templates(ent, agency=args.agency, mode=args.mode)
    if args.json:
        print(json.dumps({"total": len(rows), "templates": rows},
                         ensure_ascii=False, indent=2))
    else:
        if not rows:
            print("（无模板记录%s）" % (
                "（代理机构=%s、方式=%s）" % (args.agency, args.mode) if (args.agency or args.mode) else ""))
            return
        print("模板台账（%d 条）：" % len(rows))
        print(table(_tpl_rows(rows), ["代理机构", "方式", "文件", "占位符数", "图片占位符", "备注"]))


def cmd_tpl_query(args):
    ent = get_ent(args)
    rows = tl.query_templates(ent, agency=args.agency, mode=args.mode, keyword=args.keyword)
    if args.json:
        print(json.dumps({"total": len(rows), "templates": rows},
                         ensure_ascii=False, indent=2))
    else:
        if not rows:
            print("（无匹配记录）")
            return
        print("检索结果（%d 条）：" % len(rows))
        print(table(_tpl_rows(rows), ["代理机构", "方式", "文件", "占位符数", "图片占位符", "备注"]))


def cmd_tpl_overview(args):
    ent = get_ent(args)
    ov = tl.overview(ent)
    if args.json:
        print(json.dumps(ov, ensure_ascii=False, indent=2))
    else:
        print("模板库概览：%s" % ov["enterprise"])
        print("台账总数：%d 条" % ov["ledger_total"])
        for a, modes in sorted(ov["by_agency"].items()):
            print("  %s：%s" % (a, "、".join("%s %d" % (m, n) for m, n in sorted(modes.items()))))
        print("目录：%s" % tl.template_root(ent))


def cmd_tpl_sync(args):
    ent = get_ent(args)
    res = tl.sync_templates(ent)
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        print("模板库对账（%s）：" % ent.name)
        print("  磁盘有但台账缺失（待登记）：%d 个" % len(res["new_files"]))
        for f in res["new_files"]:
            print("    + %s" % f["相对路径"])
        print("  台账有但文件缺失：%d 个" % len(res["missing_rows"]))
        for r in res["missing_rows"]:
            print("    - %s" % r.get("相对路径", ""))


def cmd_tpl_registry(args):
    ent = get_ent(args)
    res = tl.read_registry(ent, args.agency, args.mode, file_filter=args.file)
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        if not res["exists"]:
            print("登记清单不存在：%s" % res["path"])
            print("提示：占位符登记清单.md 由 agent 按模板逐项维护（序号/占位符/说明），供 M5 填充与 M7 检查引用。")
            return
        print("登记清单：%s" % res["path"])
        print(res["content"] or "（无匹配内容）")


# --------------------------------------------------------------------------
# 子命令注册（由薄壳 bidcraft.py 调用）
# --------------------------------------------------------------------------
def register_parser(sub):
    sp = sub.add_parser("tpl-init", help="M2：初始化模板库台账（幂等；--force 重建为空台账）")
    sp.add_argument("--force", action="store_true", help="已存在时重建为空台账（仅迁移场景）")
    sp.set_defaults(func=cmd_tpl_init)

    sp = sub.add_parser("tpl-import", help="M2：导入模板文件（复制到模板库并登记台账；--in-place 登记库内已有文件）")
    sp.add_argument("--file", required=True, help="待导入模板文件路径（docx/doc/pdf/txt/md）")
    sp.add_argument("--agency", required=True, help="招标代理机构名")
    sp.add_argument("--mode", required=True, choices=tl.MODES, help="采购方式")
    sp.add_argument("--note", default="", help="备注")
    sp.add_argument("--placeholders", type=int, help="占位符数（非 docx 格式且无法自动扫描时必填）")
    sp.add_argument("--img-placeholders", type=int, help="图片占位符数（同上）")
    sp.add_argument("--in-place", action="store_true",
                    help="登记模板库内已存在的文件（不复制；用于 tpl-sync 发现后的补登记）")
    sp.set_defaults(func=cmd_tpl_import)

    sp = sub.add_parser("tpl-list", help="M2：列出模板台账（可按代理机构/方式过滤）")
    sp.add_argument("--agency", default="")
    sp.add_argument("--mode", default="")
    sp.set_defaults(func=cmd_tpl_list)

    sp = sub.add_parser("tpl-query", help="M2：按代理机构/方式/关键字检索模板台账")
    sp.add_argument("--agency", default="")
    sp.add_argument("--mode", default="")
    sp.add_argument("--keyword", default="")
    sp.set_defaults(func=cmd_tpl_query)

    sp = sub.add_parser("tpl-overview", help="M2：模板库概览（代理机构×方式计数）")
    sp.set_defaults(func=cmd_tpl_overview)

    sp = sub.add_parser("tpl-sync", help="M2：目录与台账对账（待登记新文件/缺失文件）")
    sp.set_defaults(func=cmd_tpl_sync)

    sp = sub.add_parser("tpl-registry", help="M2：打印某代理机构/方式下的占位符登记清单")
    sp.add_argument("--agency", required=True, help="招标代理机构名")
    sp.add_argument("--mode", required=True, choices=tl.MODES, help="采购方式")
    sp.add_argument("--file", default="", help="只显示包含该文件名的节")
    sp.set_defaults(func=cmd_tpl_registry)
