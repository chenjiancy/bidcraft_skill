# -*- coding: utf-8 -*-
"""
bidcraft · M6 技术标制作 —— `tech-check`（通道A 六项）/ `tech-report`（闸门②）

六项（契约 §6.1）：
  A1 评分点覆盖   F3 build_coverage（引用存在 + keyPoints 交集）
  A2 编号/结构    F2 validate_chapters_final
  A3 篇幅核算     F4 count_chars / estimate_pages / judge_pages（全项目合计）
  A4 暗标敏感词   F5 scan_sensitive
  A5 术语/人员    F6 check_consistency
  A6 占位/垃圾    F7 scan_placeholders（`{{待填}}` 记 warn，属缺料披露）

产物：
  检查/覆盖矩阵_<项目>.json   通道A 结论（供 tech-diff / M8）
  检查/覆盖矩阵_<项目>.md     人工快速阅读
  检查/技术标检查报告_<项目>.html  单文件报告（闸门②；`--confirm` 记 confirmLog）

不做语义判断：A1 只判“引用 + 关键词交集”，写得是否切题由通道B/人工裁决。
"""
import html
import json
from pathlib import Path

from _shared import core
from m8_eval import eval_std

from . import rules, store, sources

CHECK_SCHEMA = "m6.check/v1"
JSON_BASE = "检查/覆盖矩阵_%s.json"
MD_BASE = "检查/覆盖矩阵_%s.md"
HTML_BASE = "检查/技术标检查报告_%s.html"


def _issue(level, code, message, chapter=""):
    return {"level": level, "code": code, "message": message, "chapter": chapter}


def build_check_doc(ent, tech, tree, points):
    """运行 A1–A6 → 机器结论对象（不写盘）。"""
    raw = sources.scoring_items(points)
    parsed = [eval_std.parse_score_item(it, i) for i, it in enumerate(raw)]
    coverage = rules.build_coverage(parsed, tree["chapters"])

    _, struct_issues = rules.validate_chapters_final(tree)
    issues = [_issue(i.get("level", "warn"), i.get("code", "A2"), i.get("message", ""))
              for i in struct_issues]

    vocab = sources.sensitive_vocab(ent, tree)
    pc = tree.get("pageConstraint") or {}
    cfg = {"charsPerPage": pc.get("charsPerPage"), "tableCharsPerPage": 500}
    chapters, total_pages, written = {}, 0, 0

    for ch in store.list_chapters(tree):
        cid = ch.get("id")
        info = {"chars": None, "pages": None, "body": False,
                "sensitive": [], "placeholders": [], "consistency": []}
        try:
            text = store.read_chapter_body(tech, ch)
        except core.LibraryError:
            text = None
        if text:
            counts = rules.count_chars(text)
            chars = counts["body_chars"] + counts["table_chars"]
            pg = rules.estimate_pages(counts["body_chars"], counts["table_chars"], cfg)["pages"]
            info.update({"chars": chars, "pages": pg, "body": True})
            total_pages += pg
            written += 1
            sens = rules.scan_sensitive(text, vocab, tree.get("bidMode") or "明标")
            ph = rules.scan_placeholders(text)
            cons = rules.check_consistency(text, tree.get("terminology"), tree.get("personnel"),
                                           mode=tree.get("bidMode") or "明标")
            info.update({"sensitive": sens, "placeholders": ph, "consistency": cons})
            for h in sens:
                issues.append(_issue("error", "A4.sensitive",
                                     "暗标敏感词「%s」@L%s（%s）" % (h.get("text"), h.get("line"), h.get("type")),
                                     cid))
            for h in ph:
                issues.append(_issue("warn", "A6.%s" % h.get("type"),
                                     "占位/残留「%s」@L%s" % (h.get("text"), h.get("line")), cid))
            for h in cons:
                issues.append(_issue(h.get("level", "warn"), h.get("code", "A5"),
                                     h.get("message", ""), cid))
        else:
            issues.append(_issue("warn", "A3.nobody", "本章无正文（未 tech-parse）", cid))
        chapters[cid] = info

    page_issue = rules.judge_pages(total_pages, pc) if written else None
    if page_issue:
        issues.append(_issue(page_issue["level"], page_issue["code"], page_issue["message"]))

    cov_errors = len(coverage["missing"])
    cov_warns = len(coverage["weak"])
    flat_errors = sum(1 for i in issues if i.get("level") == "error")
    flat_warns = sum(1 for i in issues if i.get("level") == "warn")
    errors = cov_errors + flat_errors
    return {
        "schema": CHECK_SCHEMA,
        "project": tree.get("project"),
        "generatedAt": core.now_iso(),
        "bidMode": tree.get("bidMode"),
        "gate": "write",
        "ok": errors == 0,
        "coverage": coverage,
        "chapters": chapters,
        "pageConstraint": pc,
        "issues": issues,
        "summary": {"chapters": len(chapters), "written": written,
                    "errors": errors, "warns": cov_warns + flat_warns,
                    "pages": total_pages, "maxPages": pc.get("max")},
    }


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------
def _cell(v, dash="-"):
    if v is None or v == "":
        return dash
    return str(v).replace("|", "\\|").replace("\n", " ")


