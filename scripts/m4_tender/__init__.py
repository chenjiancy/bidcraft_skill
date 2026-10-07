# -*- coding: utf-8 -*-
"""
bidcraft · M4 招标文件解析 —— CLI（命令实现 + 子命令注册）

用法总览（示例）
----------------
  # 0) 初始化项目级招标解析目录（幂等；须先有企业，见 M1 init-enterprise）
  python bidcraft.py tender-init --project "XX安置房项目监理"

  # 1) 提取招标文件原文（DOCX/TXT/MD/PDF 内置；PDF 走 PyMuPDF 表格/多栏感知提取；
  #    --text-file 仅作图片/纯扫描件等回退）
  python bidcraft.py tender-extract --project "XX安置房项目监理" --file "D:/下载/招标文件.docx"
  python bidcraft.py tender-extract --project "XX安置房项目监理" --file "D:/下载/招标文件.pdf"
  python bidcraft.py tender-extract --project "XX安置房项目监理" --text-file "D:/下载/招标文件_文本.txt"

  # 2) agent 完成语义解析后，提交双份产物落盘（文本 + JSON，须按操作手册模板）
  python bidcraft.py tender-parse --project "XX安置房项目监理" \
      --points-md "投标要点.md" --points-json "投标要点.json" \
      --list-md "素材清单.md" --list-json "素材清单.json"

  # 3) 素材对照：逐项查素材库 → 素材对照_<项目>.csv + 缺料标红报告
  python bidcraft.py tender-check --project "XX安置房项目监理"

  # 4) 人读查看
  python bidcraft.py tender-show --project "XX安置房项目监理"

数据落位（项目级）：<软件根>/<企业>/项目级/<项目名>/招标解析/
解析主体：agent（脚本不承担语义解析，只做编排与存取）。
"""

import argparse
import json
import os
import sys
from pathlib import Path

from _shared import core            # noqa: E402
from . import rules, tender         # noqa: E402

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


def get_ent(args):
    lib = core.Library(lib_root(args))
    return lib.resolve(getattr(args, "enterprise", None))


def dump(obj, args, human=""):
    if getattr(args, "json", False):
        print(json.dumps(obj, ensure_ascii=False, indent=2))
    else:
        print(human if human else json.dumps(obj, ensure_ascii=False, indent=2))


def table(rows, headers):
    """极简等宽表（中文按 2 列宽估算，与 M1 一致）。"""
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


# --------------------------------------------------------------------------
# 命令实现
# --------------------------------------------------------------------------
def cmd_tender_init(args):
    ent = get_ent(args)
    tdir = tender.ensure_project_dir(ent, args.project)
    obj = {"ok": True, "project": args.project, "path": str(tdir)}
    dump(obj, args, human=(
        "已初始化项目招标解析目录（幂等）：\n  %s\n"
        "下一步：tender-extract 提取原文 → agent 解析 → tender-parse 落盘产物 → tender-check 素材对照"
        % tdir
    ))


def cmd_tender_extract(args):
    ent = get_ent(args)
    tdir = tender.ensure_project_dir(ent, args.project)
    archived = None
    if args.file:
        # 1) 归档原件（任意格式：PDF/DOCX/图片等）→ 源文件/
        dst, created = tender.archive_source(tdir, args.project, args.file)
        archived = {"path": str(dst), "created": created, "name": dst.name}
        stem = Path(args.file).stem
        # 2) 提取正文：DOCX/TXT/MD/PDF 内置（PDF=PyMuPDF 表格/多栏感知，④）；
        #    图片/纯扫描件等需 agent 以 --text-file 提供
        try:
            text = tender.extract_text_file(args.file)
            kind = "auto"
        except core.LibraryError as e:
            if args.text_file:
                text = tender.read_text(args.text_file)
                kind = "text(agent 提取)"
            else:
                raise core.LibraryError(
                    "%s；原件已归档至 源文件/，请 agent 提取正文后补传 --text-file" % e)
    elif args.text_file:
        text = tender.read_text(args.text_file)
        stem = Path(args.text_file).stem
        kind = "text(agent 提取)"
    else:
        raise core.LibraryError("请提供 --file（招标文件原件，自动归档）或 --text-file（已提取文本）")
    rel = tender.write_original(tdir, stem, text)
    obj = {"ok": True, "project": args.project, "original": rel, "kind": kind,
           "chars": len(text), "lines": len(text.splitlines()), "archived": archived}
    dump(obj, args, human=(
        "原文已提取并保存（%s）：%s（%d 字符 / %d 行）%s\n"
        "下一步：agent 通读原文 → 按操作手册生成投标要点/素材清单（文本+JSON）→ tender-parse 落盘"
        % (kind, tdir / rel, len(text), len(text.splitlines()),
           "\n原件已归档：%s" % (tdir / "源文件" / archived["name"]) if archived else "")
    ))


