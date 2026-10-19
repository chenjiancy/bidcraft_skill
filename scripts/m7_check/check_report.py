# -*- coding: utf-8 -*-
"""
bidcraft · M7 标书检查 —— HTML 报告渲染（check-report，人工确认闸门展示形态）

输入（标书检查/ 目录）：
  - 机器检查_<项目>.json         （通道A）
  - 检查要点_<项目>.json         （通道B，agent 产物）
  - 双通道检查差异_<项目>.json   （check-diff 产物）
输出：标书检查报告_<项目>.html（单文件，浏览器打开核对）

复刻 m4_tender/tender_report.py 的 _TPL+_CSS+replace 渲染模式。
"""
import html
from datetime import datetime

_TPL = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>标书检查报告 · @@PROJECT@@</title>
<style>@@CSS@@</style>
</head>
<body>
<div class="wrap">
  <div class="head">
    <h1>M7 标书检查报告</h1>
    <div class="meta">项目：@@PROJECT@@ ｜ 审查日期：@@DATE@@ ｜ 双通道：通道A 机器检查 + 通道B agent 语义审查</div>
  </div>

  <div class="card">
    <h2>一、执行摘要</h2>
    @@KPI@@
  </div>

  <div class="card">
    <h2>二、双通道差异（人工裁决）</h2>
    @@DIFF@@
  </div>

  <div class="card">
    <h2>三、通道A · 机器检查明细</h2>
    @@MACHINE@@
  </div>

  <div class="card">
    <h2>四、通道B · 语义审查明细</h2>
    @@CHECKDETAIL@@
  </div>

  <div class="card">
    <h2>五、废标红线核对</h2>
    @@REDLINE@@
  </div>

  <div class="card">
    <h2>六、整改清单（补正方向，不替写内容）</h2>
    @@FIXES@@
  </div>

  <div class="foot">
    <h2>审查局限与人工复核（强制）</h2>
    <ul>
      <li>所有 🔴/🟠 项及标注的页码、条款原文，必须由人工回到原文件逐字核对（AI 偶尔标错页码或张冠李戴）。</li>
      <li>行业常识判断（门槛/加分/决胜点）必须由人做，AI 只做事实核对。</li>
      <li>本报告为辅助工具，不构成法律意见或评标结论；最终以评审委员会认定为准。</li>
    </ul>
  </div>