def render_md(doc):
    s = doc["summary"]
    lines = ["# 技术标检查 · %s（通道A）" % doc["project"], "",
             "- 生成时间：%s" % doc["generatedAt"],
             "- 标书模式：%s" % doc["bidMode"],
             "- 结论：%s（error %d / warn %d）" % ("通过" if doc["ok"] else "不通过",
                                                s["errors"], s["warns"]),
             "- 篇幅：估算 %s 页 / 上限 %s 页（已写 %d/%d 章）"
             % (s["pages"], s["maxPages"], s["written"], s["chapters"]), "",
             "## A1 覆盖矩阵", "",
             "| idx | 评分项 | kind | 权重 | 覆盖 | 章节 | 交集比 | 级别 | 说明 |",
             "|---|---|---|---|---|---|---|---|---|"]
    for r in doc["coverage"]["rows"]:
        lines.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            r["idx"], _cell(r["item"]), _cell(r["kind"]), _cell(r["weight"]),
            "是" if r["covered"] else "否", _cell(",".join(r["chapters"] or [])),
            r["ratio"], _cell(r["level"]), _cell(r["note"])))
    lines += ["", "## 章节明细", "",
              "| 章节 | 字数 | 估算页 | 敏感词 | 占位 | 一致性 |", "|---|---|---|---|---|---|"]
    for cid, info in doc["chapters"].items():
        lines.append("| %s | %s | %s | %d | %d | %d |" % (
            cid, _cell(info["chars"]), _cell(info["pages"]),
            len(info["sensitive"]), len(info["placeholders"]), len(info["consistency"])))
    lines += ["", "## 问题清单", ""]
    if not doc["issues"]:
        lines.append("无。")
    else:
        lines += ["| 级别 | 代码 | 章节 | 说明 |", "|---|---|---|---|"]
        for i in doc["issues"]:
            lines.append("| %s | %s | %s | %s |" % (
                i["level"], i["code"], _cell(i.get("chapter")), _cell(i["message"])))
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# HTML（单文件、无外链）
# ---------------------------------------------------------------------------
_CSS = """
:root{--bg:#f4f3ef;--card:#fff;--ink:#25231f;--muted:#6f6a61;--line:#ddd8ce;
      --err:#b3261e;--warn:#8a5a00;--ok:#2e6b3f;--accent:#274b6d}
*{box-sizing:border-box}
body{margin:0;padding:28px;background:var(--bg);color:var(--ink);
     font-family:"FangSong","仿宋","SimSun",serif;font-size:15px;line-height:1.7}
.wrap{max-width:1180px;margin:0 auto}
h1,h2{font-family:"Microsoft YaHei","微软雅黑",sans-serif;color:var(--accent);margin:0 0 8px}
h1{font-size:24px}h2{font-size:18px;margin-top:28px}
.sub{color:var(--muted);margin-bottom:18px}
.kpis{display:flex;gap:12px;flex-wrap:wrap;margin:18px 0 6px}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:12px 18px;min-width:118px}
.kpi b{display:block;font-size:22px;font-family:"Microsoft YaHei",sans-serif}
.kpi span{color:var(--muted);font-size:12px}
.kpi.err b{color:var(--err)}.kpi.warn b{color:var(--warn)}.kpi.ok b{color:var(--ok)}
table{width:100%;border-collapse:collapse;background:var(--card);font-size:14px}
th,td{border:1px solid var(--line);padding:6px 8px;vertical-align:top;text-align:left}
th{background:#eae5da;font-family:"Microsoft YaHei",sans-serif;font-weight:600}
tr:nth-child(even) td{background:#fbfaf7}
.tag{display:inline-block;padding:0 6px;border-radius:4px;font-size:12px}
.tag.error{background:#fbe9e7;color:var(--err);border:1px solid #f0c2bc}
.tag.warn{background:#fdf3df;color:var(--warn);border:1px solid #eed9a8}
.tag.ok{background:#e8f2ea;color:var(--ok);border:1px solid #bcd8c3}
.decide{background:var(--card);border:1px dashed #b9b2a4;border-radius:8px;padding:14px 18px;margin-top:18px}
.decide ul{margin:8px 0 0 18px;padding:0}
.decide li{margin:4px 0}
textarea{width:100%;min-height:84px;border:1px solid var(--line);border-radius:6px;
         background:#fff;padding:8px;font-family:inherit;font-size:14px}
.foot{color:var(--muted);font-size:12px;margin-top:24px}
"""


