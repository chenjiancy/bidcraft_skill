# -*- coding: utf-8 -*-
"""
bidcraft · M10 失分补救任务单 —— HTML 报告渲染

把 失分补救任务单_<项目>.json 渲染为可交付 HTML：
KPI（任务总数/可追分合计/客观当前/主观区间）+ 优先级图例 + 任务清单表
+ 每任务详情卡 + 评标闭环示意 + 免责/人工确认闸门。
"""
import datetime

_PRIO_COLOR = {"高": "#d93026", "中": "#e69138", "低": "#7f8c8d"}


def _esc(s):
    if s is None:
        return ""
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def render_task_html(project, doc, html_path):
    s = doc.get("summary", {})
    tasks = doc.get("tasks", [])
    order = {"高": 0, "中": 1, "低": 2}
    tasks_sorted = sorted(tasks, key=lambda t: (order.get(t.get("优先级"), 9), t.get("id", "")))

    sub = s.get("主观分")
    sub_txt = ("[%s-%s] / %s" % (sub["min"], sub["max"], sub["满分"])) if sub else "未评"

    kpi = (
        '<span class="kpi"><b>%s</b>任务总数</span>'
        '<span class="kpi"><b>%.1f 分</b>可追分合计</span>'
        '<span class="kpi"><b>%.1f / %.1f</b>客观分（当前）</span>'
        '<span class="kpi"><b>%s</b>主观分（通道B）</span>'
    ) % (len(tasks), s.get("可追分合计") or 0, s.get("客观分当前") or 0, s.get("客观分满分") or 0, _esc(sub_txt))

    legend = "".join(
        '<span class="lg" style="background:%s">%s</span>' % (c, k) for k, c in _PRIO_COLOR.items())

    rows = []
    for t in tasks_sorted:
        rows.append("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td>"
                    "<td><span style='color:%s;font-weight:600'>%s</span></td>"
                    "<td style='text-align:right'>%s</td><td>%s</td></tr>" % (
                        t["id"], t["类型"], t["动作"], _esc(t["标题"])[:52],
                        _PRIO_COLOR.get(t["优先级"], "#555"), t["优先级"],
                        ("%.1f" % t["预期加分"]) if t.get("预期加分") is not None else "—", t["来源"]))
    table = ("<table><tr style='background:#f1f3f4'><th>ID</th><th>类型</th><th>动作</th><th>标题</th>"
             "<th>优先级</th><th>预期加分</th><th>来源</th></tr>%s</table>") % "".join(rows)

    cards = []
    for t in tasks_sorted:
        steps = "".join("<li>%s</li>" % _esc(st) for st in t.get("动作步骤", []))
        mat = "/".join(str(v) for v in t.get("涉及素材", {}).values()) if t.get("涉及素材") else "—"
        cards.append(
            "<div class='card' style='border-left:4px solid %s'>"
            "<div class='ch'><b>%s %s</b> <span class='tag'>%s</span>"
            "<span class='tag' style='background:%s;color:#fff'>%s</span>"
            "<span class='tag'>预期加分 %s</span></div>"
            "<div class='cb'><b>评分项：</b>%s</div>"
            "<div class='cb'><b>当前状态：</b>%s</div>"
            "<div class='cb'><b>目标状态：</b>%s</div>"
            "<div class='cb'><b>动作步骤：</b><ol>%s</ol></div>"
            "<div class='cb'><b>涉及素材：</b>%s</div>"
            "<div class='cb'><b>验证方式：</b>%s</div></div>"
            % (
                _PRIO_COLOR.get(t["优先级"], "#555"), t["id"], _esc(t["动作"]), t["类型"],
                _PRIO_COLOR.get(t["优先级"], "#555"), t["优先级"],
                ("%.1f 分" % t["预期加分"]) if t.get("预期加分") is not None else "—",
                _esc(t.get("评分项", "")), _esc(t.get("当前状态", "")), _esc(t.get("目标状态", "")),
                steps, _esc(mat), _esc(t.get("验证方式", "")))
        )
    cards_html = "".join(cards)

    flow = (
        "<div class='flow'><div class='fnode'>M8 模拟评标<br/><small>eval-run / eval-parse / eval-report</small></div>"
        "<div class='farr'>→</div><div class='fnode'>失分诊断<br/><small>客观 issues + 主观诊断 + 暗标 rule + 报价风险</small></div>"
        "<div class='farr'>→</div><div class='fnode'>M10 补救任务单<br/><small>素材补齐 / 内容补强 / 格式合规 / 报价策略</small></div>"
        "<div class='farr'>→</div><div class='fnode'>执行 + 重评验证<br/><small>重跑 eval-run / eval-report（人工确认闸门）</small></div></div>"
    )

    html_doc = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>失分补救任务单 · %s</title>
