# -*- coding: utf-8 -*-
"""
bidcraft · M8 AI模拟评标 —— CLI（阶段1：通道A 客观分规则引擎 + 报价分反推）

命令：eval-run
  --project  项目名（项目级/<项目>，M4 解析产物所在）
  --quote    用户报价金额（元，铁律：报价由用户提供；不传则报价分未评）
  --tdir     招标解析目录（默认 项目级/<项目>/招标解析；数据源项目内硬校验）
  --mat      素材清单 json（默认 tdir/素材清单_<项目>.json；项目内硬校验）
  --bid      标书目录（可选，预留阶段2 交叉验证）

产物（项目级/<项目>/模拟评标/）：
  模拟评标_<项目>.json / .md（评分标准结构化 + 客观分明细 + 报价分析 + 失分诊断）
  模拟评标报告_<项目>.html（人工确认闸门）
"""
import argparse
import sys
from pathlib import Path

from _shared import core, naming as nm
from m4_tender import rules as t_rules
from . import eval_std, evaluator, eval_report, rules as m8rules

OUT_DIR_NAME = "模拟评标"


def sim_base(project):
    return "模拟评标_%s" % project


def subjective_base(project):
    return "主观评审_%s" % project


def report_base(project):
    return "模拟评标报告_%s" % project


def _ensure_inside(label, p, proj_dir):
    """数据源项目内硬校验：resolve 后必须位于 项目级/<项目>/ 内，越界即拒绝（项目数据隔离）。"""
    rp = Path(p).resolve()
    pd = Path(proj_dir).resolve()
    try:
        rp.relative_to(pd)
    except ValueError:
        raise core.LibraryError("%s 越界：%s 不在项目目录 %s 内（M8 数据源仅允许指向本项目，禁止跨项目）"
                                % (label, rp, pd))


def _proj_dir(root, enterprise, project):
    pd = Path(root) / enterprise / "项目级" / project
    if not pd.is_dir():
        raise core.LibraryError("项目目录不存在：%s（M8 依赖 M4 解析产物，先执行 M4 招标解析）" % pd)
    return pd


def _load_points(tdir, project):
    p = tdir / ("%s.json" % t_rules.points_base(project))
    if not p.is_file():
        raise core.LibraryError("投标要点 JSON 不存在：%s（M8 依赖 M4 产物，先执行 M4 招标解析）" % p)
    doc = core.read_json(str(p), None)
    if not doc:
        raise core.LibraryError("投标要点 JSON 无法读取：%s" % p)
    return doc


def _load_mat(mat_path):
    doc = core.read_json(str(mat_path), None)
    if not doc:
        raise core.LibraryError("素材清单 JSON 无法读取：%s" % mat_path)
    return doc


def _to_md(project, standard, objective, qa, summary):
    lines = ["# 模拟评标 · %s（通道A 规则引擎，阶段1）" % project, ""]
    lines.append("## 评分办法")
    lines.append(standard["method"])
    lines.append("")
    lines.append("## 客观分明细")
    lines.append("| 评分项 | 满分 | 估得分 | 状态 | 证据 |")
    lines.append("|---|---|---|---|---|")
    for r in objective:
        lines.append("| %s | %.1f | %.1f | %s | %s |" % (r["item"], r["max"], r["score"], r["level"], r["evidence"]))
    lines.append("")
    lines.append("## 报价分析")
    if qa.get("provided"):
        lines.append("报价 %s 元；最高限价 %s 元" % (int(qa["quote"]), int(qa["cap"]) if qa["cap"] else "未知"))
        lines.append(qa["note"])
        for b in qa["bands"]:
            lines.append("- 保住 %.1f 分：基准价 ∈ [%.1f, %.1f] 元" % (b["target"], b["range"][0], b["range"][1]))
        for r in qa["risks"]:
            lines.append("- ⚠️ %s" % r)
    else:
        lines.append(qa.get("note", "未提供报价，报价分未评"))
    lines.append("")
    lines.append("## 失分诊断（优先级从高到低）")
    for it in summary["issues"]:
        gap = it.get("gap")
        lines.append("- %s（失分 %s / 满分 %s）：%s" % (it["item"],
                     ("%.1f" % gap) if gap is not None else "—", it["max"], it["advice"]))
    if not summary["issues"]:
        lines.append("- 客观分无失分缺口（以素材清单为据）。")
    lines.append("")
    lines.append("## 未评项")
    for p in summary["unrated"]:
        lines.append("- %s（%s）：%s" % (p["item"], p["kind"], p["note"]))
    lines.append("")
    lines.append("> 免责：%s" % summary["disclaimer"])
    return "\n".join(lines)


