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


def render_report(project, standard, objective, quote, qa, summary, out_path):
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
    for it in summary.get("issues", []):
        gap = it.get("gap")
        lv = "high" if (gap is not None and gap >= 5) else ("mid" if gap is not None else "low")
        issues += (
            "<div style='background:#fafafa;border-left:4px solid %s;padding:10px 12px;margin:8px 0;border-radius:4px;'>"
            "<b>%s</b>（失分 %.1f / 满分 %.1f）<div style='font-size:13px;color:#555;margin-top:4px'>%s</div></div>"
        ) % (_GAP[lv], _esc(it["item"]), gap if gap is not None else 0, it["max"], _esc(it["advice"]))

    unrated = ""
    for p in summary.get("unrated", []):
        unrated += "<li>%s（%s）· %s 分：%s</li>" % (_esc(p["item"]), _esc(p["kind"]),
                                                   ("%.1f" % p["max"]) if p["max"] is not None else "?",
                                                   _esc(p["note"]))

    # 报价分析
    if qa.get("provided"):
        qsec = (
            "<h3>报价分分析（反推基准价区间）</h3>"
            "<p style='font-size:13px;color:#555'>%s</p>"
            "%s"
            "<p style='font-size:13px;'><b>保住各档得分所需基准价区间：</b></p>"
            "<table style='border-collapse:collapse;width:100%%;font-size:13px'>"
            "<tr style='background:#f1f3f4'><th style='padding:6px;border:1px solid #ddd'>目标得分</th>"
            "<th style='padding:6px;border:1px solid #ddd'>所需基准价区间（元）</th></tr>"
        )
        for b in qa["bands"]:
            qsec += "<tr><td style='padding:6px;border:1px solid #ddd'>%.1f 分</td><td style='padding:6px;border:1px solid #ddd'>[%s, %s]</td></tr>" % (
                b["target"], _fmt_amt(b["range"][0]), _fmt_amt(b["range"][1]))
        qsec += "</table>"
        for r in qa["risks"]:
            qsec += "<div style='background:#fdecea;border-left:4px solid #d93026;padding:8px 10px;margin:6px 0;font-size:13px'>%s</div>" % _esc(r)
    else:
        qsec = "<h3>报价分分析</h3><p style='font-size:13px;color:#555'>%s</p>" % _esc(qa.get("note", ""))

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
<p style='color:#888;font-size:13px'>生成时间 %s ｜ 通道A 规则引擎（客观分 + 报价反推）｜ 人工确认闸门</p>

<div class="sum">
<span class="kpi"><b>%.1f / %.1f</b>客观分（估）</span>
<span class="kpi"><b>%.1f</b>报价分（反推参考）</span>
<span class="kpi"><b>%.1f</b>主观分（待 M6 精评）</span>
<span class="kpi"><b>%.0f</b>总分构成</span>
</div>

<h2>一、评分办法（招标原文要点）</h2>
<p style='font-size:13px'>%s</p>

<h2>二、评分标准构成（M4 解析结构化）</h2>
<table><tr style='background:#f1f3f4'><th>评分项</th><th>类型</th><th>分值</th><th>说明</th></tr>%s</table>

<h2>三、客观分明细（通道A 规则引擎）</h2>
<table><tr style='background:#f1f3f4'><th>评分项</th><th>满分</th><th>估得分</th><th>状态</th><th>证据</th><th>核对说明</th></tr>%s</table>

<h2>四、%s</h2>%s

<h2>五、失分诊断（优先级从高到低）</h2>%s

<h2>六、未评项（待 M6 / 待通道B / 待人工）</h2>
<ul style='font-size:13px;line-height:1.9'>%s</ul>

<div class="disc">免责声明：%s</div>
</div></body></html>""" % (
        _esc(project), _esc(project), now,
        summary["objective_score"], summary["objective_max"], summary["quote_total"],
        summary["subjective_total"], standard["total"],
        _esc(standard["method"]),
        rows_std, rows_obj,
        "报价分分析" if qa.get("provided") else "报价分分析（未报价）", qsec,
        issues or "<p style='font-size:13px;color:#2e7d32'>客观分无失分缺口（以素材清单为据）。</p>",
        unrated or "<li>无</li>",
        _esc(summary["disclaimer"]))

    out_path.write_text(html_doc, encoding="utf-8")
    return out_path
