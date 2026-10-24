# -*- coding: utf-8 -*-
"""
bidcraft · M6 技术标制作 —— 章节版本历史（链企引入 C1：写前自动快照 + 撤销安全网）

职责：
  1. 写正文前把旧文本快照进 `.history/{ch_id}/`（不覆盖旧稿）；
  2. 四道防抖：空文本不快照 / 同文去重 / 2 分钟同 reason 合并窗口 / 每章上限 20 版（删最旧）；
  3. `index.json` 版本索引（schema m6.history/v1，与 m9 台账同风格）；
  4. `tech-history list / diff / restore`：列版本、两版对比、撤销到指定版本
     （撤销写回走 write_chapter_body → 回收站 + 新快照 = 双向可撤销）；
  5. 纯运行态字段（status/字数/runId）走章节树 / .meta 状态文件，不经过正文快照（天然 skipHistory）。

本层只做确定性版本 I/O，不判断内容质量。
"""
import difflib
import hashlib
import json
import time
from pathlib import Path

from _shared import core

HISTORY_DIR = ".history"
INDEX_FILE = "index.json"
SCHEMA = "m6.history/v1"
MAX_VERSIONS = 20
MERGE_WINDOW_S = 120
KEEP = 12  # diff 摘要保留的变更定位条数


# ---------------------------------------------------------------------------
# 路径
# ---------------------------------------------------------------------------
def history_root(tech_dir):
    return Path(tech_dir) / HISTORY_DIR


def chapter_history_dir(tech_dir, ch_id):
    return history_root(tech_dir) / ch_id


def index_path(tech_dir, ch_id):
    return chapter_history_dir(tech_dir, ch_id) / INDEX_FILE


def _read_index(tech_dir, ch_id):
    p = index_path(tech_dir, ch_id)
    if not p.is_file():
        return {"schema": SCHEMA, "chapter": ch_id, "versions": []}
    try:
        idx = json.loads(p.read_text(encoding="utf-8"))
    except ValueError:
        raise core.LibraryError("版本索引 JSON 损坏：%s（保留现场，请勿删除）" % p)
    if not isinstance(idx, dict) or idx.get("schema") != SCHEMA:
        raise core.LibraryError("版本索引 schema 异常：%s" % p)
    return idx


