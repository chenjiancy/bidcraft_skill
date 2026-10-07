# -*- coding: utf-8 -*-
"""
bidcraft · M1 素材库 —— 模块子包（命令实现拆分至 commands.py，本文件仅子命令注册 + re-export）

用法总览（示例）
----------------
  # 0) 建企业（首次调用 skill 必做；软件目录三层结构由 init-enterprise 生成）
  python bidcraft.py init-enterprise --name "示例XX工程监理有限公司"

  # 1) 打开收件箱 → 逐张上传 → 关闭收件箱
  python bidcraft.py open-inbox
  python bidcraft.py upload --file "D:/下载/营业执照.jpg"
  python bidcraft.py upload --file "D:/下载/张三身份证正面.jpg"
  python bidcraft.py close-inbox

  # 2) 生成归档建议（半自动：人来确认/修改）
  python bidcraft.py propose --out 归档提案.json

  # 3) 按提案执行归档
  python bidcraft.py apply --proposal 归档提案.json

  # 4) 巡检（非常规上传 + 命名规范 + 归属）
  python bidcraft.py inspect

  # 5) 检索 / 概览 / 回收站
  python bidcraft.py query --category 人员 --keyword 监理工程师
  python bidcraft.py overview
  python bidcraft.py cleanup-trash --days 30

素材库根目录（软件根）优先级：--root 参数 > 环境变量 BIDCRAFT_LIB_ROOT > 当前目录下的「素材库/」。
"""

import argparse
import json
import os
import sys
from pathlib import Path

from _shared import core          # noqa: E402
from _shared import naming as nm  # noqa: E402

# 命令实现（拆分至 commands.py；保留全部对外符号：lib_root/get_lib/get_ent/dump/table/cmd_*）
from .commands import (lib_root, get_lib, get_ent, dump, table,   # noqa: E402,F401
                       cmd_init_enterprise, cmd_list_enterprises, cmd_overview,
                       cmd_open_inbox, cmd_sync_inbox, cmd_upload, cmd_close_inbox,
                       cmd_inbox_status, cmd_propose, cmd_apply, cmd_validate,
                       cmd_inspect, cmd_query, cmd_trash, cmd_rm_project,
                       cmd_cleanup_trash, cmd_reconcile, cmd_rules, cmd_build_name,
                       cmd_build_project_folder, cmd_classify, cmd_ownership_check)

try:  # Windows 控制台中文输出
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