def cmd_tender_parse(args):
    ent = get_ent(args)
    tdir = tender.ensure_project_dir(ent, args.project)
    md_p, json_p = tender.save_points(tdir, args.project, args.points_md, args.points_json)
    md_l, json_l = tender.save_list(tdir, args.project, args.list_md, args.list_json)
    obj = {"ok": True, "project": args.project,
           "points_md": str(md_p), "points_json": str(json_p),
           "list_md": str(md_l), "list_json": str(json_l)}
    dump(obj, args, human=(
        "产物已落盘（双份：人读文本 + 机读 JSON）：\n"
        "  投标要点：%s\n          %s\n"
        "  素材清单：%s\n          %s\n"
        "下一步：tender-check --project \"%s\" 对照素材库（缺料标红）"
        % (md_p, json_p, md_l, json_l, args.project)
    ))


def cmd_tender_check(args):
    ent = get_ent(args)
    tdir = tender.ensure_project_dir(ent, args.project)
    rows, summary, csv_name = tender.run_check(ent, tdir, args.project)
    obj = {"ok": True, "project": args.project, "csv": csv_name,
           "rows": rows, "summary": summary}
    if args.json:
        print(json.dumps(obj, ensure_ascii=False, indent=2))
    else:
        t = [[r["category"], r["subtype"], "、".join(r["keywords"]),
              r["purpose"], "必须" if r["required"] else "加分", r["status"],
              "、".join(r["paths"][:2]) or "-"] for r in rows]
        print("项目：%s　素材对照（%d 项）\n" % (args.project, len(rows)))
        print(table(t, ["大类", "子类", "关键字", "用途", "必须/加分", "状态", "命中素材"]))
        print("\n汇总：共 %d 项｜✅已有 %d｜🔴必缺 %d｜⚠️加分缺 %d" % (
            summary["total"], summary["have"], summary["missing_required"], summary["missing_bonus"]))
        if summary["redlines"]:
            print("\n🔴 废标风险（必缺项，需立即补充）：%s" % "、".join(summary["redlines"]))
        print("\n对照表已写入：%s\n缺料补充请确认后反馈给 agent 更新素材库/清单。" % (tdir / csv_name))


def cmd_tender_fmt(args):
    """v2.1：响应文件格式章节脚本化提取 → 响应文件格式_<项目>.txt（一字不改）。"""
    ent = get_ent(args)
    tdir = tender.ensure_project_dir(ent, args.project)
    r = tender.extract_fmt(tdir, args.project, getattr(args, "start", None),
                           getattr(args, "end", None))
    dump(r, args, human=(
        "响应文件格式已提取（切片 %d–%d 行，共 %d 行 / %d 字符，与原文逐行一致）：\n  %s\n"
        "下一步：本文件是内容地基，供 M2 项目模板生成时做内容校验（D25）；一字不改，除非人工修改。"
        % (r["start"], r["end"], r["lines"], r["chars"], r["path"])
    ))


