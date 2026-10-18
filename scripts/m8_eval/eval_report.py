# -*- coding: utf-8 -*-
"""
bidcraft · M8 AI模拟评标 —— HTML 报告渲染（模拟评标报告_<项目>.html，人工确认闸门）
"""
import datetime
import html as _html

# 失分等级配色
_GAP = {"high": "#d93026", "mid": "#e69138", "low": "#b7b7b7"}


def _esc(x):
    return _html.escape(str(x))


def _level_badge(level):
    color = {"已计算": "#2e7d32", "参考": "#e69138", "缺失": "#d93026"}.get(level, "#757575")
    return '<span style="background:%s;color:#fff;padding:2px 8px;border-radius:10px;font-size:12px;">%s</span>' % (
        color, _esc(level))


def _svg_quote_curve(analysis, width=720, height=260):
    """报价得分-基准价曲线（SVG polyline，纯确定性绘制）。"""
    curve = analysis.get("curve") or []
    if not curve:
        return "<p>无报价数据，未生成曲线。</p>"
    xs = [c["base"] for c in curve]
    ys = [c["score"] for c in curve]
    b0, b1 = min(xs), max(xs)
    s0, s1 = 0.0, max(ys) * 1.05 or 30.0
    pad_l, pad_r, pad_t, pad_b = 46, 14, 16, 34
    iw, ih = width - pad_l - pad_r, height - pad_t - pad_b

    def px(b):
        return pad_l + (b - b0) / (b1 - b0) * iw if b1 > b0 else pad_l

    def py(s):
        return pad_t + (s1 - s) / (s1 - s0) * ih if s1 > s0 else pad_t

    pts = " ".join("%.1f,%.1f" % (px(c["base"]), py(c["score"])) for c in curve)
    # 报价位置竖线
    q = analysis.get("quote")
    cap = analysis.get("cap")
    marks = ""
    if q:
        if b0 <= q <= b1:
            marks += '<line x1="%.1f" y1="%d" x2="%.1f" y2="%d" stroke="#1a73e8" stroke-width="1.5" stroke-dasharray="4,3"/>' % (px(q), pad_t, px(q), pad_t + ih)
            marks += '<text x="%.1f" y="%d" font-size="11" fill="#1a73e8">报价</text>' % (px(q) + 2, pad_t - 4)
    if cap and b0 <= cap <= b1:
        marks += '<line x1="%.1f" y1="%d" x2="%.1f" y2="%d" stroke="#d93026" stroke-width="1.5" stroke-dasharray="4,3"/>' % (px(cap), pad_t, px(cap), pad_t + ih)
        marks += '<text x="%.1f" y="%d" font-size="11" fill="#d93026">最高限价</text>' % (px(cap) + 2, pad_t - 4)

    # 横轴刻度（最多 7 个）
    ticks = ""
    n = min(7, 8)
    for i in range(n + 1):
        b = b0 + (b1 - b0) * i / n
        ticks += '<text x="%.1f" y="%d" font-size="11" fill="#666" text-anchor="middle">%s</text>' % (
            px(b), pad_t + ih + 16, _fmt_amt(b))
    # 纵轴刻度
    for s in (0, 10, 20, 30):
        if s <= s1:
            ticks += '<text x="%d" y="%.1f" font-size="11" fill="#666" text-anchor="end">%d</text>' % (pad_l - 6, py(s) + 4, s)

    return (
        '<svg viewBox="0 0 %d %d" style="width:100%%;max-width:%dpx;font-family:\'Microsoft YaHei\',sans-serif;">'
        '<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="#ccc"/>'
        '<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="#ccc"/>'
        '<polyline points="%s" fill="none" stroke="#2e7d32" stroke-width="2"/>'
        '%s%s</svg>'
    ) % (width, height, width, pad_l, pad_t + ih, pad_l + iw, pad_t + ih,
         pad_l, pad_t, pad_l, pad_t + ih, pts, marks, ticks)


def _fmt_amt(v):
    if v is None:
        return "?"
    if v >= 10000:
        return "%.1f万" % (v / 10000.0)
    return "%.0f" % v


