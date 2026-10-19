# -*- coding: utf-8 -*-
"""
bidcraft · M5 项目模板生成器 —— 命令实现 + 子命令注册（v2.0 布局样板范式）

用法总览（示例）
----------------
  python bidcraft.py fill-tpl --project "示例化工园尾水水质提升工程（EPC总承包）监理"
      [--agent <代理机构>] [--out <输出目录>]
  python bidcraft.py proj-mat --project <项目> [--xlsm <素材清单表.xlsm>]

V5 链路（proj-gen / proj-content-contract / proj-config-check / proj-check /
proj-freeze，招标原文深拷贝 + format_config 唯一来源）已于 2026-10-19 全面作废并移除；
唯一商务标生成管线 = fill-tpl（企业母版布局样板深拷贝 → 项目模板 → 类别聚合填充）。
"""

import argparse
import json
import os
import sys
from pathlib import Path

from _shared import core            # noqa: E402
from . import fill_from_tpl as ftpl  # noqa: E402

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


def _parse_extra(args):
    """解析 --extra '文件=样本路径;文件2=路径2' → {文件: 路径}。"""
    out = {}
    for seg in (args.extra or "").split(";"):
        seg = seg.strip()
        if not seg:
            continue
        if "=" not in seg:
            print("错误：--extra 格式应为 文件=样本路径（分号分隔），收到：%s" % seg, file=sys.stderr)
            raise SystemExit(1)
        fname, path = seg.split("=", 1)
        out[fname.strip()] = path.strip()
    return out


def cmd_fill_tpl(args):
    """M5（v2.0 布局样板范式）：企业母版（布局样板）深拷贝→项目模板→类别聚合填充→商务标。"""
    ent = get_ent(args)
    proj = ent / "项目级" / args.project
    if not proj.is_dir():
        print("错误：项目目录不存在：%s" % proj, file=sys.stderr)
        raise SystemExit(1)
    try:
        s = ftpl.fill_from_tpl(ent, proj, out_dir=args.out or None,
                               agent=args.agent or None)
    except ftpl.FillError as e:
        print("错误：%s" % e, file=sys.stderr)
        raise SystemExit(1)
    if args.json:
        print(json.dumps(s, ensure_ascii=False, indent=2))
        return
    print("商务标已生成（深拷贝模板库→填充）：%s" % (proj / "商务标"))
    print("  文字占位填充 %d 处" % s["文字占位填充"])
    if s["缺图"]:
        print("  未命中披露（缺图 %d 项，见 缺图清单.md）：" % len(s["缺图"]))
        for ph, note in s["缺图"]:
            print("    ✗ %s（%s）" % (ph, note))
    else:
        print("  缺图：无")




def cmd_proj_material(args):
    """M5 前置：把用户已填的素材清单表组装为生成器结构素材清单 JSON（v2.0 数据源）。"""
    ent = get_ent(args)
    from . import mat_export as me
    social = Path(args.social) if args.social else None
    if social is None:
        # 默认：项目资料/社保*.png（R08 社保，用户上传至项目资料）
        cands = sorted((ent / "项目级" / args.project / "项目资料").glob("社保*"))
        if cands:
            social = cands[0]
    material = me.export_material(ent, args.project, xlsm_path=args.xlsm,
                                  ledger=args.ledger, social_path=str(social) if social else "")
    out = me.write_material(ent, args.project, material, out_path=args.out)
    if args.json:
        print(json.dumps(material, ensure_ascii=False, indent=2))
        return
    print("生成器结构素材清单已组装：%s" % out)
    print("personnel：%s" % "、".join(p["name"] for p in material["personnel"]))
    for sec in ("qualification_required", "iso_certificates", "honors",
                "performance", "social_security_required"):
        items = material.get(sec, [])
        n_path = sum(1 for it in items if it.get("path"))
        print("  %-24s %d 项（已解析路径 %d/%d）" % (sec, len(items), n_path, len(items)))


def register_parser(sub):
    sp = sub.add_parser("proj-mat", help="M5：素材清单表组装为生成器结构素材清单 JSON（v2.0 数据源）")
    sp.add_argument("--project", required=True, help="项目名（项目级/<项目>）")
    sp.add_argument("--xlsm", default="", help="素材清单表路径（默认 招标解析/素材清单_空白表_v5*.xlsm 最新）")
    sp.add_argument("--ledger", default="", help="素材台账 JSON 路径（默认 企业级/素材库/素材台账.json）")
    sp.add_argument("--social", default="", help="社保素材路径（默认 项目资料/社保* 自动定位）")
    sp.add_argument("--out", default="", help="输出 JSON 路径（默认 招标解析/素材清单_<项目>.json）")
    sp.set_defaults(func=cmd_proj_material)

    sp = sub.add_parser("fill-tpl", help="M5（v2.0 布局样板范式）：企业母版（布局样板）深拷贝→项目模板→类别聚合填充→商务标（唯一商务标生成管线；替代已作废的 proj-gen 招标原文路径）")
    sp.add_argument("--project", required=True, help="项目名（项目级/<项目>）")
    sp.add_argument("--agent", default="", help="代理机构（默认从素材清单『招标代理机构』读取）")
    sp.add_argument("--out", default="", help="商务标输出目录（默认 项目级/<项目>/商务标）")
    sp.set_defaults(func=cmd_fill_tpl)
