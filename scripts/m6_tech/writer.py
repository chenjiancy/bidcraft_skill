# -*- coding: utf-8 -*-
"""
bidcraft · M6 技术标制作 —— `tech-parse`（正文落盘 + 自述块解析 + 写后回读）

契约 §4 / §8：
  1. 闸门①未确认拒绝；章节须已 tech-ctx（.meta 上下文包存在）
  2. 校验：非空 / 字数 ≥ wordCnt×0.7 / 模板占位（TODO/XXX/{{占位}}）/
     暗标敏感词（error 级）
  3. `M6-COVERAGE` / `M6-REVISE` 自述块 → `.meta/ch-xx.selfcheck.json`，正文剥离
  4. 落盘（旧正文进 .rewrite-trash）→ 回读逐字比对 → WRITTEN
  5. 任一硬校验失败：不落盘，章节置 FAILED（保留现场，可重跑）

`{{待填:说明}}` 属缺料披露（P3 允许），仅 warn，不阻断；模板占位 `{{占位}}` 硬失败。
"""
import json
from pathlib import Path

from _shared import core
from . import rules, store, sources

# 硬失败的占位类型（`待填` 是缺料披露，保留）
HARD_PLACEHOLDER_TYPES = ("模板占位", "TODO", "XXX")


def _mark_failed(tech, cid):
    """校验失败 → FAILED（不覆盖正文）；已是 FAILED 时幂等。"""
    tree = store.read_tree(tech)
    ch = store.find_chapter(tree, cid)
    if (ch.get("status") or "") == "FAILED":
        return
    try:
        store.advance_chapter(tech, cid, "FAILED")
    except core.LibraryError:
        pass


def _to_writing(tech, ch):
    """把章节推进到 WRITING（兼容 CONTEXT_READY/FAILED/重写态）。"""
    cur = ch.get("status") or "PENDING"
    if cur == "WRITING":
        return True
    if cur in ("CONTEXT_READY", "WRITTEN", "CHECKED", "CONFIRMED", "FAILED"):
        store.advance_chapter(tech, ch["id"], "WRITING")
        return True
    return False


def _vocab(ent, tree):
    return sources.sensitive_vocab(ent, tree)


def cmd_tech_parse(args):
    ent = sources.get_ent(args)
    proj = sources.proj_dir(ent, args.project)
    tech = sources.tech_dir(ent, args.project)
    tree = store.read_tree(tech)
    if not store.outline_confirmed(tree):
        raise core.LibraryError("闸门①未确认：章节树需先 tech-outline --confirm，禁止 tech-parse")
    ch = store.find_chapter(tree, args.chapter)
    if (ch.get("status") or "PENDING") == "PENDING":
        raise core.LibraryError("章节 %s 尚无上下文包（PENDING），请先 tech-ctx" % args.chapter)
    store.read_context_pack(tech, args.chapter)      # 缺 .meta 直接报错

    src = sources.ensure_inside("章节正文", args.file, proj)
    try:
        md = Path(src).read_text(encoding="utf-8")
    except OSError as e:
        raise core.LibraryError("章节正文无法读取：%s（%s）" % (src, e))

    info, self_err = rules.parse_selfcheck_block(md)
    body = rules.strip_selfcheck_block(md)
    problems, warnings = [], []

    if self_err:
        problems.append(("SELFCHECK", self_err))
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
        raise core.LibraryError("正文校验失败，未落盘（章节置 FAILED）：\n%s" % detail)

    if not _to_writing(tech, ch):
        raise core.LibraryError("章节 %s 当前状态 %s 不允许进入 WRITING"
                                % (args.chapter, ch.get("status")))
    store.write_chapter_body(tech, ch, body)
    if info:
        store.write_selfcheck(tech, args.chapter, info)
    back = store.read_chapter_body(tech, ch)
    if back != body:
        _mark_failed(tech, args.chapter)
        raise core.LibraryError("正文回读不一致（写入 %d 字符 / 读回 %d 字符），章节置 FAILED"
                                % (len(body), len(back)))
    store.advance_chapter(tech, args.chapter, "WRITTEN")

    out = {"chapter": args.chapter, "status": "WRITTEN", "chars": total,
           "wordCnt": ch.get("wordCnt"), "selfcheck": (info or {}).get("block"),
           "warnings": warnings}
    if getattr(args, "json", False):
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print("%s 正文已落盘并回读一致（%d 字 / 预算 %s 字）→ WRITTEN"
              % (args.chapter, total, ch.get("wordCnt")))
        if info:
            print("  自述块：%s → 章节/.meta/%s.selfcheck.json" % (info["block"], args.chapter))
        for w in warnings:
            print("  ⚠ %s" % w)
        print("下一步：tech-check（通道A 六项检查）→ tech-report（闸门②）")
    return 0