def render_report(project, standard, objective, quote, qa, summary, out_path, subjective=None):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    rows_obj = ""
    for r in objective:
        rows_obj += (
            "<tr><td>%s</td><td style='text-align:right'>%.1f</td><td style='text-align:right'>%.1f</td>"
            "<td>%s</td><td style='font-size:12px;color:#555'>%s</td><td style='font-size:12px;color:#888'>%s</td></tr>"
        ) % (_esc(r["item"]), r["max"], r["score"], _level_badge(r["level"]),
             _esc(r["evidence"]), _esc(r["note"]))

    rows_std = ""
    for p in standard["items"]:
        rows_std += "<tr><td>%s</td><td>%s</td><td style='text-align:right'>%s</td><td style='font-size:12px;color:#888'>%s</td></tr>" % (
            _esc(p["item"]), _esc(p["kind"]),
            ("%.1f" % p["weight"]) if p["weight"] is not None else "?",
            _esc(p["note"]))

    issues = ""
    src_issues = list(summary.get("issues", []))
    # 合并通道B 主观失分诊断
    sub_gaps = []
    if subjective:
        for it in subjective.get("失分诊断") or []:
            gap = it.get("失分")
            sub_gaps.append({
                "item": "%s（主观）" % it.get("子项"), "gap": gap,
                "max": it.get("失分") and (subjective.get("主观合计", {}).get("满分") or 0) or 0,
                "advice": it.get("说明") or "",
            })
    merged = src_issues + sub_gaps
    for it in merged:
        gap = it.get("gap")
        lv = "high" if (gap is not None and gap >= 5) else ("mid" if gap is not None else "low")
        issues += (
            "<div style='background:#fafafa;border-left:4px solid %s;padding:10px 12px;margin:8px 0;border-radius:4px;'>"
            "<b>%s</b>（失分 %s / 满分 %s）<div style='font-size:13px;color:#555;margin-top:4px'>%s</div></div>"
        ) % (_GAP[lv], _esc(it["item"]),
             ("%.1f" % gap) if gap is not None else "—",
             ("%.1f" % it["max"]) if isinstance(it.get("max"), (int, float)) else "—",
             _esc(it["advice"]))

    unrated = ""
    for p in summary.get("unrated", []):
        unrated += "<li>%s（%s）· %s 分：%s</li>" % (_esc(p["item"]), _esc(p["kind"]),
                                                   ("%.1f" % p["max"]) if p["max"] is not None else "?",
                                                   _esc(p["note"]))
    if subjective:
        unrated += "<li>主观分已由通道B 评审（%s）——见下方主观分明细。</li>" % _esc(subjective.get("结论", ""))
    else:
        unrated += "<li><b>主观分未评</b>：监理大纲/技术方案主观分待通道B（eval-parse）评审或 M6 交付后精评。</li>"

    # 主观分明细（通道B）
    sub_sec = ""
    if subjective:
        rows_sub = ""
        for it in subjective.get("主观评分") or []:
            est = it.get("预估分") or {}
            rows_sub += (
                "<tr><td>%s</td><td style='text-align:right'>%.1f</td>"
                "<td style='text-align:center'>[%s, %s]（建议 %s）</td>"
                "<td>%s</td><td style='font-size:12px;color:#555'>%s</td>"
                "<td style='font-size:12px;color:#888'>%s</td><td>%s</td></tr>"
            ) % (_esc(it.get("子项", "")), it.get("满分", 0),
                 est.get("min", 0), est.get("max", 0), est.get("建议", 0),
                 _esc(it.get("档次", "")), _esc(it.get("证据锚点", "")),
                 _esc(it.get("失分原因", "")), _esc(it.get("风险", "")))
        t = subjective.get("主观合计") or {}
        sub_sec = (
            "<h2>三、主观分明细（通道B · 模拟评审）</h2>"
            "<p style='font-size:13px;color:#555'>对象：%s ｜ 主观合计预估 [%s, %s]，建议 %s / 满分 %s ｜ 结论：%s</p>"
            "<table><tr style='background:#f1f3f4'><th>子项</th><th>满分</th><th>预估分</th><th>档次</th>"
            "<th>证据锚点</th><th>失分原因</th><th>风险</th></tr>%s</table>"
        ) % (_esc(subjective.get("对象", "")), t.get("min", 0), t.get("max", 0),
             t.get("建议", 0), t.get("满分", 0), _esc(subjective.get("结论", "")), rows_sub)
    else:
        sub_sec = (
            "<h2>三、主观分明细（通道B）</h2>"
            "<p style='font-size:13px;color:#e69138'>主观分未评：监理大纲/技术方案主观分待通道B（eval-parse 按 references/M8-模拟评标-提示词.md）评审，或 M6 交付后精评。</p>"
        )

    # 报价分析
    if qa.get("provided"):
        qsec = (
            "<h3>报价分分析（反推基准价区间）</h3>"
            "<p style='font-size:13px;color:#555'>%s</p>"
            "<p style='font-size:13px;'><b>保住各档得分所需基准价区间：</b></p>"
            "<table style='border-collapse:collapse;width:100%%;font-size:13px'>"
            "<tr style='background:#f1f3f4'><th style='padding:6px;border:1px solid #ddd'>目标得分</th>"
            "<th style='padding:6px;border:1px solid #ddd'>所需基准价区间（元）</th></tr>"
        ) % _esc(qa.get("note", ""))
        for b in qa["bands"]:
            qsec += "<tr><td style='padding:6px;border:1px solid #ddd'>%.1f 分</td><td style='padding:6px;border:1px solid #ddd'>[%s, %s]</td></tr>" % (
                b["target"], _fmt_amt(b["range"][0]), _fmt_amt(b["range"][1]))
        qsec += "</table>"
        for r in qa["risks"]:
            qsec += "<div style='background:#fdecea;border-left:4px solid #d93026;padding:8px 10px;margin:6px 0;font-size:13px'>%s</div>" % _esc(r)
    else:
        qsec = "<h3>报价分分析</h3><p style='font-size:13px;color:#555'>%s</p>" % _esc(qa.get("note", ""))

    # 主观 KPI
    if subjective:
        t = subjective.get("主观合计") or {}
        kpi_sub = '<span class="kpi"><b>[%s, %s] / %s</b>主观分（通道B 预估）</span>' % (
            t.get("min", 0), t.get("max", 0), t.get("满分", 0))
    else:
        kpi_sub = '<span class="kpi"><b>未评</b>主观分（待通道B）</span>'

    html_doc = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>模拟评标报告 · %s</title>