def cmd_eval_run(args):
    root = Path(args.root)
    ent = args.enterprise
    if not ent:
        raise core.LibraryError("请指定 --enterprise（企业名）")
    proj_dir = _proj_dir(root, ent, args.project)

    tdir = Path(args.tdir) if args.tdir else proj_dir / "招标解析"
    _ensure_inside("招标解析目录(--tdir)", tdir, proj_dir)
    if not tdir.is_dir():
        raise core.LibraryError("招标解析目录不存在：%s（先执行 M4 招标解析）" % tdir)

    points = _load_points(tdir, args.project)
    standard = eval_std.parse_scoring(points)

    mat_path = Path(args.mat) if args.mat else tdir / ("%s.json" % t_rules.list_base(args.project))
    _ensure_inside("素材清单(--mat)", mat_path, proj_dir)
    if not mat_path.is_file():
        raise core.LibraryError("素材清单 JSON 不存在：%s" % mat_path)
    mat = _load_mat(mat_path)

    # 报价上限（pricing 模块）
    pricing = None
    for m in (points.get("modules") or []):
        if m.get("id") == "pricing":
            pricing = m
            break
    cap = evaluator.parse_cap(pricing)

    objective = evaluator.calc_objective(standard, mat)

    # 报价分
    quote = None
    if args.quote:
        quote = float(args.quote)
    quote_params = next((p["params"] for p in standard["items"] if p["kind"] == "quote"), {})
    qa = evaluator.quote_analysis(quote, cap, quote_params)

    summary = evaluator.build_summary(standard, objective, quote, qa)

    out_dir = proj_dir / OUT_DIR_NAME
    out_dir.mkdir(parents=True, exist_ok=True)
    base = sim_base(args.project)
    json_path = out_dir / ("%s.json" % base)
    md_path = out_dir / ("%s.md" % base)
    html_path = out_dir / ("%s.html" % report_base(args.project))

    payload = {
        "project": args.project,
        "standard": standard,
        "objective": objective,
        "quote": qa,
        "summary": summary,
    }
    core.write_json(str(json_path), payload)
    md_path.write_text(_to_md(args.project, standard, objective, qa, summary), encoding="utf-8")
    eval_report.render_report(args.project, standard, objective, quote, qa, summary, html_path)
    back = core.read_json(str(json_path), None)
    if not back or back.get("project") != args.project:
        raise core.LibraryError("模拟评标 JSON 写后回读失败：%s" % json_path)
    if not json_path.exists() or not md_path.exists() or not html_path.exists():
        raise core.LibraryError("模拟评标产物落盘不完整（json/md/html）")

    print("模拟评标（通道A）已生成：%s" % json_path)
    print("文本版：%s" % md_path)
    print("HTML 报告：%s（浏览器打开，人工确认闸门）" % html_path)
    print("客观分估分：%.1f / %.1f；报价分：反推参考；主观分：待 M6 精评" % (
        summary["objective_score"], summary["objective_max"]))


def cmd_eval_parse(args):
    """通道B 主观评审产物落盘（agent 按 references/M8-模拟评标-提示词.md 产出，结构校验闸门）。"""
    root = Path(args.root)
    ent = args.enterprise
    if not ent:
        raise core.LibraryError("请指定 --enterprise（企业名）")
    proj_dir = _proj_dir(root, ent, args.project)

    md_path = Path(args.md)
    jf = Path(args.json_file)
    if not md_path.is_file() or not jf.is_file():
        raise core.LibraryError("通道B 主观评审 md/json 必须都存在（按 references/M8-模拟评标-提示词.md 产出）")

    doc = core.read_json(str(jf), None)
    if not doc:
        raise core.LibraryError("主观评审 JSON 无法读取：%s" % jf)
    ok, issues = m8rules.validate_subjective_json(doc)
    if not ok:
        raise core.LibraryError("主观评审 JSON 结构校验未通过：%s" % "；".join(issues))

    out_dir = proj_dir / OUT_DIR_NAME
    out_dir.mkdir(parents=True, exist_ok=True)
    base = subjective_base(args.project)
    dst_json = out_dir / ("%s.json" % base)
    dst_md = out_dir / ("%s.md" % base)
    core.write_json(str(dst_json), doc)
    dst_md.write_text(md_path.read_text(encoding="utf-8"), encoding="utf-8")

    back = core.read_json(str(dst_json), None)
    if not back or back.get("project") != args.project:
        raise core.LibraryError("主观评审 JSON 写后回读失败：%s" % dst_json)
    if not dst_md.exists():
        raise core.LibraryError("主观评审 md 落盘失败：%s" % dst_md)

    print("主观评审（通道B）已落盘：%s" % dst_json)
    print("文本版：%s" % dst_md)
    print("下一步：eval-report 合并通道A+通道B 渲染完整报告（人工确认闸门）")