</div>
</body>
</html>"""

_CSS = """
body{margin:0;background:#f2f3f5;font-family:"Microsoft YaHei",sans-serif;color:#1f2329;line-height:1.7}
.wrap{max-width:1080px;margin:0 auto;padding:24px 20px 60px}
.head{background:#1d4ed8;color:#fff;border-radius:10px;padding:22px 28px;margin-bottom:18px}
.head h1{margin:0 0 6px;font-size:24px}
.meta{font-size:13px;opacity:.9}
.card{background:#fff;border:1px solid #e5e6eb;border-radius:10px;padding:18px 24px;margin-bottom:16px}
h2{margin:0 0 12px;font-size:18px;color:#1d4ed8;border-bottom:1px solid #f0f1f3;padding-bottom:8px}
table{width:100%;border-collapse:collapse;font-size:13px;margin-top:6px}
th{background:#f2f3f5;font-weight:600;text-align:left;padding:7px 10px;border:1px solid #e5e6eb;white-space:nowrap}
td{padding:7px 10px;border:1px solid #e5e6eb;vertical-align:top}
.ok{color:#00b42a;font-weight:600}
.bad{color:#f53f3f;font-weight:600}
.skip{color:#86909c}
.risk-red{background:#ffece8;color:#f53f3f;font-weight:600;border-radius:4px;padding:1px 6px;white-space:nowrap}
.risk-orange{background:#fff3e8;color:#ff7d00;font-weight:600;border-radius:4px;padding:1px 6px;white-space:nowrap}
.risk-yellow{background:#fff7e8;color:#ff8800;border-radius:4px;padding:1px 6px;white-space:nowrap}
.risk-green{background:#e8f3ec;color:#00b42a;border-radius:4px;padding:1px 6px;white-space:nowrap}
.kpi{display:flex;gap:14px;flex-wrap:wrap}
.kpi .item{flex:1;min-width:150px;background:#f8f9fb;border:1px solid #e5e6eb;border-radius:8px;padding:12px 16px;text-align:center}
.kpi .num{font-size:24px;font-weight:700;margin:4px 0 2px}
.kpi .lbl{font-size:12px;color:#86909c}
ul{margin:8px 0;padding-left:20px}
li{margin-bottom:4px}
.diff-item{background:#fffbe6;border:1px solid #ffe4a8;border-radius:6px;padding:8px 12px;margin-bottom:8px;font-size:13px}
.diff-item .tag{font-weight:600;color:#b25e00}
.mono{font-family:Consolas,monospace;font-size:12px;color:#4e5969}
"""


def _esc(v):
    return html.escape(str(v or ""), quote=False)


def _risk_badge(lv):
    lv = (lv or "").strip()
    if lv == "🔴":
        return '<span class="risk-red">🔴 废标</span>'
    if lv == "🟠":
        return '<span class="risk-orange">🟠 严重</span>'
    if lv == "🟡":
        return '<span class="risk-yellow">🟡 一般</span>'
    if lv == "🟢":
        return '<span class="risk-green">🟢 提示</span>'
    return _esc(lv or "—")


def _kpi_html(machine, check, diff):
    a_ok = sum(1 for c in (machine.get("检查") or []) if c.get("ok"))
    a_n = len(machine.get("检查") or [])
    a_bad = a_n - a_ok
    a_issues = sum(len(c.get("issues") or []) for c in (machine.get("检查") or []))
    conclusion = check.get("结论") if check else "（通道B 未产出）"
    red_n = len(check.get("废标红线") or []) if check else 0
    red_risk = sum(1 for r in (check.get("废标红线") or [])
                   if (r.get("风险等级") or "").strip() == "🔴")
    fixes = len(check.get("整改清单") or []) if check else 0
    diffs = diff.get("diffs") or []
    diff_n = len(diffs)
    return (
        '<div class="kpi">'
        '<div class="item"><div class="lbl">通道A 机器检查</div><div class="num">%d/%d</div>'
        '<div class="lbl">通过项 / 总项（问题 %d 条）</div></div>'
        '<div class="item"><div class="lbl">通道B 结论</div><div class="num">%s</div>'
        '<div class="lbl">%s</div></div>'
        '<div class="item"><div class="lbl">废标红线核对</div><div class="num">%d</div>'
        '<div class="lbl">共 %d 条（🔴 %d 条）</div></div>'
        '<div class="item"><div class="lbl">整改清单</div><div class="num">%d</div>'
        '<div class="lbl">补正项</div></div>'
        '<div class="item"><div class="lbl">双通道差异</div><div class="num">%d</div>'
        '<div class="lbl">待人工裁决</div></div>'
        '</div>'
        % (a_ok, a_n, a_issues, _esc(conclusion), _esc(check.get("总结", "") if check else ""),
           red_n, red_n, red_risk, fixes, diff_n))


def _diff_html(diff):
    diffs = diff.get("diffs") or []
    if not diffs:
        return '<p class="ok">两通道无实质差异（无需人工裁决）。</p>'
    out = []
    for i, d in enumerate(diffs, 1):
        out.append(
            '<div class="diff-item"><span class="tag">[%d] %s</span> — %s'
            '<div><b>通道A：</b>%s</div>'
            '<div><b>通道B：</b>%s</div>'
            '<div><b>建议：</b>%s</div></div>'
            % (i, _esc(d.get("差异类型")), _esc(d.get("检查项") or d.get("维度")),
               _esc(d.get("通道A")), _esc(d.get("通道B")), _esc(d.get("建议"))))
    return "\n".join(out)


def _machine_html(machine):
    checks = machine.get("检查") or []
    if not checks:
        return "<p>（通道A 未产出）</p>"
    rows = []
    for c in checks:
        ok = c.get("ok")
        mark = '<span class="ok">✓ 通过</span>' if ok else '<span class="bad">✗ 未通过</span>'
        issues = c.get("issues") or []
        issues_html = "<br>".join(_esc(x) for x in issues[:12]) if issues else "—"
        if len(issues) > 12:
            issues_html += "<br><span class='mono'>…共 %d 条</span>" % len(issues)
        rows.append("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>"
                    % (_esc(c.get("id")), _esc(c.get("name")), _esc(c.get("level")),
                       mark, issues_html))
    return ('<table><tr><th>ID</th><th>检查项</th><th>级别</th><th>结论</th><th>问题明细</th></tr>'
            + "".join(rows) + "</table>")


def _checkdetail_html(check):
    dims = (check or {}).get("维度明细") or []
    if not dims:
        return "<p>（通道B 未产出维度明细）</p>"
    rows = []
    for d in dims:
        rows.append(
            "<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>"
            % (_esc(d.get("维度")), _risk_badge(d.get("风险等级")),
               _esc(d.get("问题描述")), _esc(d.get("来源追溯")),
               _esc(d.get("整改建议"))))
    return ('<table><tr><th>维度</th><th>风险</th><th>问题描述</th><th>来源追溯</th>'
            '<th>整改建议（补正方向）</th></tr>' + "".join(rows) + "</table>")


def _redline_html(check):
    reds = (check or {}).get("废标红线") or []
    if not reds:
        return "<p>（通道B 未产出废标红线核对）</p>"
    rows = []
    for r in reds:
        rows.append("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>"
                    % (_esc(r.get("条款")), _esc(r.get("是否响应")),
                       _esc(r.get("证据位置")), _risk_badge(r.get("风险等级")),
                       _esc(r.get("说明"))))
    return ('<table><tr><th>废标条款</th><th>是否响应</th><th>证据位置</th><th>风险</th>'
            '<th>说明</th></tr>' + "".join(rows) + "</table>")


def _fixes_html(check):
    fixes = (check or {}).get("整改清单") or []
    if not fixes:
        return "<p>（无整改项）</p>"
    rows = []
    for f in fixes:
        rows.append("<tr><td>%s</td><td>%s</td><td>%s</td></tr>"
                    % (_esc(f.get("优先级")), _esc(f.get("问题")), _esc(f.get("补正"))))
    return ('<table><tr><th>优先级</th><th>问题</th><th>补正方向</th></tr>'
            + "".join(rows) + "</table>")


def render_report_html(machine_doc, check_doc, diff_doc, generated_date=None):
    """机器检查 + 检查要点 + 双通道差异 → 单文件 HTML 字符串。"""
    machine = machine_doc or {}
    check = check_doc or {}
    diff = diff_doc or {}
    date = generated_date or datetime.now().strftime("%Y-%m-%d")
    project = _esc(machine.get("project") or check.get("project") or "")
    return (_TPL
            .replace("@@PROJECT@@", project)
            .replace("@@DATE@@", _esc(date))
            .replace("@@CSS@@", _CSS)
            .replace("@@KPI@@", _kpi_html(machine, check, diff))
            .replace("@@DIFF@@", _diff_html(diff))
            .replace("@@MACHINE@@", _machine_html(machine))
            .replace("@@CHECKDETAIL@@", _checkdetail_html(check))
            .replace("@@REDLINE@@", _redline_html(check))
            .replace("@@FIXES@@", _fixes_html(check)))