<style>
body{font-family:'Microsoft YaHei',sans-serif;margin:0;background:#f7f8fa;color:#1f2d3d}
.wrap{max-width:960px;margin:0 auto;padding:24px}
h1{font-size:22px} h2{font-size:18px;border-left:4px solid #1a73e8;padding-left:10px;margin-top:28px}
h3{font-size:15px;margin-top:18px}
table{border-collapse:collapse;width:100%%;font-size:13px;margin-top:8px}
th,td{padding:6px 8px;border:1px solid #ddd;text-align:left;vertical-align:top}
th{background:#f1f3f4}
.sum{background:#fff;border-radius:10px;padding:16px 20px;margin:14px 0;box-shadow:0 1px 3px rgba(0,0,0,.08)}
.kpi{display:inline-block;background:#eef4ff;border-radius:8px;padding:10px 18px;margin-right:10px;text-align:center}
.kpi b{font-size:20px;color:#1a73e8;display:block}
.disc{font-size:12px;color:#888;background:#fafafa;border-radius:6px;padding:8px 12px;margin-top:20px}
</style></head><body><div class="wrap">
<h1>模拟评标报告 · %s</h1>
<p style='color:#888;font-size:13px'>生成时间 %s ｜ 通道A 规则引擎（客观分+报价反推）+ 通道B 模拟评审（主观分）｜ 人工确认闸门</p>

<div class="sum">
<span class="kpi"><b>%.1f / %.1f</b>客观分（估）</span>
%s
<span class="kpi"><b>%.1f</b>报价分（反推参考）</span>
<span class="kpi"><b>%.0f</b>总分构成</span>
</div>

<h2>一、评分办法（招标原文要点）</h2>
<p style='font-size:13px'>%s</p>

<h2>二、评分标准构成（M4 解析结构化）</h2>
<table><tr style='background:#f1f3f4'><th>评分项</th><th>类型</th><th>分值</th><th>说明</th></tr>%s</table>

%s

<h2>四、客观分明细（通道A 规则引擎）</h2>
<table><tr style='background:#f1f3f4'><th>评分项</th><th>满分</th><th>估得分</th><th>状态</th><th>证据</th><th>核对说明</th></tr>%s</table>

<h2>五、%s</h2>%s

<h2>六、失分诊断（优先级从高到低）</h2>%s

<h2>七、未评项与说明</h2>
<ul style='font-size:13px;line-height:1.9'>%s</ul>

<div class="disc">免责声明：%s</div>
</div></body></html>""" % (
        _esc(project), _esc(project), now,
        summary["objective_score"], summary["objective_max"],
        kpi_sub,
        summary["quote_total"],
        standard["total"],
        _esc(standard["method"]),
        rows_std, sub_sec, rows_obj,
        "报价分分析" if qa.get("provided") else "报价分分析（未报价）", qsec,
        issues or "<p style='font-size:13px;color:#2e7d32'>客观分无失分缺口（以素材清单为据）；主观分见通道B。</p>",
        unrated or "<li>无</li>",
        _esc(summary["disclaimer"]))

    out_path.write_text(html_doc, encoding="utf-8")
    return out_path
