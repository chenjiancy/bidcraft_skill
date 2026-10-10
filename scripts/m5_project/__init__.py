# -*- coding: utf-8 -*-
"""
bidcraft · M5 项目模板生成器 —— 命令实现 + 子命令注册

用法总览（示例）
----------------
  python bidcraft.py proj-gen --project "示例化工园尾水水质提升工程（EPC总承包）监理"
      [--contract <内容契约.json>] [--material <素材清单.json>] [--source <招标文件.docx>]
      [--tpl-select <模板选择.json>] [--out <输出目录>] [--no-baseline]
"""

import argparse
import json
import os
import sys
from pathlib import Path

from _shared import core            # noqa: E402
from . import generator as gen      # noqa: E402
from . import freeze as fz          # noqa: E402

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


def cmd_proj_gen(args):
    ent = get_ent(args)
    if not gen.HAVE_DOCX:
        print("错误：生成器依赖 python-docx，当前环境未安装（pip install python-docx）")
        raise SystemExit(1)
    res = gen.generate(
        ent, args.project,
        contract_path=args.contract, material_path=args.material,
        source_path=args.source, out_dir=args.out, base_dir=args.base_dir,
        format_config=args.format_config,
        register_baseline=not args.no_baseline,
        skip_verify=getattr(args, "skip_verify", False),
        extra_sources=_parse_extra(args) if getattr(args, "extra", "") else None,
    )
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return
    print("项目模板已生成（v5：招标原文投标文件格式深拷贝 + 通用格式配置 + 素材清单动态图片占位）：%s" % res["目录"])
    for f in res["文件"]:
        print("  ✓ %-32s 契约项 %-24s 占位符 %d 图片占位 %d"
              % (f["文件"], ",".join(f["契约项"]), f["占位符数"],
                 f.get("图片占位", 0)))
    for s in res["未生成"]:
        print("  — 未生成 %-10s %s" % (s["契约项"], s["原因"]))
    v = res.get("校验") or {}
    if v.get("结论") == "通过":
        print("代码硬校验：通过（文字逐字比对，%d 文件全部一致）" % len(v.get("文件", [])))
    elif v.get("结论") == "跳过":
        print("代码硬校验：跳过（契约未定位/无生成文件）")
    elif v.get("结论") == "不通过":
        print("代码硬校验：不通过（见 生成记录.json → 代码硬校验 → 问题）", file=sys.stderr)
        for f in v.get("文件", []):
            if f.get("结论") == "不通过":
                prob = f.get("问题") or []
                first = prob[0] if prob else {}
                desc = first.get("说明", first) if isinstance(first, dict) else first
                print("  ✗ %-32s %s" % (f["文件"], str(desc)[:120]))
    else:
        print("代码硬校验：%s" % v.get("结论"))
    pg = res.get("页数校验") or {}
    if pg.get("结论") == "通过":
        print("页数校验：通过（独占页严禁跨页，%d 文件）" % len(pg.get("文件", [])))
    elif pg.get("结论") == "跳过":
        print("页数校验：跳过")
    else:
        print("页数校验：不通过（见 生成记录.json → 页数校验 → 问题；可人工调整排版或走 agent 检查复核）",
              file=sys.stderr)
        for f in pg.get("文件", []):
            if f.get("结论") == "不通过":
                print("  ✗ %-32s %s" % (f.get("文件", ""), str(f.get("说明", ""))[:120]))
    if args.no_baseline:
        print("已跳过产物基线登记（--no-baseline）")
    else:
        print("已登记产物基线（fb）")


