# -*- coding: utf-8 -*-
"""
bidcraft · M4 招标文件解析 —— 投标要点 HTML 渲染（纯逻辑，无 I/O）

v2.3+：闸门① 展示形态。输入 投标要点.json + 双通道差异.json，
渲染为单文件 HTML（内联 CSS、无外部依赖、双击可直接打开）。

设计约定：
  - 纯函数 render_report_html(points_doc, diff_doc, generated_date) → str（可单元测试）
  - 数据全部来自输入文档，不硬编码项目内容；已裁决事项块读 points_doc["verdicts"]（v2.4）
  - 9 模块（fields/items/mixed）通用渲染；废标红线独立红色块
"""

import html
from datetime import datetime

TYPE_BADGE = {
    "强制": "badge-red",
    "资格性": "badge-red",
    "符合性": "badge-red",
    "其他": "badge-gray",
}

_KPI_KEYS = [
    ("项目编号", "项目编号"),
    ("最高投标限价", "最高投标限价"),
    ("工程投资估算", "工程投资估算"),
    ("投标截止/开标", "开标时间"),
    ("标的形式", "电子标或纸质标"),
    ("投标方式", "实名制或非实名制"),
    ("评标办法", "评标办法"),
    ("采购方式", "采购方式"),
]


def _ev(v):
    if not v:
        return ""
    return '<div class="ev">出处：%s</div>' % html.escape(v)


def _fld(k, v, evidence=""):
    return ('<div class="fld"><div class="fld-k">%s</div>'
            '<div class="fld-v">%s</div>%s</div>'
            % (html.escape(k), html.escape(v), _ev(evidence)))


def _render_fields(mod):
    return "\n".join(
        _fld(k, v.get("value", "") if isinstance(v, dict) else str(v),
             v.get("evidence", "") if isinstance(v, dict) else "")
        for k, v in (mod.get("fields") or {}).items())


def _render_items(mod):
    lis = []
    for it in mod.get("items") or []:
        typ = it.get("type", "")
        rule = it.get("rule", it.get("event", ""))
        badge = ('<span class="badge %s">%s</span>' % (
            TYPE_BADGE.get(typ, "badge-gray"), html.escape(typ))) if typ else ""
        lis.append("<li>%s<div class='rule'>%s</div>%s</li>"
                   % (badge, html.escape(rule), _ev(it.get("evidence", ""))))
    if lis:
        return "<ul>%s</ul>" % "\n".join(lis)
    return '<div class="empty">无待确认项</div>' if mod.get("id") == "pending" else "<ul></ul>"


def _render_mixed(mod):
    parts = []
    method = mod.get("method") or {}
    if method.get("value"):
        parts.append(_fld("评标方法", method.get("value", ""), method.get("evidence", "")))
    items = mod.get("score_items") or []
    if items:
        trs = []
        for it in items:
            trs.append(
                "<tr><td>%s</td><td class='num'>%s %s</td><td>%s</td><td class='ev-col'>%s</td></tr>"
                % (html.escape(it.get("item", "")), html.escape(str(it.get("weight", ""))),
                   html.escape(it.get("unit", "")), html.escape(it.get("score_rule", "")),
                   html.escape(it.get("evidence", ""))))
        parts.append(
            "<table><thead><tr><th>评分项</th><th>分值</th><th>得分条件</th><th>出处</th></tr></thead>"
            "<tbody>%s</tbody></table>" % "".join(trs))
    return "\n".join(parts)


def _render_module(mod):
    mtype = mod.get("type", "")
    if mtype == "fields":
        body = _render_fields(mod)
    elif mtype == "items":
        body = _render_items(mod)
    elif mtype == "mixed":
        body = _render_mixed(mod)
    else:
        body = ""
    return ('<section class="mod" id="mod-%s"><h2><span class="mod-idx">%s</span>%s</h2>%s</section>'
            % (html.escape(mod.get("id", "")), html.escape(mod.get("id", "")),
               html.escape(mod.get("title", mod.get("id", ""))), body))


def _find_mod(points, mid):
    for m in points.get("modules") or []:
        if m.get("id") == mid:
            return m
    return None


def _basic_fields(points):
    m = _find_mod(points, "basic")
    return (m or {}).get("fields") or {}


def _gv(points, key, default=""):
    v = _basic_fields(points).get(key)
    if isinstance(v, dict):
        return v.get("value", default)
    return v or default


