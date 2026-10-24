# -*- coding: utf-8 -*-
"""
bidcraft · M9 取证/自检 —— CLI

命令：
  m9-verify   --project <项目>   一键自检体检（确定性断言：M4 产物齐 / M6 成稿 / M7 检查 /
                                  M8 评标 / M10 补救闭环）→ 自检/自检体检_<项目>.json/.md/.html
  m9-evidence --project <项目>   投标留痕包（M4→M6→M7→M8→M10 全过程产物索引 + 关键状态）
                                  → 自检/投标留痕包_<项目>.json/.md/.html
均写后回读 fail fast；状态判级确定性，人工确认闸门不替代。
"""
import datetime as _dt
from pathlib import Path

from _shared import core

from . import verify

OUT_DIR_NAME = "自检"


def _proj_dir(root, enterprise, project):
    pd = Path(root) / enterprise / "项目级" / project
    if not pd.is_dir():
        raise core.LibraryError("项目目录不存在：%s" % pd)
    return pd


def _out_dir(proj_dir):
    d = proj_dir / OUT_DIR_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def _esc(s):
    if s is None:
        return ""
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


_ST_COLOR = {"绿灯": "#1a7f37", "黄灯": "#b26a00", "红灯": "#c62828"}


def _write_report(doc, out_dir, project, kind):
    base = ("自检体检_%s" if kind == "verify" else "投标留痕包_%s") % project
    json_path = out_dir / ("%s.json" % base)
    md_path = out_dir / ("%s.md" % base)
    html_path = out_dir / ("%s.html" % base)
    core.write_json(str(json_path), doc)
    md_path.write_text(_to_md(doc, kind), encoding="utf-8")
    _render_html(project, doc, kind, html_path)
    back = core.read_json(str(json_path), None)
    if not back or back.get("project") != project:
        raise core.LibraryError("%s 写后回读失败：%s" % (kind, json_path))
    if not md_path.exists() or not html_path.exists():
        raise core.LibraryError("%s 落盘不完整（json/md/html）" % kind)
    return json_path, md_path, html_path


def cmd_m9_verify(args):
    proj_dir = _proj_dir(Path(args.root), args.enterprise, args.project)
    checks, overall, conclusion, ts = verify.run_checks(proj_dir, args.project)
    doc = {"project": args.project, "生成依据": "M9 自检：一键确定性体检（M4→M6→M7→M8→M10 闭环）",
           "生成时间": ts, "总评": overall, "结论": conclusion, "检查明细": checks}
    json_path, _md, html = _write_report(doc, _out_dir(proj_dir), args.project, "verify")
    n = {s: sum(1 for c in checks if c["状态"] == s) for s in ("pass", "warn", "fail")}
    print("自检体检：总评 %s（通过 %d ｜ 可整改 %d ｜ 必做未做 %d）" % (overall, n["pass"], n["warn"], n["fail"]))
    print(conclusion)
    print("报告：%s" % json_path)
    print("HTML：%s（浏览器打开）" % html)
    print("下一步：红灯项补齐 → 重跑 m9-verify；黄灯项整改 → remedy-done/remedy-recheck 闭环后重跑")


def cmd_m9_evidence(args):
    proj_dir = _proj_dir(Path(args.root), args.enterprise, args.project)
    doc = verify.collect_evidence(proj_dir, args.project)
    json_path, _md, html = _write_report(doc, _out_dir(proj_dir), args.project, "evidence")
    print("投标留痕包已生成：%s" % json_path)
    print("HTML：%s（浏览器打开，留痕取证）" % html)
    print("总评 %s ｜ KPI：%s" % (doc["总评"], " ".join("%s=%s" % (k, v) for k, v in doc["KPI"].items() if v is not None)))


def _to_md(doc, kind):
    lines = []
    if kind == "verify":
        lines += ["# 自检体检报告 · %s" % doc.get("project", ""), "",
                  "生成时间：%s ｜ 总评：**%s**" % (doc.get("生成时间", ""), doc.get("总评", "")), "",
                  "> %s" % doc.get("结论", ""), "",
                  "## 检查明细", "| 模块 | 检查 | 状态 | 依据 |", "|---|---|---|---|"]
        for c in doc.get("检查明细", []):
            mark = {"pass": "🟢", "warn": "🟡", "fail": "🔴"}.get(c.get("状态"), "⚪")
            lines.append("| %s | %s | %s %s | %s |" % (c.get("模块"), c.get("检查"),
                                                       mark, c.get("状态"), c.get("依据", "")))
    else:
        lines += ["# 投标留痕包 · %s" % doc.get("project", ""), "",
                  "生成时间：%s ｜ 总评：**%s**" % (doc.get("生成时间", ""), doc.get("总评", "")), "",
                  "> %s" % doc.get("结论", ""), "",
                  "## 关键状态 KPI",
                  "| 指标 | 值 |", "|---|---|"]
        for k, v in (doc.get("KPI") or {}).items():
            lines.append("| %s | %s |" % (k, v if v is not None else "—"))
        lines += ["", "## 全过程产物索引（M4→M6→M7→M8→M10）", "| 模块 | 产物 | 相对路径 | 存在 | 大小 |", "|---|---|---|---|---|"]
        for it in doc.get("产物清单", []):
            lines.append("| %s | %s | `%s` | %s | %s |" % (
                it.get("模块"), it.get("产物"), it.get("相对路径"),
                "✅" if it.get("存在") else "❌", it.get("大小")))
    lines.append("")
    lines.append("> 人工确认闸门：自检/取证为确定性机器检查（产物存在性 + 契约 + 闭环状态）；"
                 "不替代人工终审，最终以评标委员会评审为准。")
    return "\n".join(lines)