def cmd_proj_check(args):
    """M5：生成『项目模板检查指令』（固化提示词 + 硬校验结果 + 输出 schema）。
    agent 检查必须读取并遵循该指令执行（不得自由发挥），结果人工确认。"""
    ent = get_ent(args)
    proj = ent / "项目级" / args.project
    if not proj.is_dir():
        print("错误：项目目录不存在：%s" % proj, file=sys.stderr)
        raise SystemExit(1)
    tpl = args.tpl or str(proj / "项目模板")
    if not Path(tpl).is_dir():
        print("错误：项目模板目录不存在：%s（先运行 proj-gen）" % tpl, file=sys.stderr)
        raise SystemExit(1)
    prompt_md = Path(__file__).resolve().parents[2] / "references" / "M5-项目模板检查-提示词.md"
    if not prompt_md.is_file():
        print("错误：固化提示词不存在：%s" % prompt_md, file=sys.stderr)
        raise SystemExit(1)
    fixed_prompt = prompt_md.read_text(encoding="utf-8")
    record = core.read_json(Path(tpl) / "生成记录.json", {}) or {}
    instr = {
        "指令版本": "M5-check-v1.0",
        "项目": args.project,
        "生成时间": record.get("生成时间", ""),
        "模板目录": str(Path(tpl).resolve()),
        "生成记录": str((Path(tpl) / "生成记录.json").resolve()),
        "代码硬校验结果": record.get("代码硬校验", {}),
        "页数校验结果": record.get("页数校验", {}),
        "占位符清单": str((Path(tpl) / "项目占位符清单.md").resolve()),
        "固化提示词（必须遵循，不得自由发挥）": fixed_prompt,
        "输出": "检查报告写入 %s（严格 JSON，8 项固定清单逐项 通过/不通过/跳过 + 问题描述 + 建议），结果由人工确认。"
                % str((Path(tpl) / "检查报告.json").resolve()),
    }
    out_json = Path(tpl) / "检查指令.json"
    out_json.write_text(json.dumps(instr, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.json:
        print(json.dumps(instr, ensure_ascii=False, indent=2))
        return
    print("项目模板检查指令已生成：%s" % out_json)
    print("- 调用 agent 检查时必须读取并遵循该指令（含固化提示词），不得自由发挥；")
    print("- agent 按指令执行只读检查（不改动模板），检查报告写入 项目模板/检查报告.json；")
    print("- 检查结果由人工确认；确认通过后再进入商务标生成（唯一模板来源=项目模板）。")


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


def cmd_proj_contract(args):
    """M5 前置①：从招标文件 docx 自动生成内容契约 JSON（块范围定位，文字更新源）。"""
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
    print("内容契约已生成（招标解析投标文件格式，文字更新源）：%s" % out)
    print("格式章节：%s" % contract["格式章节"])
    for it in contract["格式文件"]:
        span = it["块范围"]
        mark = "  ✓ " if span else "  —  "
        print("%s%s  块 %s  %s" % (mark, it["id"], span if span else "（未定位，proj-gen 将跳过）", it["标题"]))


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


def cmd_proj_config_check(args):
    """M5（v5）：生成『格式配置校验指令』（固化提示词 + 输入路径 + 输出 schema）。
    agent 读取该指令，生成前校验 format_config.json 与招标文件投标格式要求是否
    冲突/缺失（只读检查），报告写入 招标解析/检查报告_格式配置.json，结果人工确认；
    确认通过前不得执行 proj-gen。"""
    ent = get_ent(args)
    proj = ent / "项目级" / args.project
    if not proj.is_dir():
        print("错误：项目目录不存在：%s" % proj, file=sys.stderr)
        raise SystemExit(1)
    prompt_md = Path(__file__).resolve().parents[2] / "references" / "M5-格式配置校验-提示词.md"
    if not prompt_md.is_file():
        print("错误：固化提示词不存在：%s" % prompt_md, file=sys.stderr)
        raise SystemExit(1)
    fixed_prompt = prompt_md.read_text(encoding="utf-8")
    cfg_path = Path(args.format_config) if args.format_config \
        else Path(__file__).resolve().parent / "format_config.json"
    contract_path = Path(args.contract) if args.contract else gen._default_contract_path(proj)
    instr = {
        "指令版本": "M5-config-check-v1.0",
        "项目": args.project,
        "格式配置": str(cfg_path.resolve()),
        "内容契约": str(contract_path.resolve()),
        "招标文件源": str((Path(args.source) if args.source else gen._default_source_docx(proj)).resolve()),
        "固化提示词（必须遵循，不得自由发挥）": fixed_prompt,
        "输出": "检查报告写入 %s（严格 JSON，8 项固定清单逐项 通过/不通过/待补充 + 问题 + 建议），结果由人工确认；确认通过前不得执行 proj-gen。"
                % str((proj / "招标解析" / "检查报告_格式配置.json").resolve()),
    }
    out_json = proj / "招标解析" / "格式配置校验指令.json"
    out_json.write_text(json.dumps(instr, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.json:
        print(json.dumps(instr, ensure_ascii=False, indent=2))
        return
    print("格式配置校验指令已生成：%s" % out_json)
    print("- 调用 agent 执行生成前校验（只读，8 项检查清单，固化提示词，不得自由发挥）；")
    print("- 检查报告写入 招标解析/检查报告_格式配置.json；")
    print("- 结果由人工确认；确认通过后再执行 proj-gen 生成项目模板。")


def register_parser(sub):
    sp = sub.add_parser("proj-gen", help="M5（v5）：招标原文投标格式深拷贝 + 通用格式配置 + 素材清单动态图片占位生成项目模板")
    sp.add_argument("--project", required=True, help="项目名（项目级/<项目>）")
    sp.add_argument("--contract", default="", help="内容契约 JSON 路径（默认 招标解析/内容契约/内容契约.json）")
    sp.add_argument("--material", default="", help="素材清单 JSON 路径（默认 招标解析/素材清单_<项目>.json）")
    sp.add_argument("--source", default="", help="招标文件 docx 路径（默认 招标解析/招标文件-*.docx）")
    sp.add_argument("--out", default="", help="项目模板输出目录（默认 项目级/<项目>/项目模板）")
    sp.add_argument("--base-dir", default="", help="保留兼容参数（V5 不使用）")
    sp.add_argument("--format-config", default="", help="通用格式配置 JSON 路径（默认 scripts/m5_project/format_config.json）")
    sp.add_argument("--extra", default="", help="补充文件：'文件=样本docx路径;…'（招标格式未列、用户确认需要的文件，如 中小企业声明函.docx=样本路径；从样本深拷贝+格式配置+占位化）")
    sp.add_argument("--no-baseline", action="store_true", help="跳过产物基线登记")
    sp.add_argument("--skip-verify", action="store_true", help="跳过生成后代码硬校验（一般不用）")
    sp.set_defaults(func=cmd_proj_gen)

    sp = sub.add_parser("proj-mat", help="M5：v5.1 素材清单表组装为生成器结构素材清单 JSON")
    sp.add_argument("--project", required=True, help="项目名（项目级/<项目>）")
    sp.add_argument("--xlsm", default="", help="素材清单表路径（默认 招标解析/素材清单_空白表_v5*.xlsm 最新）")
    sp.add_argument("--ledger", default="", help="素材台账 JSON 路径（默认 企业级/素材库/素材台账.json）")
    sp.add_argument("--social", default="", help="社保素材路径（默认 项目资料/社保* 自动定位）")
    sp.add_argument("--out", default="", help="输出 JSON 路径（默认 招标解析/素材清单_<项目>.json）")
    sp.set_defaults(func=cmd_proj_material)


    sp = sub.add_parser("proj-content-contract", help="M5：从招标文件 docx 生成内容契约 JSON（块范围定位）")
    sp.add_argument("--project", required=True, help="项目名（项目级/<项目>）")
    sp.add_argument("--source", default="", help="招标文件 docx 路径（默认 招标解析/招标文件-*.docx）")
    sp.add_argument("--out", default="", help="契约 JSON 输出路径（默认 招标解析/内容契约/内容契约.json）")
    sp.set_defaults(func=cmd_proj_contract)

    sp = sub.add_parser("proj-config-check", help="M5（v5）：生成『格式配置校验指令』（固化提示词，生成前 agent 校验格式配置 vs 招标要求，结果人工确认）")
    sp.add_argument("--project", required=True, help="项目名（项目级/<项目>）")
    sp.add_argument("--format-config", default="", help="通用格式配置 JSON 路径（默认 scripts/m5_project/format_config.json）")
    sp.add_argument("--contract", default="", help="内容契约 JSON 路径（默认 招标解析/内容契约/内容契约.json）")
    sp.add_argument("--source", default="", help="招标文件 docx 路径（默认 招标解析/招标文件-*.docx）")
    sp.set_defaults(func=cmd_proj_config_check)

    sp = sub.add_parser("proj-check", help="M5：生成项目模板检查指令（固化提示词+硬校验结果+输出schema，agent 检查必须遵循）")
    sp.add_argument("--project", required=True, help="项目名（项目级/<项目>）")
    sp.add_argument("--tpl", default="", help="项目模板目录（默认 项目级/<项目>/项目模板）")
    sp.set_defaults(func=cmd_proj_check)

    sp = sub.add_parser("proj-freeze", help="M5：冻结项目模板（登记fb基线+冻结清单，商务标只认冻结版）")
    sp.add_argument("--project", required=True, help="项目名（项目级/<项目>）")
    sp.add_argument("--tpl", default="", help="项目模板目录（默认 项目级/<项目>/项目模板）")
    sp.add_argument("--check", action="store_true", help="冻结审计（对比基线检查是否被改动）")
    sp.add_argument("--note", default="", help="冻结备注")
    sp.set_defaults(func=cmd_proj_freeze)
