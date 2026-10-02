# -*- coding: utf-8 -*-
"""
bidcraft · M4 招标文件解析 —— CLI（命令实现 + 子命令注册）

用法总览（示例）
----------------
  # 0) 初始化项目级招标解析目录（幂等；须先有企业，见 M1 init-enterprise）
  python bidcraft.py tender-init --project "XX安置房项目监理"

  # 1) 提取招标文件原文（DOCX/TXT/MD 内置；PDF/图片由 agent 提取后 --text-file 传入）
  python bidcraft.py tender-extract --project "XX安置房项目监理" --file "D:/下载/招标文件.docx"
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
        # 2) 提取正文：DOCX/TXT/MD 内置；PDF/图片需 agent 以 --text-file 提供
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


# --------------------------------------------------------------------------
# 子命令注册（由薄壳 bidcraft.py 调用）
# --------------------------------------------------------------------------
def register_parser(sub):
    sp = sub.add_parser("tender-init", help="M4：初始化项目级招标解析目录（幂等）")
    sp.add_argument("--project", required=True, help="投标项目名（禁路径分隔符）")
    sp.set_defaults(func=cmd_tender_init)

    sp = sub.add_parser("tender-extract", help="M4：归档招标文件原件（源文件/）并提取原文（DOCX/TXT/MD 内置；PDF/图片配 --text-file）")
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

    sp = sub.add_parser("tender-show", help="M4：人读查看解析产物（默认投标要点）")
    sp.add_argument("--project", required=True)
    sp.add_argument("--what", choices=("points", "list", "check"), default="points",
                    help="points=投标要点 / list=素材清单 / check=素材对照（默认 points）")
    sp.set_defaults(func=cmd_tender_show)
