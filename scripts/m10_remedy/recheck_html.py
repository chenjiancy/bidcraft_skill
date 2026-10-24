# -*- coding: utf-8 -*-
"""M10 T18 补救后重检报告 HTML 渲染（单文件自包含，人工确认闸门）。"""


def _esc(s):
    if s is None:
        return ""
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


_COLOR = {"通过": "#1a7f37", "未通过": "#c62828", "需人工复核": "#b26a00", "无法复核": "#b26a00"}


def render_recheck_html(project, out, html_path):
    s = out.get("summary", {})
    rows = []
    for r in out.get("results", []):
        c = _COLOR.get(r.get("验证"), "#555")
        rows.append("<tr><td>%s</td><td>%s</td><td><span style='color:%s;font-weight:700'>%s</span></td>"
                    "<td>%s</td></tr>" % (r.get("id"), _esc(r.get("标题"))[:60], c, r.get("验证"), _esc(r.get("证据"))))
    table = ("<table><tr style='background:#f1f3f4'><th>ID</th><th>标题</th><th>验证</th><th>证据</th></tr>%s</table>"
             % "".join(rows)) if rows else "<p>无已勾选任务复核明细</p>"

    new_html = ""
    if out.get("new_tasks"):
        items = []
        for t in out["new_tasks"]:
            steps = "".join("<li>%s</li>" % _esc(st) for st in t.get("动作步骤", [])[:4])
            items.append("<div class='card'><b>%s %s</b> — %s<ul>%s</ul></div>" % (
                t.get("id"), t.get("动作"), _esc(t.get("标题")), steps))
        new_html = "<h3>新增问题任务（已并入任务单，共 %d 条）</h3>%s" % (len(out["new_tasks"]), "".join(items))

    html = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>补救后重检报告 · %s</title>
<style>
 body{font-family:SimSun,serif;color:#222;margin:24px auto;max-width:920px;padding:0 16px}
 h1{font-size:20px;text-align:center;margin:8px 0}
 .meta{text-align:center;color:#666;font-size:13px;margin-bottom:16px}
 .kpis{display:flex;gap:10px;flex-wrap:wrap;margin:12px 0 16px}
 .kpi{background:#f6f8fa;border:1px solid #e1e4e8;border-radius:6px;padding:8px 12px;font-size:13px}
 .kpi b{font-size:16px;display:block}
 table{width:100%%;border-collapse:collapse;font-size:13px}
 th,td{border:1px solid #d0d7de;padding:6px 8px;text-align:left;vertical-align:top}
 .card{border:1px solid #e1e4e8;border-radius:6px;padding:10px 14px;margin:8px 0;font-size:13px}
 ul{margin:6px 0 0 20px;padding:0}
 .foot{margin-top:18px;font-size:12px;color:#666;border-top:1px solid #e1e4e8;padding-top:8px}
</style></head><body>
<h1>补救后重检报告 · %s</h1>
<div class="meta">重检时间：%s ｜ 生成依据：%s</div>
<div class="kpis">
 <span class="kpi"><b>%s</b>已勾选任务</span>
 <span class="kpi"><b>%s</b>验证通过</span>
 <span class="kpi"><b>%s</b>未通过</span>
 <span class="kpi"><b>%s</b>需人工复核</span>
 <span class="kpi"><b>%s</b>新增问题</span>
</div>
<div class="foot-l">%s</div>
<h3>复核明细</h3>%s
%s
<div class="foot">人工确认闸门：重检为确定性机器复核（M7 check-rule 检查快照对比 + M8 eval-run 失分 gap 对比）；语义项（失分原因/主观分）标注需人工核对 eval-report；最终以评标委员会评审为准。</div>
</body></html>""" % (
        _esc(project), _esc(project), _esc(out.get("重检时间")), _esc(out.get("生成依据")),
        s.get("已勾选任务"), s.get("验证通过"), s.get("未通过"), s.get("需人工复核"), s.get("新增问题"),
        _esc(out.get("结论", "")), table, new_html)
    html_path.write_text(html, encoding="utf-8")