def cmd_tender_rule(args):
    """v2.1：通道A 文档解析——规则引擎从原文抽取确定性字段 → 文档解析_<项目>.json。"""
    ent = get_ent(args)
    tdir = tender.ensure_project_dir(ent, args.project)
    r = tender.run_rule_extract(tdir, args.project)
    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return
    print("通道A 文档解析（规则引擎）已落盘：%s（%d 个字段）" % (r["path"], r["count"]))
    rows = []
    for f in r["fields"].values():
        v = "、".join(f["value"]) if isinstance(f["value"], list) else str(f["value"])
        if "lines" in f:
            ln = "、".join(str(x) for x in f["lines"][:5])
        else:
            ln = f.get("note", "")
        rows.append([f.get("label", ""), f.get("module", ""), v, ln])
    print("\n" + table(rows, ["字段", "模块", "值", "原文行"]))
    print("\n下一步：tender-diff --project \"%s\" 做双通道差异比对（通道A vs 通道B 投标要点）" % args.project)


def cmd_tender_diff(args):
    """v2.1：双通道差异比对：文档解析.json vs 投标要点.json → 差异清单。"""
    ent = get_ent(args)
    tdir = tender.ensure_project_dir(ent, args.project)
    diffs, md_p, json_p = tender.run_dual_diff(tdir, args.project)
    if args.json:
        print(json.dumps({"project": args.project, "diffs": diffs}, ensure_ascii=False, indent=2))
        return
    print("双通道解析差异：共 %d 项（通道A 文档解析 vs 通道B 语义解析）\n" % len(diffs))
    if not diffs:
        print("（两通道对已抽取确定性字段无实质差异）")
    for i, d in enumerate(diffs, 1):
        print("%d. [%s] %s" % (i, d["差异类型"], d["解析项"]))
        print("   通道A：%s" % d["通道A"])
        print("   通道B：%s" % d["通道B"])
    print("\n差异清单已落盘：\n  %s\n  %s" % (md_p, json_p))
    print("提示：差异并入投标要点 diffs 块（由 agent 合并），以招标原文为最终依据，用户裁决。")


def cmd_tender_show(args):
    ent = get_ent(args)
    tdir = tender.project_tender_dir(ent, args.project)
    if args.what == "check":
        list_json = tdir / ("%s.json" % rules.list_base(args.project))
        if not list_json.exists():
            raise core.LibraryError("尚未执行 tender-check/parse：%s" % list_json)
        doc = tender.load_doc(list_json)
        items = doc.get("items", []) if doc else []
        rows = rules.build_check_rows(items, tender._hit_fn(ent))
        summary = rules.summarize(rows)
        print(rules.render_check_text(rows, summary, args.project))
        return
    if args.what == "list":
        f = tdir / ("%s.md" % rules.list_base(args.project))
    else:
        f = tdir / ("%s.md" % rules.points_base(args.project))
    if not f.exists():
        raise core.LibraryError("产物不存在：%s（先执行 tender-parse）" % f)
    print(f.read_text(encoding="utf-8"))


def cmd_tender_report(args):
    """v2.3：投标要点 HTML 渲染（闸门① 核对形态）→ 投标要点_<项目>.html。"""
    ent = get_ent(args)
    tdir = tender.ensure_project_dir(ent, args.project)
    r = tender.render_report(tdir, args.project)
    dump(r, args, human=(
        "投标要点 HTML 已生成（%d 字符）：\n  %s\n"
        "打开方式：浏览器打开该文件核对（闸门①）；与 md/json 同源渲染，逐项核对 9 模块、"
        "双通道差异、已裁决事项、废标红线。" % (r["chars"], r["path"])
    ))


def cmd_tender_annex(args):
    """v2.4：补遗/澄清/修改文件归档 + 原文提取 → 补遗/ + 补遗原文_<项目>_<n>.txt。"""
    ent = get_ent(args)
    tdir = tender.ensure_project_dir(ent, args.project)
    r = tender.run_annex(tdir, args.project, args.file, args.type)
    dump(r, args, human=(
        "补遗（%s）已归档并提取正文：\n  原件：%s\n  正文：%s（%d 行）\n"
        "下一步：agent 按提示词【补遗/澄清比对】与原文件逐条比对，输出对投标人影响对照表，"
        "并以补遗后的要求为准更新相关模块（投标要点重新落盘）。"
        % (r["type"], r["path"], r["text_path"], r["lines"])
    ))