<style>
body{font-family:'Microsoft YaHei',sans-serif;margin:0;background:#f7f8fa;color:#1f2d3d}
.wrap{max-width:980px;margin:0 auto;padding:24px}
h1{font-size:22px} h2{font-size:18px;border-left:4px solid #1a73e8;padding-left:10px;margin-top:28px}
table{border-collapse:collapse;width:100%%;font-size:13px;margin-top:8px}
th,td{padding:6px 8px;border:1px solid #ddd;text-align:left;vertical-align:top}
th{background:#f1f3f4}
.sum{background:#fff;border-radius:10px;padding:16px 20px;margin:14px 0;box-shadow:0 1px 3px rgba(0,0,0,.08)}
.kpi{display:inline-block;background:#eef4ff;border-radius:8px;padding:10px 18px;margin-right:10px;text-align:center}
.kpi b{font-size:20px;color:#1a73e8;display:block}
.lg{display:inline-block;color:#fff;border-radius:10px;padding:2px 12px;margin-right:6px;font-size:12px}
.card{background:#fff;border-radius:8px;padding:14px 18px;margin:12px 0;box-shadow:0 1px 3px rgba(0,0,0,.08)}
.ch{font-size:15px;margin-bottom:8px}
.tag{display:inline-block;background:#f1f3f4;border-radius:10px;padding:1px 10px;margin-right:8px;font-size:12px;color:#555}
.cb{font-size:13px;color:#444;margin:6px 0;line-height:1.7}
.cb ol{margin:4px 0;padding-left:22px}
.flow{display:flex;align-items:stretch;justify-content:space-between;background:#fff;border-radius:10px;padding:16px 20px;margin:14px 0;box-shadow:0 1px 3px rgba(0,0,0,.08)}
.fnode{flex:1;background:#eef4ff;border-radius:8px;padding:10px;text-align:center;font-size:13px;line-height:1.6}
.fnode small{color:#888}
.farr{display:flex;align-items:center;font-size:22px;color:#1a73e8;padding:0 6px}
.disc{font-size:12px;color:#888;background:#fafafa;border-radius:6px;padding:8px 12px;margin-top:20px}
</style></head><body><div class="wrap">
<h1>失分补救任务单 · %s</h1>
<p style='color:#888;font-size:13px'>生成时间 %s ｜ 依据：M8 模拟评标（通道A+通道B）失分诊断 ｜ 人工确认闸门</p>

<div class="sum">%s<p style='font-size:12px;color:#888;margin-top:8px'>优先级图例：%s</p></div>

<h2>一、评标→补救→重评 闭环</h2>
%s

<h2>二、任务清单（按优先级）</h2>
%s

<h2>三、任务详情</h2>
%s

<div class="disc">免责声明：任务单为投标前自检参考（依据联网核实的投标复盘实践：区分能力问题 vs 写作/形式问题逐项补救）；素材补齐须经 M5 素材归档流程（propose/apply）；客观分证据以素材清单为据，数量/有效期/时间须人工核对；最终以评标委员会评审为准。</div>
</div></body></html>""" % (
        _esc(project), _esc(project),
        datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        kpi, legend, flow, table, cards_html)

    html_path.write_text(html_doc, encoding="utf-8")
    return html_path