def cmd_eval_report(args):
    """合并通道A（模拟评标_<项目>.json）+ 通道B（主观评审_<项目>.json）渲染完整模拟评标报告。"""
    root = Path(args.root)
    ent = args.enterprise
    if not ent:
        raise core.LibraryError("请指定 --enterprise（企业名）")
    proj_dir = _proj_dir(root, ent, args.project)
    out_dir = proj_dir / OUT_DIR_NAME

    sim_path = out_dir / ("%s.json" % sim_base(args.project))
    if not sim_path.is_file():
        raise core.LibraryError("通道A 产物不存在：%s（先执行 eval-run）" % sim_path)
    a = core.read_json(str(sim_path), None)
    if not a:
        raise core.LibraryError("通道A 产物无法读取：%s" % sim_path)

    sub_path = out_dir / ("%s.json" % subjective_base(args.project))
    subjective = None
    if sub_path.is_file():
        subjective = core.read_json(str(sub_path), None)
        if subjective:
            ok, issues = m8rules.validate_subjective_json(subjective)
            if not ok:
                raise core.LibraryError("主观评审 JSON 结构异常：%s" % "；".join(issues))
    else:
        print("提示：通道B 主观评审未产出（%s 不存在），报告仅通道A（主观分未评）" % sub_path)

    html_path = out_dir / ("%s.html" % report_base(args.project))
    eval_report.render_report(args.project, a["standard"], a["objective"],
                              a["quote"].get("quote") if a.get("quote") else None,
                              a.get("quote", {}), a["summary"], html_path, subjective=subjective)
    if not html_path.exists():
        raise core.LibraryError("模拟评标报告渲染失败：%s" % html_path)

    total = a["summary"]
    print("模拟评标报告（合并）已生成：%s（浏览器打开，人工确认闸门）" % html_path)
    print("客观分 %.1f/%.1f；主观分 %s；报价分 反推参考（%s）" % (
        total["objective_score"], total["objective_max"],
        ("[%.1f-%.1f]/%.1f" % (subjective["主观合计"]["min"], subjective["主观合计"]["max"],
                                subjective["主观合计"]["满分"])) if subjective else "未评",
        "已评" if a.get("quote", {}).get("provided") else "未评"))


def register_parser(sub):
    sp = sub.add_parser("eval-run", help="M8·阶段1 模拟评标（通道A 规则引擎：评分标准结构化 + 客观分计算 + 报价分反推基准价区间）→ 项目级/<项目>/模拟评标/模拟评标_<项目>.json/.md + HTML 报告")
    sp.add_argument("--project", required=True, help="项目名（项目级/<项目>，M4 解析产物所在）")
    sp.add_argument("--quote", default="", help="用户报价金额（元，铁律：报价由用户提供；不传则报价分未评）")
    sp.add_argument("--tdir", default="", help="招标解析目录（默认 项目级/<项目>/招标解析；数据源须在本项目内）")
    sp.add_argument("--mat", default="", help="素材清单 json（默认 tdir/素材清单_<项目>.json；数据源须在本项目内）")
    sp.add_argument("--bid", default="", help="标书目录（预留：阶段2 标书文本交叉验证用）")
    sp.set_defaults(func=cmd_eval_run)

    sp = sub.add_parser("eval-parse", help="M8·阶段2 通道B 主观评审产物落盘（agent 按 references/M8-模拟评标-提示词.md 产出，JSON 结构校验闸门）→ 模拟评标/主观评审_<项目>.json/.md")
    sp.add_argument("--project", required=True, help="项目名（项目级/<项目>）")
    sp.add_argument("--md", required=True, help="agent 产出的主观评审 md 路径")
    sp.add_argument("--json-file", required=True, help="agent 产出的主观评审 json 路径")
    sp.set_defaults(func=cmd_eval_parse)

    sp = sub.add_parser("eval-report", help="M8·阶段2 合并渲染完整模拟评标报告（通道A 模拟评标_<项目>.json + 通道B 主观评审_<项目>.json）→ 模拟评标报告_<项目>.html（人工确认闸门）")
    sp.add_argument("--project", required=True, help="项目名（项目级/<项目>）")
    sp.set_defaults(func=cmd_eval_report)