def _e(v):
    return html.escape("" if v is None else str(v))


def _tag(level):
    cls = "error" if level == "error" else ("warn" if level == "warn" else "ok")
    return '<span class="tag %s">%s</span>' % (cls, _e(level))


def render_html(doc, tree):
    s = doc["summary"]
    gate2 = next((r for r in (tree.get("confirmLog") or []) if r.get("gate") == "write"), None)
    rows = []
    for r in doc["coverage"]["rows"]:
        rows.append("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td>"
                    "<td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
                        _e(r["idx"]), _e(r["item"]), _e(r["kind"]), _e(r["weight"]),
                        "是" if r["covered"] else "否", _e(",".join(r["chapters"] or [])),
                        _e(r["ratio"]), _tag(r["level"]), _e(r["note"])))
    ch_rows = []
    for cid, info in doc["chapters"].items():
        ch_rows.append("<tr><td>%s</td><td>%s</td><td>%s</td><td>%d</td><td>%d</td><td>%d</td></tr>" % (
            _e(cid), _e(info["chars"]), _e(info["pages"]), len(info["sensitive"]),
            len(info["placeholders"]), len(info["consistency"])))
    issue_rows = []
    for i in doc["issues"]:
        issue_rows.append("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
            _tag(i.get("level")), _e(i.get("code")), _e(i.get("chapter")), _e(i.get("message"))))
    decide = []
    for r in doc["coverage"]["rows"]:
        if r["level"]:
            decide.append("<li><label><input type=\"checkbox\"> 确认 idx %s（%s）：%s</label></li>"
                          % (_e(r["idx"]), _e(r["item"]), _e(r["note"])))
    for i in doc["issues"]:
        if i.get("level") == "error":
            decide.append("<li><label><input type=\"checkbox\"> %s %s：%s</label></li>"
                          % (_e(i.get("code")), _e(i.get("chapter")), _e(i.get("message"))))
    verdict = "通过" if doc["ok"] else "不通过"
    gate_txt = "已记录（%s）" % _e(gate2.get("at")) if gate2 else "未记录"
    body = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>%s · 技术标检查报告</title><style>%s</style></head>
<body><div class="wrap">
<h1>技术标检查报告 · %s</h1>
<div class="sub">生成时间 %s ｜ 标书模式 %s ｜ 闸门② %s</div>
<div class="kpis">
  <div class="kpi"><b>%d</b><span>章节</span></div>
  <div class="kpi"><b>%d</b><span>已写正文</span></div>
  <div class="kpi err"><b>%d</b><span>error</span></div>
  <div class="kpi warn"><b>%d</b><span>warn</span></div>
  <div class="kpi %s"><b>%s</b><span>通道A 结论</span></div>
  <div class="kpi"><b>%s / %s</b><span>估算页 / 上限</span></div>
</div>

<h2>A1 覆盖矩阵（评分项 × 章节）</h2>
<table><thead><tr><th>idx</th><th>评分项</th><th>kind</th><th>权重</th><th>覆盖</th>
<th>章节</th><th>交集比</th><th>级别</th><th>说明</th></tr></thead>
<tbody>%s</tbody></table>

<h2>章节明细（A3–A6）</h2>
<table><thead><tr><th>章节</th><th>字数</th><th>估算页</th><th>敏感词</th><th>占位</th>
<th>一致性</th></tr></thead><tbody>%s</tbody></table>

<h2>问题清单</h2>
<table><thead><tr><th>级别</th><th>代码</th><th>章节</th><th>说明</th></tr></thead>
<tbody>%s</tbody></table>