# --------------------------------------------------------------------------
# 子命令注册（由薄壳 bidcraft.py 调用）
# --------------------------------------------------------------------------
def register_parser(sub):
    sp = sub.add_parser("tender-init", help="M4：初始化项目级招标解析目录（幂等）")
    sp.add_argument("--project", required=True, help="投标项目名（禁路径分隔符）")
    sp.set_defaults(func=cmd_tender_init)

    sp = sub.add_parser("tender-extract", help="M4：归档招标文件原件（源文件/）并提取原文（DOCX/TXT/MD/PDF 内置；PDF=PyMuPDF 表格/多栏感知；图片/扫描件配 --text-file）")
    sp.add_argument("--project", required=True)
    sp.add_argument("--file", help="招标文件原件路径（任意格式，自动归档到 源文件/）")
    sp.add_argument("--text-file", help="已提取文本路径（PDF/图片场景，agent 提取后传入）")
    sp.set_defaults(func=cmd_tender_extract)

    sp = sub.add_parser("tender-parse", help="M4：提交 agent 解析产物落盘（投标要点/素材清单，文本+JSON 双份）")
    sp.add_argument("--project", required=True)
    sp.add_argument("--points-md", required=True, help="投标要点.md 路径（agent 产出）")
    sp.add_argument("--points-json", required=True, help="投标要点.json 路径（机读，供 M5/M7）")
    sp.add_argument("--list-md", required=True, help="素材清单.md 路径（agent 产出）")
    sp.add_argument("--list-json", required=True, help="素材清单.json 路径（机读）")
    sp.set_defaults(func=cmd_tender_parse)

    sp = sub.add_parser("tender-check", help="M4：素材清单逐项对照素材库 → 对照表 CSV + 缺料标红")
    sp.add_argument("--project", required=True)
    sp.set_defaults(func=cmd_tender_check)

    sp = sub.add_parser("tender-fmt", help="M4·v2.1：响应文件格式章节脚本化提取 → 响应文件格式_<项目>.txt（一字不改；--start/--end 可覆盖 1 基行号）")
    sp.add_argument("--project", required=True)
    sp.add_argument("--start", type=int, help="起始行号（1 基，自动定位失败时指定）")
    sp.add_argument("--end", type=int, help="结束行号（1 基，含；默认定位到下一章或文件尾）")
    sp.set_defaults(func=cmd_tender_fmt)

    sp = sub.add_parser("tender-rule", help="M4·v2.1：通道A 文档解析（规则引擎）→ 文档解析_<项目>.json（确定性字段）")
    sp.add_argument("--project", required=True)
    sp.set_defaults(func=cmd_tender_rule)

    sp = sub.add_parser("tender-diff", help="M4·v2.1：双通道差异比对（通道A 文档解析 vs 通道B 投标要点）→ 双通道差异_<项目>.json/.md")
    sp.add_argument("--project", required=True)
    sp.set_defaults(func=cmd_tender_diff)

    sp = sub.add_parser("tender-show", help="M4：人读查看解析产物（默认投标要点）")
    sp.add_argument("--project", required=True)
    sp.add_argument("--what", choices=("points", "list", "check"), default="points",
                    help="points=投标要点 / list=素材清单 / check=素材对照（默认 points）")
    sp.set_defaults(func=cmd_tender_show)

    sp = sub.add_parser("tender-report", help="M4·v2.3：投标要点 HTML 渲染（闸门① 核对形态）→ 投标要点_<项目>.html")
    sp.add_argument("--project", required=True)
    sp.set_defaults(func=cmd_tender_report)

    sp = sub.add_parser("tender-annex", help="M4·v2.4：补遗/澄清/修改文件归档（补遗/）并提取正文 → 供 agent 跨文件比对")
    sp.add_argument("--project", required=True)
    sp.add_argument("--file", required=True, help="补遗/澄清/修改文件路径（DOCX/TXT/MD/PDF 内置；图片配 --text-file 由 agent 提取）")
    sp.add_argument("--type", choices=("补遗", "澄清", "修改"), default="补遗",
                    help="文件类型（默认 补遗）")
    sp.set_defaults(func=cmd_tender_annex)
