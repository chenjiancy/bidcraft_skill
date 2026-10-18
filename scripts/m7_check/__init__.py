# -*- coding: utf-8 -*-
"""
bidcraft · M7 标书检查 —— 命令实现 + 子命令注册

v2.0 双通道检查（对齐 M4 招标解析双通道架构）：
  - check-rule    通道A：机器检查规则引擎（checker 6 项硬检查 + 报价/证书/期限/素材核对）
  - check-parse   通道B：agent 语义审查产物落盘（按 references/M7-标书检查-提示词.md）
  - check-diff    双通道差异比对（通道A vs 通道B → 人工裁决）
  - check-report  HTML 报告渲染（人工确认闸门）
  - m7-check      旧命令（保留兼容：仅跑 checker 6 项硬检查）

产物落位：<企业>/项目级/<项目>/标书检查/
"""

import argparse
import json
import os
import sys
from pathlib import Path

from _shared import core            # noqa: E402
from . import checker as m7         # noqa: E402
from . import check_report, rule_check, rules as m7rules   # noqa: E402

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


def _proj_dir(args):
    ent = get_ent(args)
    proj = ent / "项目级" / args.project
    if not proj.is_dir():
        print("错误：项目目录不存在：%s" % proj, file=sys.stderr)
        raise SystemExit(1)
    return proj


def _check_dir(proj):
    cdir = proj / m7rules.check_subdir()
    cdir.mkdir(parents=True, exist_ok=True)
    return cdir


def _load(proj, base_fn, label, must=True):
    cdir = _check_dir(proj)
    p = cdir / ("%s.json" % base_fn(proj.name))
    if not p.is_file():
        if not must:
            return None, cdir
        print("错误：%s 不存在：%s（先执行 %s）" % (label, p, "check-rule/check-parse" if label != "双通道差异" else "check-rule+check-parse"), file=sys.stderr)
        raise SystemExit(1)
    doc = core.read_json(str(p), None)
    if doc is None:
        print("错误：%s 无法读取：%s" % (label, p), file=sys.stderr)
        raise SystemExit(1)
    return doc, cdir


# --------------------------------------------------------------------------
# check-rule：通道A 机器检查
# --------------------------------------------------------------------------
def cmd_check_rule(args):
    proj = _proj_dir(args)
    res = rule_check.run_rule_checks(get_ent(args), proj,
                                     out_dir=args.out or None,
                                     tpl_dir=args.tpl or None,
                                     tdir=args.tdir or None)
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return
    print("M7 通道A 机器检查总判定：%s" % ("全部通过 ✓" if res["ok"] else "存在未通过项 ✗"))
    for r in res["检查"]:
        mark = "✓" if r["ok"] else "✗"
        print("  [%s] %s（%s） 问题 %d 条" % (mark, r["name"], r["level"], len(r["issues"])))
        for x in r["issues"][:6]:
            print("      - %s" % x)
        if len(r["issues"]) > 6:
            print("      … 共 %d 条，详见报告" % len(r["issues"]))
    print("落盘：%s" % res["json"])


# --------------------------------------------------------------------------
# check-parse：通道B agent 产物落盘（校验 + 双份写入 + 回读）
# --------------------------------------------------------------------------
def cmd_check_parse(args):
    proj = _proj_dir(args)
    md_path, json_path = Path(args.md), Path(args.json_file)
    if not md_path.exists():
        print("错误：agent 产物文本不存在：%s" % md_path, file=sys.stderr)
        raise SystemExit(1)
    if not json_path.exists():
        print("错误：agent 产物 JSON 不存在：%s" % json_path, file=sys.stderr)
        raise SystemExit(1)
    doc = core.read_json(str(json_path), None)
    if doc is None:
        print("错误：产物 JSON 不是合法 JSON：%s" % json_path, file=sys.stderr)
        raise SystemExit(1)
    ok, issues = m7rules.validate_check_json(doc)
    if not ok:
        print("错误：检查要点 JSON 结构校验失败：\n  - %s" % "\n  - ".join(issues), file=sys.stderr)
        raise SystemExit(1)
    cdir = _check_dir(proj)
    base = m7rules.points_base(proj.name)
    md_dst = cdir / ("%s.md" % base)
    json_dst = cdir / ("%s.json" % base)
    # 与 M4 一致：md 内容由 agent 保证与 json 一致，双份落盘
    md_dst.write_text(Path(md_path).read_text(encoding="utf-8"), encoding="utf-8")
    json_dst.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    core.readback.verify_file(md_dst, label="检查要点 md")
    core.readback.verify_json(json_dst, required_fields=("project", "结论"), label="检查要点 json")
    print("通道B 检查要点已落盘：%s / %s" % (md_dst, json_dst))
    print("结论：%s（须人工确认后进入 check-diff / check-report）" % doc.get("结论"))