def _kpi_html(points):
    cards = []
    for label, key in _KPI_KEYS:
        v = _gv(points, key)
        if v:
            cards.append('<div class="kpi"><div class="kpi-k">%s</div>'
                         '<div class="kpi-v">%s</div></div>'
                         % (html.escape(label), html.escape(v)))
    return "\n".join(cards)


def _quickview_html(points):
    """核对速览：人员红线 / 报价红线 / 评分结构 / 项目概况（动态提取）。"""
    blocks = []
    staff = _find_mod(points, "staff")
    if staff:
        sf = staff.get("fields") or {}
        for k in ("最低配备数量", "兼职限制", "社保要求"):
            if k in sf:
                v = sf[k]
                blocks.append(_fld("人员配备·%s" % k, v.get("value", ""), v.get("evidence", "")))
    pricing = _find_mod(points, "pricing")
    if pricing:
        pf = pricing.get("fields") or {}
        for k in ("报价上限（废标线）", "费率折算规则"):
            if k in pf:
                v = pf[k]
                blocks.append(_fld("报价·%s" % k, v.get("value", ""), v.get("evidence", "")))
    scoring = _find_mod(points, "scoring")
    if scoring and (scoring.get("method") or {}).get("value"):
        blocks.append(_fld("评分结构", scoring["method"]["value"], scoring["method"].get("evidence", "")))
    pv = _find_mod(points, "project_overview")
    if pv and pv.get("fields", {}).get("项目概况"):
        v = pv["fields"]["项目概况"]
        blocks.append(_fld("项目概况", v.get("value", ""), v.get("evidence", "")))
    return "\n".join(blocks)


def _diff_html(diff_doc):
    rows = []
    for d in (diff_doc or {}).get("diffs") or []:
        rows.append(
            "<tr><td>%s</td><td>%s</td><td>%s</td>"
            "<td><span class='badge badge-diff'>%s</span></td><td class='ev-col'>%s</td></tr>"
            % (html.escape(d.get("解析项", "")), html.escape(d.get("通道A", "")),
               html.escape(d.get("通道B", "")), html.escape(d.get("差异类型", "")),
               html.escape(d.get("建议", ""))))
    if rows:
        return ("<table><thead><tr><th>解析项</th><th>通道A（文档解析）</th>"
                "<th>通道B（语义解析）</th><th>差异类型</th><th>建议</th></tr></thead>"
                "<tbody>%s</tbody></table>" % "".join(rows))
    return '<div class="empty">无差异</div>'


def _verdict_html(points):
    vs = points.get("verdicts") or []
    if not vs:
        return '<div class="empty">无已裁决事项</div>'
    lis = []
    for v in vs:
        date = v.get("date", "")
        lis.append("<li><b>%s</b>：%s%s</li>"
                   % (html.escape(v.get("item", "")), html.escape(v.get("decision", "")),
                      ("（%s）" % html.escape(date)) if date else ""))
    return "<ul>%s</ul>" % "\n".join(lis)


def _red_html(points):
    reject = _find_mod(points, "reject")
    if not reject:
        return ""
    lis = ["<li>%s</li>" % html.escape(it.get("rule", ""))
           for it in reject.get("items") or [] if it.get("rule")]
    if not lis:
        return ""
    return ("<div class='red-block'><h2>废标/否决红线</h2><ul>%s</ul></div>"
            % "\n".join(lis))