def _render_html(project, doc, kind, html_path):
    overall = doc.get("总评", "—")
    color = _ST_COLOR.get(overall, "#555")
    rows = []
    if kind == "verify":
        for c in doc.get("检查明细", []):
            mark = {"pass": "🟢", "warn": "🟡", "fail": "🔴"}.get(c.get("状态"), "⚪")
            sc = {"pass": "#1a7f37", "warn": "#b26a00", "fail": "#c62828"}.get(c.get("状态"), "#555")
            rows.append("<tr><td>%s</td><td>%s</td><td><span style='color:%s;font-weight:700'>%s %s</span></td>"
                        "<td>%s</td></tr>" % (c.get("模块"), c.get("检查"), sc, mark, c.get("状态"), _esc(c.get("依据"))))
        table = ("<table><tr style='background:#f1f3f4'><th>模块</th><th>检查</th><th>状态</th><th>依据</th></tr>%s</table>"
                 % "".join(rows))
        kpi = ""
    else:
        kpi_rows = ["<tr style='background:#f1f3f4'><th>指标</th><th>值</th></tr>"]
        for k, v in (doc.get("KPI") or {}).items():
            kpi_rows.append("<tr><td>%s</td><td>%s</td></tr>" % (_esc(k), _esc(v if v is not None else "—")))
        kpi = "<h3>关键状态 KPI</h3><table>%s</table>" % "".join(kpi_rows)
        for it in doc.get("产物清单", []):
            rows.append("<tr><td>%s</td><td>%s</td><td><code>%s</code></td><td>%s</td><td>%s</td></tr>" % (
                it.get("模块"), it.get("产物"), _esc(it.get("相对路径")),
                "✅" if it.get("存在") else "❌", it.get("大小")))
        table = ("<h3>全过程产物索引（M4→M6→M7→M8→M10）</h3>"
                 "<table><tr style='background:#f1f3f4'><th>模块</th><th>产物</th><th>相对路径</th><th>存在</th><th>大小</th></tr>%s</table>"
                 % "".join(rows))

    title = "自检体检报告" if kind == "verify" else "投标留痕包"
    html = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>%s · %s</title>
<style>
 body{font-family:SimSun,serif;color:#222;margin:24px auto;max-width:960px;padding:0 16px}
 h1{font-size:20px;text-align:center;margin:8px 0}
 .meta{text-align:center;color:#666;font-size:13px;margin-bottom:14px}
 .verdict{text-align:center;font-size:22px;font-weight:700;margin:10px 0 4px}
 .concl{text-align:center;color:#555;font-size:14px;margin-bottom:16px}
 table{width:100%%;border-collapse:collapse;font-size:13px;margin-bottom:16px}
 th,td{border:1px solid #d0d7de;padding:6px 8px;text-align:left;vertical-align:top}
 code{background:#f6f8fa;padding:0 4px;border-radius:3px}
 .foot{margin-top:16px;font-size:12px;color:#666;border-top:1px solid #e1e4e8;padding-top:8px}
</style></head><body>
<h1>%s · %s</h1>
<div class="meta">生成时间：%s</div>
<div class="verdict" style="color:%s">%s</div>
<div class="concl">%s</div>
%s
<div class="foot">人工确认闸门：自检/取证为确定性机器检查（产物存在性 + 契约 + 闭环状态）；不替代人工终审，最终以评标委员会评审为准。</div>
</body></html>""" % (
        title, _esc(project), title, _esc(project), _esc(doc.get("生成时间", "")),
        color, _esc(overall), _esc(doc.get("结论", "")), kpi + table)
    html_path.write_text(html, encoding="utf-8")


def register_parser(sub):
    sp = sub.add_parser("m9-verify", help="M9 自检：一键确定性体检（M4 产物齐/M6 成稿/M7 检查/M8 评标/M10 补救闭环）→ 自检/自检体检_<项目>.json/.md/.html（红绿灯）")
    sp.add_argument("--project", required=True, help="项目名")
    sp.set_defaults(func=cmd_m9_verify)

    sp2 = sub.add_parser("m9-evidence", help="M9 取证：投标留痕包（M4→M6→M7→M8→M10 全过程产物索引 + 关键状态 KPI）→ 自检/投标留痕包_<项目>.json/.md/.html")
    sp2.add_argument("--project", required=True, help="项目名")
    sp2.set_defaults(func=cmd_m9_evidence)
