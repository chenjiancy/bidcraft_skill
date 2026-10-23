# -*- coding: utf-8 -*-
"""
bidcraft · M6 技术标制作 —— 存储层（T4，纯文件系统，无 agent / 无 CLI）

职责（契约 §2 目录与产物 / §8 状态机）：
  1. `技术标/` 目录骨架：章节/、章节/.meta/、检查/、产出/、源文件/；
  2. `章节树.json` 原子读写（写前 F2 校验，写后回读一致性）；
  3. 各章正文落盘 / 回读；重写前旧正文进 `.rewrite-trash/<时间戳>/`；
  4. 上下文包 / 自述块 / 状态文件落 `.meta/`；
  5. 状态机推进（调用 F8）+ 闸门 `confirmLog` 记录；
  6. **项目内路径硬校验**：任何相对路径 resolve 后越出基目录即抛 `LibraryError`；
  7. Windows 文件锁重试（EPERM/EACCES/EBUSY，20/40/80/160/320ms 共 5 次）。

本层只做确定性 I/O，不生成正文、不判断内容质量。
"""
import errno
import json
import os
import shutil
import time
from datetime import datetime
from pathlib import Path

from _shared import core
from m4_tender import rules as t_rules

from . import rules as m6rules
from .rules_base import GATES, ID_PATTERN, STATUSES

TECH_DIR = "技术标"
TREE_FILE = "章节树.json"
SUBDIRS = ("章节", "章节/.meta", "检查", "产出", "源文件")
TRASH_DIR = ".rewrite-trash"
CTX_SCHEMA = "m6.ctx/v1"
STATE_SCHEMA = "m6.state/v1"
RETRY_DELAYS = (0.02, 0.04, 0.08, 0.16, 0.32)


# ---------------------------------------------------------------------------
# 路径与目录
# ---------------------------------------------------------------------------
def tech_path(ent_dir, project):
    """企业目录 + 项目名 → 技术标目录（不创建）。"""
    return Path(ent_dir) / "项目级" / project / TECH_DIR


def ensure_tech_dir(ent_dir, project):
    """校验项目名并创建 技术标/ 骨架；项目目录不存在则拒绝（防串项目）。"""
    ok, issue = t_rules.validate_project_name(project)
    if not ok:
        raise core.LibraryError("项目名非法：%s" % issue)
    proj_dir = Path(ent_dir) / "项目级" / project
    if not proj_dir.is_dir():
        raise core.LibraryError("项目不存在：%s（请先完成 M4/M5 或 tech-init 建项目）" % proj_dir)
    tech = proj_dir / TECH_DIR
    for sub in SUBDIRS:
        (tech / sub).mkdir(parents=True, exist_ok=True)
    return tech


def _inside(base, rel, label="路径"):
    """相对路径 resolve 后必须位于 base 内，否则拒绝（符号链接/`..` 一并覆盖）。"""
    base = Path(base).resolve()
    raw = str(rel).replace("\\", "/")
    target = (base / raw).resolve()
    try:
        target.relative_to(base)
    except ValueError:
        raise core.LibraryError("%s越界（必须在 %s 内）：%s" % (label, base, rel))
    return target


def _check_chapter_id(ch_id):
    if not isinstance(ch_id, str) or not ID_PATTERN.match(ch_id):
        raise core.LibraryError("章节 id 非法（须形如 ch-01）：%r" % (ch_id,))


# ---------------------------------------------------------------------------
# 原子写 / 回读
# ---------------------------------------------------------------------------
def _is_lock_error(e):
    return (e.errno in (errno.EACCES, errno.EPERM, errno.EBUSY)
            or getattr(e, "winerror", None) in (5, 32, 33))