<h2>闸门② 裁决区</h2>
<div class="decide">
<p>通道A 只做确定性判断；“是否切题/是否可接受”由你逐项裁决。裁决完成后执行
<code>tech-report --confirm</code> 记入 <code>章节树.json.confirmLog</code>。</p>
<ul>%s</ul>
<p><textarea placeholder="裁决备注（可选）"></textarea></p>
</div>
<div class="foot">bidcraft · M6 技术标制作 · 通道A 机器检查（A1–A6），不生成/不改写正文。</div>
</div></body></html>
""" % (_e(doc["project"]), _CSS, _e(doc["project"]), _e(doc["generatedAt"]), _e(doc["bidMode"]),
       gate_txt, s["chapters"], s["written"], s["errors"], s["warns"],
       "ok" if doc["ok"] else "err", _e(verdict), _e(s["pages"]), _e(s["maxPages"]),
       "".join(rows), "".join(ch_rows), "".join(issue_rows),
       "".join(decide) if decide else "<li>无 error/warn 项。</li>")
    return body


# ---------------------------------------------------------------------------
# tech-check
# ---------------------------------------------------------------------------
def cmd_tech_check(args):
    ent = sources.get_ent(args)
    proj = sources.proj_dir(ent, args.project)
    tech = sources.tech_dir(ent, args.project)
    tree = store.read_tree(tech)
    tdir = sources.tdir(args, proj)
    points = sources.load_points(tdir, args.project)

    doc = build_check_doc(ent, tech, tree, points)
    jp = store.write_json_inside(tech, JSON_BASE % args.project, doc)
    mp = store.write_text_inside(tech, MD_BASE % args.project, render_md(doc))

    advanced = []
    if getattr(args, "chapter", ""):
        cid = args.chapter
        ch = store.find_chapter(tree, cid)
        own_err = [i for i in doc["issues"]
                   if i.get("chapter") == cid and i.get("level") == "error"]
        cov_err = any(r.get("level") == "error" and cid in (r.get("chapters") or [])
                      for r in doc["coverage"]["rows"])
        if ch.get("status") == "WRITTEN" and not own_err and not cov_err:
            store.advance_chapter(tech, cid, "CHECKED")
            advanced.append(cid)
    elif doc["ok"]:
        for ch in store.list_chapters(store.read_tree(tech)):
            if ch.get("status") == "WRITTEN" and (doc["chapters"].get(ch.get("id")) or {}).get("body"):
                store.advance_chapter(tech, ch["id"], "CHECKED")
                advanced.append(ch["id"])

    if getattr(args, "json", False):
        print(json.dumps({"doc": doc, "advanced": advanced,
                          "json": str(jp), "md": str(mp)}, ensure_ascii=False, indent=2))
    else:
        s = doc["summary"]
        print("通道A 检查完成：%s" % ("通过" if doc["ok"] else "不通过"))
        print("  error %d / warn %d；已写 %d/%d 章；估算 %s 页 / 上限 %s 页"
              % (s["errors"], s["warns"], s["written"], s["chapters"],
                 s["pages"], s["maxPages"]))
        print("  覆盖矩阵：%s" % jp)
        print("  可读版：%s" % mp)
        for i in doc["issues"]:
            if i.get("level") == "error":
                print("  ✗ [%s] %s %s" % (i["code"], i.get("chapter") or "", i["message"]))
        if advanced:
            print("  状态推进：%s → CHECKED" % "、".join(advanced))
        print("下一步：tech-report（闸门② HTML）")
    return 0 if doc["ok"] else 1


# ---------------------------------------------------------------------------
# tech-report
# ---------------------------------------------------------------------------
def cmd_tech_report(args):
    ent = sources.get_ent(args)
    sources.proj_dir(ent, args.project)
    tech = sources.tech_dir(ent, args.project)
    jp = Path(tech) / (JSON_BASE % args.project)
    if not jp.is_file():
        raise core.LibraryError("检查结论不存在：%s（请先 tech-check）" % jp)
    try:
        doc = json.loads(jp.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise core.LibraryError("检查结论无法读取：%s（%s）" % (jp, e))

    confirmed, advanced = False, []
    if getattr(args, "confirm", False):
        if not doc.get("ok") and not getattr(args, "force", False):
            raise core.LibraryError(
                "闸门②拒绝：通道A 存在 error 级问题（error %s）；如确认接受请加 --force"
                % (doc.get("summary") or {}).get("errors"))
        note = getattr(args, "note", "") or "tech-report --confirm"
        if not doc.get("ok"):
            note += "（--force，存在 error）"
        store.confirm_gate(tech, "write", note=note)
        confirmed = True
        for ch in store.list_chapters(store.read_tree(tech)):
            if ch.get("status") == "CHECKED":
                store.advance_chapter(tech, ch["id"], "CONFIRMED")
                advanced.append(ch["id"])

    tree = store.read_tree(tech)
    hp = store.write_text_inside(tech, HTML_BASE % args.project, render_html(doc, tree))

    if getattr(args, "json", False):
        print(json.dumps({"html": str(hp), "ok": doc.get("ok"),
                          "confirmed": confirmed, "advanced": advanced},
                         ensure_ascii=False, indent=2))
    else:
        print("技术标检查报告：%s" % hp)
        print("  通道A 结论：%s；error %s / warn %s"
              % ("通过" if doc.get("ok") else "不通过",
                 (doc.get("summary") or {}).get("errors"),
                 (doc.get("summary") or {}).get("warns")))
        if confirmed:
            print("  闸门②：已记录 confirmLog（write）")
            if advanced:
                print("  状态推进：%s → CONFIRMED" % "、".join(advanced))
            else:
                print("  ⚠ 无 CHECKED 章节可推进（先 tech-check 通过）")
        else:
            print("  闸门②：未记录（审阅后 tech-report --confirm）")
    return 0 if (confirmed or doc.get("ok")) else 1