# --------------------------------------------------------------------------
# check-diff：双通道差异比对
# --------------------------------------------------------------------------
def cmd_check_diff(args):
    proj = _proj_dir(args)
    machine, cdir = _load(proj, m7rules.machine_base, "机器检查")
    check, _ = _load(proj, m7rules.points_base, "检查要点")
    diffs = m7rules.compare_dual(machine, check)
    doc = {"project": proj.name, "channel": "diff",
           "note": "双通道检查差异（通道A 机器检查 vs 通道B agent 语义审查）",
           "diffs": diffs, "generated": core.now_iso()}
    base = m7rules.diff_base(proj.name)
    json_path = cdir / ("%s.json" % base)
    md_path = cdir / ("%s.md" % base)
    md_lines = ["# 双通道检查差异 · %s" % proj.name, "",
                "- 通道A：机器检查（check-rule）｜通道B：agent 语义审查（check-parse）",
                "- 差异类型：遗漏提示 / 结论冲突 / 仅通道B（语义审查）",
                "- 裁决：以招标原文与投标文件原文件为最终依据，人工确认后方可定稿", ""]
    if not diffs:
        md_lines.append("（两通道无实质差异）")
    for i, d in enumerate(diffs, 1):
        md_lines.append("%d. [%s] %s" % (i, d.get("差异类型"), d.get("检查项") or d.get("维度")))
        md_lines.append("   通道A：%s" % d.get("通道A"))
        md_lines.append("   通道B：%s" % d.get("通道B"))
        md_lines.append("   建议：%s" % d.get("建议"))
    json_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text("\n".join(md_lines), encoding="utf-8")
    core.readback.verify_json(json_path, required_fields=("project", "diffs"), label="双通道检查差异 json")
    core.readback.verify_file(md_path, label="双通道检查差异 md")
    if args.json:
        print(json.dumps(doc, ensure_ascii=False, indent=2))
        return
    print("双通道差异：%d 条（%s）" % (len(diffs), "无差异" if not diffs else "须人工裁决"))
    for d in diffs:
        print("  [%s] %s：A=%s | B=%s" % (d.get("差异类型"), d.get("检查项"),
                                          (d.get("通道A") or "")[:60], (d.get("通道B") or "")[:60]))
    print("落盘：%s / %s" % (json_path, md_path))


# --------------------------------------------------------------------------
# check-report：HTML 报告渲染
# --------------------------------------------------------------------------
def cmd_check_report(args):
    proj = _proj_dir(args)
    machine, cdir = _load(proj, m7rules.machine_base, "机器检查")
    check, _ = _load(proj, m7rules.points_base, "检查要点", must=not args.allow_missing_b)
    diff, _ = _load(proj, m7rules.diff_base, "双通道检查差异", must=not args.allow_missing_b)
    html_text = check_report.render_report_html(
        machine, check or {}, diff or {}, core.now_iso()[:10])
    dst = cdir / ("%s.html" % m7rules.report_base(proj.name))
    dst.write_text(html_text, encoding="utf-8")
    core.readback.verify_file(dst, label="标书检查报告 html")
    print("标书检查报告已生成：%s（浏览器打开，人工确认闸门）" % dst)
    if args.json:
        print(json.dumps({"path": str(dst), "chars": len(html_text)}, ensure_ascii=False))


# --------------------------------------------------------------------------
# 旧命令 m7-check（保留兼容）
# --------------------------------------------------------------------------
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
    print("报告：%s（v2.0 起推荐 check-rule 双通道通道A）" % res["目录"])


def register_parser(sub):
    # ---- 双通道（v2.0）----
    sp = sub.add_parser("check-rule", help="M7·v2.0 通道A：机器检查规则引擎（checker 6 项硬检查 + 报价/证书/期限/素材确定性核对，标准=M4 解析产物）→ 标书检查/机器检查_<项目>.json/.md")
    sp.add_argument("--project", required=True, help="项目名（项目级/<项目>）")
    sp.add_argument("--out", default="", help="商务标输出目录（默认 项目级/<项目>/商务标）")
    sp.add_argument("--tpl", default="", help="项目模板目录（默认 项目级/<项目>/项目模板）")
    sp.add_argument("--tdir", default="", help="招标解析目录（默认 项目级/<项目>/招标解析，M4 产物所在地）")
    sp.set_defaults(func=cmd_check_rule)

    sp = sub.add_parser("check-parse", help="M7·v2.0 通道B：agent 语义审查产物落盘（按 references/M7-标书检查-提示词.md 产出，文本+JSON 双份，结构校验）")
    sp.add_argument("--project", required=True, help="项目名（项目级/<项目>）")
    sp.add_argument("--md", required=True, help="agent 产出的检查要点 md 路径")
    sp.add_argument("--json-file", required=True, help="agent 产出的检查要点 json 路径")
    sp.set_defaults(func=cmd_check_parse)

    sp = sub.add_parser("check-diff", help="M7·v2.0 双通道差异比对（通道A 机器检查 vs 通道B 检查要点）→ 双通道检查差异_<项目>.json/.md（人工裁决）")
    sp.add_argument("--project", required=True, help="项目名（项目级/<项目>）")
    sp.set_defaults(func=cmd_check_diff)

    sp = sub.add_parser("check-report", help="M7·v2.0 标书检查 HTML 报告渲染（执行摘要/差异/通道A/通道B/废标红线/整改清单/免责）→ 标书检查报告_<项目>.html（人工确认闸门）")
    sp.add_argument("--project", required=True, help="项目名（项目级/<项目>）")
    sp.add_argument("--allow-missing-b", action="store_true",
                    help="允许通道B/差异未产出时仍渲染（仅通道A 报告）")
    sp.set_defaults(func=cmd_check_report)

    # ---- 旧命令（v1.0 保留兼容）----
    sp = sub.add_parser("m7-check", help="M7·v1.0：交标前质量检查（格式完整性/占位符清零/敏感残留等 6 项硬检查）")
    sp.add_argument("--project", required=True, help="项目名（项目级/<项目>）")
    sp.add_argument("--out", default="", help="商务标输出目录（默认 项目级/<项目>/商务标）")
    sp.add_argument("--tpl", default="", help="项目模板目录（默认 项目级/<项目>/项目模板）")
    sp.set_defaults(func=cmd_m7_check)
