# -*- coding: utf-8 -*-
"""
bidcraft · M6 技术标制作 —— T11 `tech-rewrite`（精修回路，契约 §6.2 P5 / V11）

P5 精修契约：
  1. 闸门①未确认拒绝；章节须已有现存正文（无正文先 tech-parse）
  2. agent 基于现有正文做定向修订（不重写全章），产出修订稿 md（须带 `M6-REVISE` 变更块）
  3. 硬校验同 tech-parse：非空 / 字数 ≥ wordCnt×0.7 / 模板占位 / 暗标敏感词，
     失败不落盘置 FAILED（保留现场，可重跑）
  4. 差异披露：旧正文 vs 修订稿行级 diff 摘要 + M6-REVISE 变更块 + 失分点对照提示
  5. 旧正文自动备份进 `.rewrite-trash/<时间戳>/`（可还原）→ 回写 → 回读逐字比对 → WRITTEN
  6. 精修后须重新 tech-check / tech-report（闸门② 不静默继承）
"""
import difflib
import json
from pathlib import Path

from _shared import core
from . import rules, sources, store
from .writer import HARD_PLACEHOLDER_TYPES, _mark_failed, _to_writing, _vocab


def _diff_summary(old, new):
    """行级 diff 摘要：修改/新增/删除行数 + 前 8 处变更行定位。"""
    sm = difflib.SequenceMatcher(None, old, new)
    add = rem = rep = 0
    spots = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        if tag == "replace":
            rep += max(i2 - i1, j2 - j1)
        elif tag == "delete":
            rem += i2 - i1
        elif tag == "insert":
            add += j2 - j1
        if len(spots) < 8:
            spots.append("%s@L%s" % (tag, i1 + 1))
    return {"modified": rep, "added": add, "removed": rem, "spots": spots}


def cmd_tech_rewrite(args):
    ent = sources.get_ent(args)
    proj = sources.proj_dir(ent, args.project)
    tech = sources.tech_dir(ent, args.project)
    tree = store.read_tree(tech)
    if not store.outline_confirmed(tree):
        raise core.LibraryError("闸门①未确认：章节树需先 tech-outline --confirm，禁止 tech-rewrite")
    ch = store.find_chapter(tree, args.chapter)
    old_body = store.read_chapter_body(tech, ch)      # 无正文直接报错
    if not old_body.strip():
        raise core.LibraryError("章节 %s 尚无正文（%s），请先 tech-parse 落盘后再精修"
                                % (args.chapter, store.chapter_body_path(tech, ch)))

    src = sources.ensure_inside("精修稿", args.file, proj)
    try:
        md = Path(src).read_text(encoding="utf-8")
    except OSError as e:
        raise core.LibraryError("精修稿无法读取：%s（%s）" % (src, e))

    info, self_err = rules.parse_selfcheck_block(md)
    body = rules.strip_selfcheck_block(md)
    problems, warnings = [], []

    if self_err:
        problems.append(("SELFCHECK", self_err))
    if info and info.get("block") != "M6-REVISE":
        problems.append(("REVISEBLOCK",
                         "精修稿须带 M6-REVISE 变更块（P5 契约），收到 %s" % info.get("block")))
    if not info:
        warnings.append("精修稿未带 M6-REVISE 变更块（P5 提示词要求），仅披露行级 diff")
    if not body.strip():
        problems.append(("EMPTY", "正文为空（剥离自述块后无内容）"))
    counts = rules.count_chars(body)
    total = counts["body_chars"] + counts["table_chars"]
    need = int((ch.get("wordCnt") or 0) * 0.7)
    if total < need:
        problems.append(("WORDCNT", "正文 %d 字 < 预算 %d×0.7=%d 字（篇幅不足）"
                         % (total, ch.get("wordCnt") or 0, need)))

    ph = rules.scan_placeholders(body)
    hard_ph = [h for h in ph if h.get("type") in HARD_PLACEHOLDER_TYPES]
    if hard_ph:
        problems.append(("PLACEHOLDER", "存在未替换模板占位：%s"
                         % "；".join("%s@L%s" % (h.get("text", ""), h.get("line")) for h in hard_ph)))
    soft_ph = [h for h in ph if h.get("type") == "待填"]
    if soft_ph:
        warnings.append("缺料披露 {{待填}} %d 处（允许，须在 tech-check 裁决）" % len(soft_ph))

    sens = rules.scan_sensitive(body, _vocab(ent, tree), tree.get("bidMode") or "明标")
    if sens:
        problems.append(("SENSITIVE", "暗标敏感词命中 %d 处：%s"
                         % (len(sens), "；".join("%s@L%s" % (h["text"], h["line"]) for h in sens[:5]))))

    if problems:
        _mark_failed(tech, args.chapter)
        detail = "\n".join("[%s] %s" % p for p in problems)
        raise core.LibraryError("精修稿校验失败，未落盘（章节置 FAILED）：\n%s" % detail)

    if not _to_writing(tech, ch):
        raise core.LibraryError("章节 %s 当前状态 %s 不允许进入 WRITING（精修）"
                                % (args.chapter, ch.get("status")))

    old_lines = old_body.splitlines()
    new_lines = body.splitlines()
    summary = _diff_summary(old_lines, new_lines)

    store.write_chapter_body(tech, ch, body)          # backup=True → .rewrite-trash 自动备份旧稿
    if info:
        store.write_revise(tech, args.chapter, info)
    back = store.read_chapter_body(tech, ch)
    if back != body:
        _mark_failed(tech, args.chapter)
        raise core.LibraryError("精修回读不一致（写入 %d 字符 / 读回 %d 字符），章节置 FAILED"
                                % (len(body), len(back)))
    store.advance_chapter(tech, args.chapter, "WRITTEN")

    out = {"chapter": args.chapter, "status": "WRITTEN",
           "diff": summary,
           "revise": (info or {}).get("data"),
           "warnings": warnings,
           "next": "tech-check → tech-report（闸门② 不静默继承，须重新确认）"}
    if getattr(args, "json", False):
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print("%s 精修落盘并回读一致（%d 字 / 预算 %s 字）→ WRITTEN"
              % (args.chapter, total, ch.get("wordCnt")))
        print("  行级 diff：修改 %d / 新增 %d / 删除 %d 行（%s）"
              % (summary["modified"], summary["added"], summary["removed"],
                 "，".join(summary["spots"]) or "无变更"))
        if info:
            data = info["data"]
            print("  M6-REVISE 变更块：%d 处变更（%s）"
                  % (len(data.get("changes") or []), data.get("untouched") or "未声明未改动范围"))
            for c in (data.get("changes") or [])[:5]:
                print("    - %s：%s" % (c.get("where"), (c.get("why") or "")[:40]))
        if not info:
            print("  ⚠ 未带 M6-REVISE 变更块（P5 要求），请人工核对修订点")
        for w in warnings:
            print("  ⚠ %s" % w)
        print("下一步：tech-check（通道A 六项检查）→ tech-report --confirm（重新确认闸门②）")
    return 0
