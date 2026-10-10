# -*- coding: utf-8 -*-
"""
bidcraft · M5 项目模板生成器 —— 命令实现 + 子命令注册

用法总览（示例）
----------------
  python bidcraft.py proj-gen --project "示例化工园尾水水质提升工程（EPC总承包）监理"
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
from . import freeze as fz          # noqa: E402
from . import gen_diff as gd        # noqa: E402

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
    if args.no_baseline:
        print("已跳过产物基线登记（--no-baseline）")
    else:
        print("已登记产物基线（fb）")


def cmd_proj_freeze(args):
    ent = get_ent(args)
    proj = ent / "项目级" / args.project
    if not proj.is_dir():
        print("错误：项目目录不存在：%s" % proj, file=sys.stderr)
        raise SystemExit(1)
    tpl = args.tpl or str(proj / "项目模板")
    if args.check:
        res = fz.audit_frozen(ent, args.project, tpl_dir=tpl)
        if args.json:
            print(json.dumps(res, ensure_ascii=False, indent=2))
            return
        print("冻结审计：未变 %d / 已改 %d / 缺失 %d"
              % (len(res["unchanged"]), len(res["modified"]), len(res["missing"])))
        for r in res["modified"]:
            print("  ✗ 已改（须重新冻结）：%s（基线 %s）" % (r["相对路径"], r["版本"]))
        for r in res["missing"]:
            print("  ✗ 缺失：%s" % r["相对路径"])
        if not res["modified"] and not res["missing"]:
            print("冻结版未变，商务标可放心使用。")
        return
    man = fz.freeze_project(ent, args.project, tpl_dir=tpl, note=args.note)
    if args.json:
        print(json.dumps(man, ensure_ascii=False, indent=2))
        return
    print("已冻结：%s ｜ 冻结版本 %s ｜ %d 个模板文件（基线已登记，改动会被 fb audit 检出）"
          % (args.project, man["冻结版本"], man["文件数"]))
    print("冻结清单：%s" % fz.freeze_manifest_path(tpl))


def cmd_proj_diff(args):
    """内容校验差异清单：企业模板 vs 招标解析内容契约（D16–D20）。

    默认列出差异（md+json 落盘到 招标解析/差异清单.*）；
    --apply 读取用户已决策的差异清单（keep/update），把 keep 项文本
    写回项目模板生成稿（update 项默认已满足：生成稿文字 100% 契约）。
    """
    ent = get_ent(args)
    proj = ent / "项目级" / args.project
    if not proj.is_dir():
        print("错误：项目目录不存在：%s" % proj, file=sys.stderr)
        raise SystemExit(1)
    # 差异清单：默认读 招标解析/差异清单.json，可 --diff 指定
    diff_json = Path(args.diff) if args.diff else proj / "招标解析" / "差异清单.json"
    if args.apply:
        if not diff_json.is_file():
            print("错误：无差异清单可应用：%s（先运行 proj-diff 生成）" % diff_json, file=sys.stderr)
            raise SystemExit(1)
        keep, update = gd.load_decisions(diff_json)
        out = proj / "项目模板"
        if not out.is_dir():
            print("错误：项目模板目录不存在：%s（先运行 proj-gen）" % out, file=sys.stderr)
            raise SystemExit(1)
        applied_total, missing_total = 0, []
        for f in sorted({d.get("文件", "") for d in keep}):
            docx_path = out / f
            if not docx_path.is_file():
                missing_total.append("%s（文件缺失）" % f)
                continue
            items = [d for d in keep if d.get("文件") == f]
            n, miss = gd.apply_keep_to_docx(docx_path, items)
            applied_total += n
            missing_total.extend(miss)
        if args.json:
            print(json.dumps({"应用keep": applied_total, "update项": len(update),
                              "锚点未命中": missing_total},
                             ensure_ascii=False, indent=2))
            return
        print("已应用 keep 决策：%d 处写回模板文本 ｜ update 项 %d 处（生成稿默认契约文本，天然满足）"
              % (applied_total, len(update)))
        for x in missing_total:
            print("  — 锚点未命中（人工核对）：%s" % x)
        return
    # 默认：生成差异清单
    contract_path = Path(args.contract or gen._default_contract_path(proj))
    material_path = Path(args.material or gen._default_material_path(proj))
    source_path = Path(args.source or gen._default_source_docx(proj))
    contract = core.read_json(contract_path, None)
    if not contract or "格式文件" not in contract:
        print("错误：格式契约 JSON 无『格式文件』清单：%s" % contract_path, file=sys.stderr)
        raise SystemExit(1)
    material = core.read_json(material_path, None)
    if not material:
        print("错误：素材清单 JSON 为空：%s" % material_path, file=sys.stderr)
        raise SystemExit(1)
    blocks, _ = gen._extract_blocks(source_path)
    by_id = {it.get("id"): it for it in contract["格式文件"]}
    # 企业模板目录：--base-dir 或 素材清单代理机构+采购方式 定位
    base_dir = Path(args.base_dir) if args.base_dir else None
    if base_dir is None:
        agency = material.get("招标代理机构", "")
        mode = material.get("采购方式", "投标") or "投标"
        if agency:
            base_dir = Path(ent) / "企业级" / "模板库" / agency / mode
    diffs = []
    for m in gen.FILE_MAP:
        if m.get("kind") != "build":
            continue
        it = by_id.get(m["id"])
        if not it or not base_dir or not base_dir.is_dir():
            continue
        tpl_path = base_dir / m["file"]
        if not tpl_path.is_file():
            continue
        span = it.get("块范围") or [0, 0]
        try:
            diffs += gd.diff_template_vs_contract(tpl_path, blocks, span,
                                                  m["id"], m["file"])
        except Exception as ex:
            print("  — %s 差异提取失败：%s" % (m["file"], ex), file=sys.stderr)
    md, js = gd.write_diff_manifest(diffs, args.project, proj / "招标解析")
    if args.json:
        print(json.dumps({"差异": diffs, "清单md": str(md), "清单json": str(js)},
                         ensure_ascii=False, indent=2))
        return
    print("差异清单已生成：%s（%d 项）" % (md, len(diffs)))
    print("下一步：审阅 %s 后，编辑 %s 中『建议』字段（update/keep），"
          "再运行 proj-diff --apply --diff <该json> 应用。" % (md, js))


def cmd_proj_contract(args):
    """M5 前置①：从招标文件 docx 自动生成格式契约 JSON（块范围定位）。"""
    ent = get_ent(args)
    from . import contract_gen as cg
    src = Path(args.source) if args.source else None
    if src is None:
        # 默认：招标解析/招标文件-*.docx 或 招标文件_*.docx（源为 .doc 时提示先转换）
        try:
            from .gen_paths import _default_source_docx
            src = _default_source_docx(ent / "项目级" / args.project)
        except Exception as e:
            print("错误：%s（源文件为 .doc 时请先用 scripts/tools/doc2docx.ps1 转换为 .docx）"
                  % e, file=sys.stderr)
            raise SystemExit(1)
    contract = cg.build_contract_from_docx(src, args.project)
    out = cg.write_contract(ent, args.project, contract, out_path=args.out)
    if args.json:
        print(json.dumps(contract, ensure_ascii=False, indent=2))
        return
    print("格式契约已生成：%s" % out)
    print("格式章节：%s" % contract["格式章节"])
    for it in contract["格式文件"]:
        span = it["块范围"]
        mark = "  ✓ " if span else "  —  "
        print("%s%s  块 %s  %s" % (mark, it["id"], span if span else "（未定位，proj-gen 将跳过）", it["标题"]))


def cmd_proj_tpl_import(args):
    """M5 前置③：把格式契约空白格式提炼为企业级模板（企业级/模板库/<代理>/投标/）。"""
    ent = get_ent(args)
    from . import tpl_import as ti
    res = ti.import_templates(ent, args.project, args.agent,
                              source=args.source, out_dir=args.out)
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return
    print("企业模板已入库：%s" % res["模板目录"])
    for f in res["文件"]:
        print("  ✓ %-32s 契约项 %s  块 %s" % (f["模板"], f["契约项"], f["块范围"]))
    for s in res["跳过"]:
        print("  — 跳过 %-28s %s" % (s["模板"], s["原因"]))


def cmd_proj_material(args):
    """M5 前置④：把用户已填的 v5.1 素材清单表组装为生成器结构素材清单 JSON。"""
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
    sp = sub.add_parser("proj-tpl-import", help="M5：格式契约空白格式提炼为企业级模板入库")
    sp.add_argument("--project", required=True, help="项目名（项目级/<项目>）")
    sp.add_argument("--agent", required=True, help="代理机构名（企业级/模板库/<代理>/投标/）")
    sp.add_argument("--source", default="", help="招标文件 docx 路径（默认 招标解析/招标文件-*.docx）")
    sp.add_argument("--out", default="", help="模板输出目录（默认 企业级/模板库/<代理>/投标/）")
    sp.set_defaults(func=cmd_proj_tpl_import)

    sp = sub.add_parser("proj-mat", help="M5：v5.1 素材清单表组装为生成器结构素材清单 JSON")
    sp.add_argument("--project", required=True, help="项目名（项目级/<项目>）")
    sp.add_argument("--xlsm", default="", help="素材清单表路径（默认 招标解析/素材清单_空白表_v5*.xlsm 最新）")
    sp.add_argument("--ledger", default="", help="素材台账 JSON 路径（默认 企业级/素材库/素材台账.json）")
    sp.add_argument("--social", default="", help="社保素材路径（默认 项目资料/社保* 自动定位）")
    sp.add_argument("--out", default="", help="输出 JSON 路径（默认 招标解析/素材清单_<项目>.json）")
    sp.set_defaults(func=cmd_proj_material)


    sp = sub.add_parser("proj-contract", help="M5：从招标文件 docx 生成格式契约 JSON（块范围定位）")
    sp.add_argument("--project", required=True, help="项目名（项目级/<项目>）")
    sp.add_argument("--source", default="", help="招标文件 docx 路径（默认 招标解析/招标文件-*.docx）")
    sp.add_argument("--out", default="", help="契约 JSON 输出路径（默认 招标解析/格式契约/格式契约.json）")
    sp.set_defaults(func=cmd_proj_contract)

    sp = sub.add_parser("proj-gen", help="M5：按格式契约+素材清单动态生成项目模板（docx+占位符）")
    sp.add_argument("--project", required=True, help="项目名（项目级/<项目>）")
    sp.add_argument("--contract", default="", help="格式契约 JSON 路径（默认 招标解析/格式契约/…json）")
    sp.add_argument("--material", default="", help="素材清单 JSON 路径（默认 招标解析/素材清单.json）")
    sp.add_argument("--source", default="", help="招标文件 docx 路径（默认 招标解析/招标文件-*.docx）")
    sp.add_argument("--out", default="", help="输出目录（默认 项目级/<项目>/项目模板）")
    sp.add_argument("--base-dir", default="", help="基础模板目录（企业级/模板库/<代理>/<方式>/，样式参考）")
    sp.add_argument("--no-baseline", action="store_true", help="跳过产物基线登记")
    sp.set_defaults(func=cmd_proj_gen)

    sp = sub.add_parser("proj-diff", help="M5：内容校验差异清单（企业模板 vs 招标解析契约，D16–D20）")
    sp.add_argument("--project", required=True, help="项目名（项目级/<项目>）")
    sp.add_argument("--contract", default="", help="格式契约 JSON 路径（默认 招标解析/格式契约/…json）")
    sp.add_argument("--material", default="", help="素材清单 JSON 路径（默认 招标解析/素材清单.json）")
    sp.add_argument("--source", default="", help="招标文件 docx 路径（默认 招标解析/招标文件-*.docx）")
    sp.add_argument("--base-dir", default="", help="企业模板库目录（默认 素材清单代理机构+采购方式 定位）")
    sp.add_argument("--diff", default="", help="差异清单 JSON 路径（默认 招标解析/差异清单.json）")
    sp.add_argument("--apply", action="store_true", help="应用差异清单决策（keep 写回模板文本）")
    sp.set_defaults(func=cmd_proj_diff)

    sp = sub.add_parser("proj-freeze", help="M5：冻结项目模板（登记fb基线+冻结清单，商务标只认冻结版）")
    sp.add_argument("--project", required=True, help="项目名（项目级/<项目>）")
    sp.add_argument("--tpl", default="", help="项目模板目录（默认 项目级/<项目>/项目模板）")
    sp.add_argument("--check", action="store_true", help="仅审计冻结后是否被改动（不重新冻结）")
    sp.add_argument("--note", default="", help="冻结备注")
    sp.set_defaults(func=cmd_proj_freeze)