def _write_index(tech_dir, ch_id, idx):
    p = index_path(tech_dir, ch_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(idx, ensure_ascii=False, indent=2) + "\n"
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    import os as _os
    _os.replace(str(tmp), str(p))
    back = p.read_text(encoding="utf-8")
    if back != text:
        raise core.LibraryError("版本索引回读不一致：%s" % p)


# ---------------------------------------------------------------------------
# 快照
# ---------------------------------------------------------------------------
def _md5(text):
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def snapshot(tech_dir, ch_id, old_text, reason="write"):
    """写前快照：把旧文本压入版本历史。四道防抖后无新版本时返回 None。"""
    ch_id = str(ch_id)
    if not old_text or not old_text.strip():
        return None  # 空文件不快照
    idx = _read_index(tech_dir, ch_id)
    vs = idx.get("versions")
    if vs is None:
        vs = []
        idx["versions"] = vs  # 保持引用：append 需反映到 idx（[] 是 falsy，不能用 or []）
    cur = _md5(old_text)
    if vs and vs[-1].get("md5") == cur:
        return None  # 同文去重：最新版与旧文本相同 → 不新增
    now = time.time()
    if vs:
        last = vs[-1]
        if last.get("reason") == reason and now - last.get("ts", 0) < MERGE_WINDOW_S:
            # 2 分钟同 reason 合并窗口：覆盖重写该版本（保留 seq，更新时间与指纹）
            last["ts"] = now
            last["chars"] = len(old_text)
            last["md5"] = cur
            last["size"] = len(old_text.encode("utf-8"))
            _write_index(tech_dir, ch_id, idx)
            return last
    seq = (vs[-1].get("seq") + 1) if vs else 1
    entry = {"seq": seq, "ts": now, "reason": reason,
             "chars": len(old_text), "md5": cur,
             "size": len(old_text.encode("utf-8"))}
    # 写版本文件（失败不落索引）
    d = chapter_history_dir(tech_dir, ch_id)
    d.mkdir(parents=True, exist_ok=True)
    vf = d / ("v%03d.md" % seq)
    vf.write_text(old_text, encoding="utf-8")
    vs.append(entry)
    # 上限：删除最旧（超限时文件+索引项一起删，seq 不重排）
    while len(vs) > MAX_VERSIONS:
        old = vs.pop(0)
        (d / ("v%03d.md" % old["seq"])).unlink(missing_ok=True)
    _write_index(tech_dir, ch_id, idx)
    return entry


# ---------------------------------------------------------------------------
# 读取
# ---------------------------------------------------------------------------
def versions(tech_dir, ch_id):
    """列版本（按 seq 升序）。"""
    idx = _read_index(tech_dir, ch_id)
    return idx.get("versions") or []


def read_version(tech_dir, ch_id, seq):
    """读指定版本正文；不存在抛 LibraryError。"""
    seq = int(seq)
    d = chapter_history_dir(tech_dir, ch_id)
    p = d / ("v%03d.md" % seq)
    if not p.is_file():
        raise core.LibraryError("版本不存在：%s v%03d（tech-history list 查看可用版本）" % (ch_id, seq))
    try:
        return p.read_text(encoding="utf-8")
    except OSError as e:
        raise core.LibraryError("版本读取失败：%s（%s）" % (p, e))


def history_summary(tech_dir):
    """全部章节历史概览：{ch_id: {count, latest_seq, latest_ts, latest_reason, chars}}。"""
    root = history_root(tech_dir)
    out = {}
    if not root.is_dir():
        return out
    for d in sorted(root.iterdir()):
        if not d.is_dir():
            continue
        try:
            vs = versions(tech_dir, d.name)
        except core.LibraryError:
            continue
        if not vs:
            continue
        latest = vs[-1]
        out[d.name] = {"count": len(vs), "latest_seq": latest["seq"],
                       "latest_ts": latest["ts"], "latest_reason": latest["reason"],
                       "chars": latest["chars"]}
    return out


# ---------------------------------------------------------------------------
# 对比 / 撤销
# ---------------------------------------------------------------------------
def diff_summary(text_a, text_b, keep=KEEP):
    """行级 diff 摘要：修改/新增/删除行数 + 前 keep 处变更定位。"""
    sm = difflib.SequenceMatcher(None, text_a.splitlines(), text_b.splitlines())
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
        if len(spots) < keep:
            spots.append("%s@L%s" % (tag, i1 + 1))
    return {"modified": rep, "added": add, "removed": rem, "spots": spots}


def diff_versions(tech_dir, ch_id, seq_a, seq_b):
    a = read_version(tech_dir, ch_id, seq_a)
    b = read_version(tech_dir, ch_id, seq_b)
    return {"from": int(seq_a), "to": int(seq_b),
            "summary": diff_summary(a, b),
            "from_chars": len(a), "to_chars": len(b)}


def restore(tech_dir, ch_id, seq, write_chapter_body):
    """撤销到指定版本：读版本 → 写回正文（旧正文进回收站 + 新快照 reason=restore）。

    write_chapter_body 由调用方注入（store.write_chapter_body），避免本模块反向依赖 store。
    撤销本身进历史 → 可再撤销（双向可撤销）。
    """
    text = read_version(tech_dir, ch_id, seq)
    if not text.strip():
        raise core.LibraryError("版本 %s v%03d 为空，拒绝撤销" % (ch_id, seq))
    return write_chapter_body(tech_dir, ch_id, text, reason="restore")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def cmd_tech_history(args):
    """tech-history：列版本 / 两版对比 / 撤销（链企引入 C1）。"""
    from . import sources, store as _store

    ent = sources.get_ent(args)
    tech = sources.tech_dir(ent, args.project)
    tree = _store.read_tree(tech)
    ch_id = getattr(args, "chapter", "") or ""

    if getattr(args, "restore", ""):
        if not ch_id:
            raise core.LibraryError("--restore 须配合 --chapter ch-xx")
        ch = _store.find_chapter(tree, ch_id)  # 章节存在性校验
        seq = int(args.restore)
        text = read_version(tech, ch_id, seq)
        if not text.strip():
            raise core.LibraryError("版本 %s v%03d 为空，拒绝撤销" % (ch_id, seq))
        _store.write_chapter_body(tech, ch, text, reason="restore")
        if getattr(args, "json", False):
            print(json.dumps({"chapter": ch_id, "restored": seq,
                              "next": "tech-check → tech-report（闸门② 须重新确认）"},
                             ensure_ascii=False, indent=2))
        else:
            print("%s 已撤销到 v%03d 并写回正文（旧正文入回收站 + 快照 reason=restore，可再撤销）"
                  % (ch_id, seq))
            print("下一步：tech-check → tech-report（闸门② 不静默继承，须重新确认）")
        return 0

    if getattr(args, "diff", ""):
        if not ch_id:
            raise core.LibraryError("--diff 须配合 --chapter ch-xx")
        _store.find_chapter(tree, ch_id)
        seq_a, seq_b = (int(x) for x in args.diff.split(","))
        d = diff_versions(tech, ch_id, seq_a, seq_b)
        if getattr(args, "json", False):
            print(json.dumps(d, ensure_ascii=False, indent=2))
        else:
            s = d["summary"]
            print("%s v%03d → v%03d：修改 %d / 新增 %d / 删除 %d 行（%s）"
                  % (ch_id, seq_a, seq_b, s["modified"], s["added"], s["removed"],
                     "，".join(s["spots"]) or "无变更"))
            print("  字数 %d → %d" % (d["from_chars"], d["to_chars"]))
        return 0

    # 默认：list
    if ch_id:
        _store.find_chapter(tree, ch_id)
        vs = versions(tech, ch_id)
        if getattr(args, "json", False):
            print(json.dumps({"chapter": ch_id, "versions": vs}, ensure_ascii=False, indent=2))
        else:
            if not vs:
                print("%s 暂无版本历史（尚无正文，或从未发生过覆盖写入）" % ch_id)
            else:
                for v in vs:
                    print("v%03d  %s  %d 字  reason=%s  seq=%d"
                          % (v["seq"], time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(v["ts"])),
                             v["chars"], v["reason"], v["seq"]))
                print("  撤销：tech-history --chapter %s --restore <seq>；对比：--diff seqA,seqB" % ch_id)
    else:
        summary = history_summary(tech)
        if getattr(args, "json", False):
            print(json.dumps(summary, ensure_ascii=False, indent=2))
        else:
            if not summary:
                print("暂无任何章节版本历史")
            else:
                for cid in sorted(summary):
                    s = summary[cid]
                    print("%s  %d 版  最新 v%03d（%s，%d 字，reason=%s）"
                          % (cid, s["count"], s["latest_seq"],
                             time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(s["latest_ts"])),
                             s["chars"], s["latest_reason"]))
    return 0


def history_restore_text(tech_dir, ch_id, seq):
    """供 cmd_tech_history 读取版本文本（与 store.write_chapter_body 解耦的取文本入口）。"""
    return read_version(tech_dir, ch_id, seq)