def _write_text(path, text):
    """原子写（tmp→replace）+ Windows 文件锁退避；失败抛 LibraryError。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    last = None
    for i in range(len(RETRY_DELAYS) + 1):
        try:
            tmp.write_text(text, encoding="utf-8")
            os.replace(str(tmp), str(path))
            return path
        except OSError as e:
            if not _is_lock_error(e):
                raise core.LibraryError("落盘失败：%s（%s）" % (path, e))
            last = e
            if i < len(RETRY_DELAYS):
                time.sleep(RETRY_DELAYS[i])
    raise core.LibraryError("落盘失败（文件被占用，重试 %d 次）：%s（%s）"
                            % (len(RETRY_DELAYS) + 1, path, last))


def _read_text(path):
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError as e:
        raise core.LibraryError("读取失败：%s（%s）" % (path, e))


def _dump(obj):
    return json.dumps(obj, ensure_ascii=False, indent=2) + "\n"


def _write_and_verify(path, text, label):
    _write_text(path, text)
    back = _read_text(path)
    if back != text:
        raise core.LibraryError("%s回读不一致：%s" % (label, path))
    return path


def read_json_inside(base, rel):
    """读取基目录内 JSON（越界拒绝）。"""
    p = _inside(base, rel, "数据源")
    if not p.is_file():
        raise core.LibraryError("文件不存在：%s" % p)
    try:
        return json.loads(_read_text(p))
    except ValueError as e:
        raise core.LibraryError("JSON 解析失败：%s（%s）" % (p, e))


def write_json_inside(base, rel, obj):
    """写 JSON 到基目录内（越界拒绝，原子 + 回读）。"""
    p = _inside(base, rel, "产物")
    text = _dump(obj)
    _write_and_verify(p, text, "JSON")
    try:
        if json.loads(_read_text(p)) != obj:
            raise core.LibraryError("JSON 回读内容不一致：%s" % p)
    except ValueError:
        raise core.LibraryError("JSON 回读解析失败：%s" % p)
    return p


def write_text_inside(base, rel, text):
    """写文本到基目录内（越界拒绝，原子 + 回读）。"""
    p = _inside(base, rel, "产物")
    return _write_and_verify(p, text, "文本")


# ---------------------------------------------------------------------------
# 章节树
# ---------------------------------------------------------------------------
def tree_path(tech_dir):
    return Path(tech_dir) / TREE_FILE


def read_tree(tech_dir):
    """读 章节树.json（不存在/损坏即抛 LibraryError）。"""
    p = tree_path(tech_dir)
    if not p.is_file():
        raise core.LibraryError("章节树不存在：%s（请先 tech-outline）" % p)
    try:
        obj = json.loads(_read_text(p))
    except ValueError as e:
        raise core.LibraryError("章节树 JSON 损坏：%s（%s）" % (p, e))
    if not isinstance(obj, dict):
        raise core.LibraryError("章节树顶层必须是对象：%s" % p)
    return obj


def write_tree(tech_dir, tree, presets=None):
    """F2 校验通过后原子落盘并回读；校验失败不覆盖旧文件。"""
    ok, issues = m6rules.validate_chapters_final(tree, presets)
    if not ok:
        detail = "\n".join("[%s] %s" % (i["code"], i["message"]) for i in issues if i["level"] == "error")
        raise core.LibraryError("章节树校验失败，未落盘：\n%s" % detail)
    p = tree_path(tech_dir)
    _write_and_verify(p, _dump(tree), "章节树")
    try:
        if json.loads(_read_text(p)) != tree:
            raise core.LibraryError("章节树回读内容不一致：%s" % p)
    except ValueError:
        raise core.LibraryError("章节树回读解析失败：%s" % p)
    return p


def list_chapters(tree):
    return [c for c in (tree.get("chapters") or []) if isinstance(c, dict)]


def find_chapter(tree, ch_id):
    for ch in list_chapters(tree):
        if ch.get("id") == ch_id:
            return ch
    raise core.LibraryError("章节不存在：%s" % ch_id)


# ---------------------------------------------------------------------------
# 正文
# ---------------------------------------------------------------------------
def chapter_body_path(tech_dir, chapter):
    files = chapter.get("files") if isinstance(chapter, dict) else None
    if not isinstance(files, dict) or not files.get("body"):
        raise core.LibraryError("章节缺少 files.body：%s" % (chapter.get("id") if isinstance(chapter, dict) else chapter))
    return _inside(tech_dir, files["body"], "章节正文")


def read_chapter_body(tech_dir, chapter):
    p = chapter_body_path(tech_dir, chapter)
    if not p.is_file():
        raise core.LibraryError("章节正文不存在：%s" % p)
    return _read_text(p)


def backup_rewrite(tech_dir, path):
    """旧正文 → `.rewrite-trash/<时间戳>/<原文件名>`；返回备份路径。"""
    src = Path(path)
    if not src.is_file():
        return None
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")[:-3]
    dst_dir = Path(tech_dir) / TRASH_DIR / stamp
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / src.name
    try:
        shutil.copy2(str(src), str(dst))
    except OSError as e:
        raise core.LibraryError("旧正文备份失败：%s（%s）" % (src, e))
    return dst


def write_chapter_body(tech_dir, chapter, text, backup=True):
    """正文落盘 + 回读；已存在则先入回收站（重写可还原）。"""
    if not isinstance(text, str) or not text.strip():
        raise core.LibraryError("正文为空，拒绝落盘：%s" % (chapter.get("id") if isinstance(chapter, dict) else chapter))
    p = chapter_body_path(tech_dir, chapter)
    if backup and p.is_file() and _read_text(p) != text:
        backup_rewrite(tech_dir, p)
    return _write_and_verify(p, text, "章节正文")


# ---------------------------------------------------------------------------
# .meta：上下文包 / 自述块 / 状态
# ---------------------------------------------------------------------------
def _meta_path(tech_dir, ch_id, suffix):
    _check_chapter_id(ch_id)
    return _inside(tech_dir, "章节/.meta/%s%s" % (ch_id, suffix), ".meta 路径")


def write_context_pack(tech_dir, ch_id, pack):
    """写上下文包（P3 注入快照）；schema 必须为 m6.ctx/v1。"""
    if not isinstance(pack, dict) or pack.get("schema") != CTX_SCHEMA:
        raise core.LibraryError("上下文包 schema 必须为 %s" % CTX_SCHEMA)
    p = _meta_path(tech_dir, ch_id, ".json")
    _write_and_verify(p, _dump(pack), "上下文包")
    return p


def read_context_pack(tech_dir, ch_id):
    p = _meta_path(tech_dir, ch_id, ".json")
    if not p.is_file():
        raise core.LibraryError("上下文包不存在：%s（请先 tech-ctx）" % p)
    try:
        return json.loads(_read_text(p))
    except ValueError as e:
        raise core.LibraryError("上下文包 JSON 损坏：%s（%s）" % (p, e))


def write_selfcheck(tech_dir, ch_id, info):
    """写自述块解析结果（parse_selfcheck_block 的 info）→ `.meta/ch-xx.selfcheck.json`。"""
    if not isinstance(info, dict) or info.get("block") not in ("M6-COVERAGE", "M6-REVISE"):
        raise core.LibraryError("自述块 info 非法（须含 block=M6-COVERAGE/M6-REVISE）")
    if not isinstance(info.get("data"), dict):
        raise core.LibraryError("自述块 info.data 必须是对象")
    payload = {"chapter": ch_id, "block": info["block"], "data": info["data"],
               "createdAt": core.now_iso()}
    p = _meta_path(tech_dir, ch_id, ".selfcheck.json")
    _write_and_verify(p, _dump(payload), "自述块")
    return p


def read_selfcheck(tech_dir, ch_id):
    p = _meta_path(tech_dir, ch_id, ".selfcheck.json")
    if not p.is_file():
        return None
    try:
        return json.loads(_read_text(p))
    except ValueError as e:
        raise core.LibraryError("自述块 JSON 损坏：%s（%s）" % (p, e))


def write_revise(tech_dir, ch_id, info):
    """写 P5 精修变更块（M6-REVISE）→ `.meta/ch-xx.revise.json`（独立于 COVERAGE，避免覆盖）。"""
    if not isinstance(info, dict) or info.get("block") != "M6-REVISE":
        raise core.LibraryError("精修块 info 非法（须含 block=M6-REVISE）")
    if not isinstance(info.get("data"), dict):
        raise core.LibraryError("精修块 info.data 必须是对象")
    payload = {"chapter": ch_id, "block": "M6-REVISE", "data": info["data"],
               "createdAt": core.now_iso()}
    p = _meta_path(tech_dir, ch_id, ".revise.json")
    _write_and_verify(p, _dump(payload), "精修变更块")
    return p


def read_revise(tech_dir, ch_id):
    p = _meta_path(tech_dir, ch_id, ".revise.json")
    if not p.is_file():
        return None
    try:
        return json.loads(_read_text(p))
    except ValueError as e:
        raise core.LibraryError("精修变更块 JSON 损坏：%s（%s）" % (p, e))


def write_state(tech_dir, ch_id, status, history=None):
    """写章节状态文件（状态机唯一落盘处之一，与章节树 status 同步）。"""
    if status not in STATUSES:
        raise core.LibraryError("非法状态：%r（允许 %s）" % (status, "/".join(STATUSES)))
    payload = {"schema": STATE_SCHEMA, "id": ch_id, "status": status,
               "updatedAt": core.now_iso(), "history": history or []}
    p = _meta_path(tech_dir, ch_id, ".state.json")
    _write_and_verify(p, _dump(payload), "状态文件")
    return p


def read_state(tech_dir, ch_id):
    p = _meta_path(tech_dir, ch_id, ".state.json")
    if not p.is_file():
        return None
    try:
        return json.loads(_read_text(p))
    except ValueError as e:
        raise core.LibraryError("状态文件 JSON 损坏：%s（%s）" % (p, e))


# ---------------------------------------------------------------------------
# 状态机推进 / 闸门
# ---------------------------------------------------------------------------
def advance_chapter(tech_dir, ch_id, to_state, presets=None):
    """按 F8 迁移表推进一章：写状态文件 + 更新章节树（两步都成功后返回新树）。"""
    tree = read_tree(tech_dir)
    ch = find_chapter(tree, ch_id)
    cur = ch.get("status") or "PENDING"
    ok, reason = m6rules.validate_transition(cur, to_state)
    if not ok:
        raise core.LibraryError(reason)
    state = read_state(tech_dir, ch_id) or {"history": []}
    history = list(state.get("history") or [])
    history.append({"from": cur, "to": to_state, "at": core.now_iso()})
    ch["status"] = to_state
    write_tree(tech_dir, tree, presets)   # 先校验并落盘权威树，再写状态快照
    write_state(tech_dir, ch_id, to_state, history)
    return tree


def confirm_gate(tech_dir, gate, note="", presets=None):
    """记录人工闸门（outline/write/final）；outline 同时置 `confirmed: true`。"""
    if gate not in GATES:
        raise core.LibraryError("非法闸门：%r（允许 %s）" % (gate, "/".join(GATES)))
    tree = read_tree(tech_dir)
    record = {"gate": gate, "at": core.now_iso(), "note": note or ""}
    tree.setdefault("confirmLog", []).append(record)
    if gate == "outline":
        tree["confirmed"] = True
    write_tree(tech_dir, tree, presets)
    return record


def outline_confirmed(tree):
    """闸门① 是否已确认（契约 §5：confirmed:true 或存在 confirmLog）。"""
    if not isinstance(tree, dict):
        return False
    return bool(tree.get("confirmed")) or bool(tree.get("confirmLog"))