_CSS = """* { box-sizing:border-box; margin:0; padding:0; }
body { font-family:"Segoe UI","Microsoft YaHei",Arial,sans-serif; color:#1f2937; background:#f8fafc; line-height:1.65; padding:24px 16px; }
.wrap { max-width:1080px; margin:0 auto; }
header { background:linear-gradient(135deg,#1e3a8a,#2563eb); color:#fff; border-radius:14px; padding:26px 30px; margin-bottom:20px; }
header h1 { font-size:22px; font-weight:600; letter-spacing:.5px; }
header .sub { font-size:13px; opacity:.92; margin-top:8px; }
header .sub b { color:#fde68a; }
h2 { font-size:17px; margin:0 0 12px; padding-bottom:8px; border-bottom:2px solid #e5e7eb; }
h2 .mod-idx { font-family:Consolas,monospace; font-size:12px; color:#1d4ed8; background:#e0e7ff; border-radius:5px; padding:2px 7px; margin-right:8px; vertical-align:2px; }
section.mod { background:#fff; border:1px solid #e5e7eb; border-radius:12px; padding:20px 24px; margin-bottom:16px; }
.kpi-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:12px; }
.kpi { background:#fff; border:1px solid #e5e7eb; border-radius:10px; padding:12px 14px; }
.kpi-k { font-size:12px; color:#6b7280; margin-bottom:4px; }
.kpi-v { font-size:14px; font-weight:600; }
.fld { padding:9px 0; border-bottom:1px dashed #e5e7eb; }
.fld:last-child { border-bottom:none; }
.fld-k { font-weight:600; color:#111827; }
.fld-v { margin-top:2px; }
.ev { font-size:12px; color:#6b7280; margin-top:3px; }
.badge { display:inline-block; font-size:11px; padding:1px 8px; border-radius:10px; margin-right:8px; vertical-align:1px; }
.badge-red { background:#fee2e2; color:#dc2626; }
.badge-gray { background:#f3f4f6; color:#4b5563; }
.badge-diff { background:#fef3c7; color:#b45309; }
ul { list-style:none; }
li { padding:7px 0; border-bottom:1px dashed #e5e7eb; }
li:last-child { border-bottom:none; }
.rule { margin-top:2px; }
.empty { color:#6b7280; font-style:italic; padding:6px 0; }
table { width:100%; border-collapse:collapse; margin-top:10px; font-size:13.5px; }
th,td { border:1px solid #e5e7eb; padding:8px 10px; text-align:left; vertical-align:top; }
th { background:#f1f5f9; font-weight:600; }
tbody tr:nth-child(even) { background:#fafbfc; }
.num { white-space:nowrap; text-align:center; }
.ev-col { color:#6b7280; font-size:12px; }
.red-block { background:#fff7f7; border:1px solid #fecaca; border-radius:12px; padding:18px 22px; margin-bottom:16px; }
.red-block h2 { border-color:#fecaca; color:#dc2626; }
.red-block li { border-bottom:1px dashed #fecaca; }
@media print { body{background:#fff;padding:0} .wrap{max-width:none} header{border-radius:0} section.mod{break-inside:avoid} }"""

_TPL = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>投标要点 · @@PROJECT@@</title>
<style>
@@CSS@@
</style>
</head>
<body>
<div class="wrap">
<header>
  <h1>投标要点 · @@PROJECT@@</h1>
  <div class="sub">项目编号 <b>@@NO@@</b> ｜ 解析通道：<b>通道B（agent 语义解析，M4-招标文件解析-提示词.md v1.1）</b>＋通道A（tender-rule）已核对 ｜ 生成日期 @@DATE@@</div>
</header>

<div class="kpi-grid">@@KPI@@</div>

<section class="mod">
<h2><span class="mod-idx">summary</span>核对速览</h2>
@@QUICK@@
</section>

<section class="mod">
<h2><span class="mod-idx">diff</span>双通道解析差异</h2>
@@DIFF@@
</section>

<section class="mod">
<h2><span class="mod-idx">verdict</span>已裁决事项</h2>
@@VERDICT@@
</section>

@@MODULES@@

@@RED@@

<footer style="text-align:center;color:#6b7280;font-size:12px;padding:18px 0 30px;">
投标要点 · @@PROJECT@@ ｜ 证据出处均标注于各项，以招标原文为最终依据
</footer>
</div>
</body>
</html>"""


def render_report_html(points_doc, diff_doc, generated_date=None):
    """投标要点 JSON + 双通道差异 JSON → 单文件 HTML 字符串。"""
    points = points_doc or {}
    diff = diff_doc or {}
    date = generated_date or datetime.now().strftime("%Y-%m-%d")
    project = html.escape(points.get("project", ""))
    no = html.escape(_gv(points, "项目编号"))
    modules = "\n".join(_render_module(m) for m in points.get("modules") or [])
    red = _red_html(points)
    return (_TPL
            .replace("@@PROJECT@@", project)
            .replace("@@NO@@", no)
            .replace("@@DATE@@", html.escape(date))
            .replace("@@CSS@@", _CSS)
            .replace("@@KPI@@", _kpi_html(points))
            .replace("@@QUICK@@", _quickview_html(points))
            .replace("@@DIFF@@", _diff_html(diff))
            .replace("@@VERDICT@@", _verdict_html(points))
            .replace("@@MODULES@@", modules)
            .replace("@@RED@@", red))