# --------------------------------------------------------------------------
# 子命令注册（由薄壳 bidcraft.py 调用）
# --------------------------------------------------------------------------
def register_parser(sub):
    sp = sub.add_parser("init-enterprise", help="创建/复用企业并初始化目录与台账（三层结构）")
    sp.add_argument("--name", required=True, help="企业全名")
    sp.add_argument("--credit-code", help="统一社会信用代码后 6 位（重名时用）")
    sp.add_argument("--owner", help="归属主体名（默认同企业名）")
    sp.set_defaults(func=cmd_init_enterprise)

    sp = sub.add_parser("list-enterprises", help="列出所有企业")
    sp.set_defaults(func=cmd_list_enterprises)

    sp = sub.add_parser("overview", help="企业素材库概览")
    sp.set_defaults(func=cmd_overview)

    sp = sub.add_parser("open-inbox", help="打开收件箱（开始一个上传批次）")
    sp.add_argument("--note", help="批次备注")
    sp.add_argument("--force", action="store_true", help="强制开新批次（放弃当前未关闭批次）")
    sp.set_defaults(func=cmd_open_inbox)

    sp = sub.add_parser("upload", help="逐张上传（单次仅一个文件）")
    sp.add_argument("--file", required=True, help="待上传文件路径")
    sp.add_argument("--name", help="覆盖写入收件箱的文件名")
    sp.set_defaults(func=cmd_upload)

    sp = sub.add_parser("close-inbox", help="关闭收件箱（封存本批次）")
    sp.set_defaults(func=cmd_close_inbox)

    sp = sub.add_parser("sync-inbox", help="补登记「直接拷进收件箱文件夹」的文件")
    sp.set_defaults(func=cmd_sync_inbox)

    sp = sub.add_parser("inbox-status", help="查看收件箱当前批次")
    sp.set_defaults(func=cmd_inbox_status)

    sp = sub.add_parser("propose", help="生成归档建议（半自动确认制）")
    sp.add_argument("--out", help="提案输出路径（默认 <素材库>/收件箱/_归档提案.json）")
    sp.add_argument("--allow-open", action="store_true", help="允许在收件箱未关闭时生成建议")
    sp.set_defaults(func=cmd_propose)

    sp = sub.add_parser("apply", help="按提案执行归档（改名+移动+写台账）")
    sp.add_argument("--proposal", required=True, help="提案 JSON 路径")
    sp.add_argument("--allow-open", action="store_true", help="允许在收件箱未关闭时执行")
    sp.set_defaults(func=cmd_apply)

    sp = sub.add_parser("validate", help="校验单个文件名是否符合规范")
    sp.add_argument("--category", required=True, choices=nm.list_categories())
    sp.add_argument("--subtype", choices=None)
    sp.add_argument("--name", required=True, help="文件名")
    sp.set_defaults(func=cmd_validate)

    sp = sub.add_parser("inspect", help="巡检：非常规上传 + 命名规范 + 归属")
    sp.set_defaults(func=cmd_inspect)

    sp = sub.add_parser("query", help="按条件检索素材台账（默认精确子串；--fuzzy 走 ⑤ 混合检索+重排）")
    sp.add_argument("--category")
    sp.add_argument("--subtype")
    sp.add_argument("--keyword")
    sp.add_argument("--owner")
    sp.add_argument("--expires-before", help="到期日早于 YYYYMMDD")
    sp.add_argument("--expires-after", help="到期日晚于/等于 YYYYMMDD")
    sp.add_argument("--fuzzy", action="store_true",
                    help="混合检索：字符相似度兜底召回 + 字段加权重排（返回带 score）")
    sp.add_argument("--top-k", type=int, default=20, help="混合检索返回条数上限（默认 20）")
    sp.set_defaults(func=cmd_query)

    sp = sub.add_parser("trash", help="把素材移入公司回收站")
    sp.add_argument("--path", required=True, help="相对素材库的路径，如 资质/旧证书_20200101.jpg")
    sp.add_argument("--reason", help="删除原因")
    sp.set_defaults(func=cmd_trash)

    sp = sub.add_parser("rm-project", help="删除项目：整体移入公司回收站（30 天后清理）")
    sp.add_argument("--project", required=True, help="项目名（项目级下的目录名）")
    sp.add_argument("--reason", help="删除原因")
    sp.set_defaults(func=cmd_rm_project)

    sp = sub.add_parser("cleanup-trash", help="清理超期回收站文件")
    sp.add_argument("--days", type=int, default=core.TRASH_RETENTION_DAYS)
    sp.set_defaults(func=cmd_cleanup_trash)

    sp = sub.add_parser("reconcile", help="数据一致性巡检：台账↔磁盘↔回收站三方对账（只读）")
    sp.add_argument("--enterprise", help="指定企业目录名；缺省巡检全部企业")
    sp.set_defaults(func=cmd_reconcile)

    sp = sub.add_parser("rules", help="打印命名规范规则表")
    sp.add_argument("--category", choices=nm.list_categories())
    sp.set_defaults(func=cmd_rules)

    sp = sub.add_parser("build-name", help="按字段拼出规范文件名")
    sp.add_argument("--category", required=True, choices=nm.list_categories())
    sp.add_argument("--subtype")
    sp.add_argument("--keyword", action="append", default=[], help="可重复")
    sp.add_argument("--date", action="append", default=[], help="可重复，8 位或 长期/日期不详")
    sp.add_argument("--page", type=int)
    sp.add_argument("--ext", help="含点或不含点均可")
    sp.set_defaults(func=cmd_build_name)

    sp = sub.add_parser("build-project-folder", help="拼出业绩项目文件夹名")
    sp.add_argument("--project", required=True)
    sp.add_argument("--date", required=True, help="签订日期 8 位")
    sp.add_argument("--director", help="总监姓名；缺省为「无总监」")
    sp.set_defaults(func=cmd_build_project_folder)

    sp = sub.add_parser("classify", help="按文件名智能判断归类与字段")
    sp.add_argument("--name", required=True)
    sp.set_defaults(func=cmd_classify)

    sp = sub.add_parser("ownership-check", help="企业归属校验（文件名层）")
    sp.add_argument("--name", required=True, help="文件名")
    sp.add_argument("--text", help="agent 从正文/OCR 提取到的文本（可选）")
    sp.set_defaults(func=cmd_ownership_check)
