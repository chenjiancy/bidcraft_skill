# -*- coding: utf-8 -*-
"""⑨ core 拆包 · 归档执行（apply 组：目标路径 / 同名冲突 / 执行归档）。

从 inbox.py 拆分（文件行数治理），对外接口经 inbox.py re-export 保持兼容：
  core.apply / core._target_rel / core._strip_page_suffix / core._ledger_person /
  core._name_conflict_hit / core._recalc_conflict
"""
import re
import shutil
from collections import defaultdict
from pathlib import Path

from .. import naming as nm

from .basic import (LibraryError, META_JSON, PERSON_SUBDIRS, lib_root, norm_rel,
                    read_json, rel_to_path, today_str)
from .batch import Inbox
from .ledger import load_ledger, new_ledger_row, save_ledger
from .trash import lib_rel, move_to_trash


# --------------------------------------------------------------------------
# 归档执行（apply）
# --------------------------------------------------------------------------
def _target_rel(ent, item):
    """计算归档目标相对路径。"""
    cat = item.get("category")
    sub = item.get("subtype")
    if not cat:
        raise LibraryError("条目 %s 缺少大类" % item.get("inbox_file"))

    if item.get("final_name"):
        fname = item["final_name"]
        # final_name 不带扩展名时自动补源文件扩展名（避免归档后丢后缀）
        _, cur_ext = nm.split_ext(fname)
        if not cur_ext:
            ext = item.get("ext") or nm.split_ext(item.get("original_name", ""))[1]
            if ext:
                fname += ext
    else:
        fname = nm.build_name(
            cat, sub,
            keywords=item.get("keywords"),
            dates=item.get("dates"),
            page=item.get("page") if item.get("page") is not None else None,
            ext=None,
        )
        ext = item.get("ext") or nm.split_ext(item.get("original_name", ""))[1]
        if ext:
            fname += ext

    if cat == "人员":
        person = (item.get("person") or "").strip()
        if not person:
            raise LibraryError("人员素材必须提供 person（%s）" % item.get("inbox_file"))
        sub_dir = sub or "其他"
        if sub_dir not in PERSON_SUBDIRS:
            # 动态扩展：允许新子类，但记录
            pass
        return norm_rel("/".join([cat, nm.sanitize_keyword(person), sub_dir, fname]))

    if cat == "业绩":
        pf = (item.get("project_folder") or "").strip()
        if not pf:
            raise LibraryError("业绩素材必须提供 project_folder（%s）" % item.get("inbox_file"))
        return norm_rel("/".join([cat, pf, fname]))

    if cat == "财务":
        # 财务大类按子类建子目录（如 财务/中小企业声明函/…）
        sub_dir = sub or "财务证照"
        return norm_rel("/".join([cat, sub_dir, fname]))

    return norm_rel("/".join([cat, fname]))


def _strip_page_suffix(fname):
    """去除文件名扩展名与多页分页后缀（_P0/_P1/…），得到素材基名。"""
    noext = str(fname).rsplit(".", 1)[0] if "." in str(fname) else str(fname)
    return re.sub(r"_P\d*$", "", noext)


def _ledger_person(rel_path):
    """从台账 rel_path 提取人员类主体姓名（rel_path 形如 人员/<姓名>/…）。"""
    parts = (rel_path or "").split("/")
    return parts[1] if len(parts) > 1 and parts[0] == "人员" else ""


def _name_conflict_hit(item, r):
    """判断提案条目与台账记录是否构成同名。

    同大类 + 同子类；人员类必须同人，且关键字（排除等级/类型固定词后）有交集；
    无实质关键字的固定词子类（如简历/退休证）同人即同名。非人员类按关键字交集。
    同一素材的多页分页（基名相同仅页码不同）不构成同名。
    """
    if item.get("final_name"):
        base_f = _strip_page_suffix(str(item["final_name"]))
    else:
        try:
            base_f = nm.build_name(
                item.get("category"), item.get("subtype") or nm.DEFAULT_SUBTYPE.get(item.get("category")),
                keywords=item.get("keywords"), dates=item.get("dates"), page=None)
        except Exception:
            base_f = None
    r_base = (r.get("rel_path") or "").rsplit("/", 1)[-1]
    if base_f and r_base.startswith(base_f + "_P"):
        return False
    my_kw = {k.strip() for k in (item.get("keywords") or []) if str(k).strip()}
    r_kw = {k.strip() for k in str(r.get("keywords") or "").split("、") if k.strip()}
    if (item.get("category") or "") == "人员":
        my_person = (item.get("person") or "").strip()
        r_person = _ledger_person(r.get("rel_path", ""))
        if not (my_person and r_person and my_person == r_person):
            return False
        sub = item.get("subtype") or ""
        if sub in ("职称证书", "退休证"):
            # 职称证书/退休证：实质标识在基名中（职称=等级+专业；退休证=退休证_长期 等固定名），
            # 基名相同才判同名；final_name 显式指定时优先以其为基名（可含类型区分，如 退休证_登记表）
            if item.get("final_name"):
                my_base = _strip_page_suffix(str(item["final_name"]))
            else:
                try:
                    my_base = nm.build_name("人员", sub, keywords=item.get("keywords"),
                                            dates=item.get("dates"), page=None)
                except Exception:
                    my_base = None
            r_base = (r.get("rel_path") or "").rsplit("/", 1)[-1]
            r_clean = _strip_page_suffix(r_base)
            return bool(my_base and r_clean == my_base)
        # 其余人员类子类（注册证书/岗位证书/身份证/简历/退休证/返聘协议/个人荣誉等）：
        # 无独立身份标识，同人同子类即视为同名（新素材更新旧素材）
        return True
    return bool(my_kw & r_kw)


def _recalc_conflict(ent, item, rows):
    """以最终提案字段实时重算同名冲突。

    propose 生成提案时 person/keywords 可能为空（脚本无法从文件名语义认出主体），
    而 agent 会在提案中补齐（如固定词子类简历的 person）。apply 前以最终字段重算：
    同大类+同子类 → 关键字有交集 → 同名；关键字为空（固定词子类）→ 同主体
    （人员类按 rel_path 中的姓名）→ 同名（删除/更新语义）。
    命中且未确认 on_conflict 时置空（apply 将拒绝）；未命中则取消同名标记。
    """
    cat = item.get("category") or ""
    sub = item.get("subtype") or ""
    if not cat or not sub:
        return
    hits = []
    for r in rows:
        if (r.get("category") or "", r.get("subtype") or "") != (cat, sub):
            continue
        if _name_conflict_hit(item, r):
            hits.append(norm_rel(r.get("rel_path", "")))
    if hits:
        item["is_name_conflict"] = True
        item["conflict_with"] = hits
        # on_conflict 保持提案状态：默认 ""（未确认 → apply 拒绝）或用户显式确认值
        # （keep_both 并存 / trash_old 删除更新 / skip 跳过）
    else:
        item["is_name_conflict"] = False
        item["conflict_with"] = []


def apply(ent, proposal, require_closed=True):
    """按提案执行归档：改名 → 移动 → 写台账 → 清理收件箱。"""
    ent = Path(ent)
    inbox = Inbox(ent)
    batch = inbox.load()
    if not batch:
        raise LibraryError("收件箱为空，无法归档")
    if require_closed and not batch.get("closed_at"):
        raise LibraryError("收件箱尚未关闭（请先执行 close-inbox）")

    meta = read_json(lib_root(ent) / META_JSON, {}) or {}
    owner = meta.get("owner") or meta.get("name") or ent.name

    rows = load_ledger(ent)
    index = {norm_rel(r.get("rel_path", "")): r for r in rows}

    results = {"archived": [], "skipped": [], "trashed": [], "failed": []}
    handled_files = []

    by_seq = {i.get("seq"): i for i in batch.get("items", [])}

    # 单页去页码：同 target 基名在本次批次内只出现一次且 page==0 → 视为单页，去掉 _P0
    _single_base_counts = defaultdict(int)
    for _item in proposal.get("items", []):
        if _item.get("decision", "archive") in ("skip", "delete"):
            continue
        try:
            _f = nm.build_name(
                _item.get("category"), _item.get("subtype") or nm.DEFAULT_SUBTYPE.get(_item.get("category")),
                keywords=_item.get("keywords"), dates=_item.get("dates"), page=None,
            )
        except (nm.NamingError, Exception):
            continue
        _single_base_counts[(_item.get("category"), _f)] += 1

    for item in proposal.get("items", []):
        seq = item.get("seq")
        it = by_seq.get(seq)
        if not it:
            results["failed"].append({"seq": seq, "error": "批次中无此条目（可能已归档）"})
            continue

        decision = item.get("decision", "archive")
        src = inbox.path_of(it["file"])

        if decision == "skip":
            results["skipped"].append({"seq": seq, "file": it["file"]})
            continue
        if decision == "delete":
            try:
                move_to_trash(ent, lib_rel("收件箱/%s" % it["file"]), reason="归档时用户选择删除")
                results["trashed"].append({"seq": seq, "file": it["file"]})
                handled_files.append(it["file"])
            except LibraryError as e:
                results["failed"].append({"seq": seq, "error": str(e)})
            continue

        # 以最终提案字段实时重算同名（person/keywords 常由 agent 在 propose 后补齐）
        _recalc_conflict(ent, item, rows)

        if item.get("is_name_conflict") and not item.get("on_conflict"):
            results["failed"].append({
                "seq": seq, "file": it["file"],
                "error": "关键字同名素材：请先确认处理方式（keep_both / skip / trash_old）后再 apply",
            })
            continue

        # 同名删除/更新：on_conflict=trash_old 时，conflict_with 中的旧素材入回收站并清理旧台账行
        if item.get("is_name_conflict") and item.get("on_conflict") == "trash_old":
            conflict_failed = None
            for old_rel in item.get("conflict_with") or []:
                try:
                    old_rel = norm_rel(str(old_rel))
                    move_to_trash(ent, lib_rel(old_rel), reason="被新素材更新替代")
                    rows[:] = [r for r in rows if norm_rel(r.get("rel_path", "")) != old_rel]
                    index.pop(old_rel, None)
                except LibraryError as e:
                    conflict_failed = "删除旧素材失败：%s" % str(e)
                    break
            if conflict_failed:
                results["failed"].append({"seq": seq, "file": it["file"], "error": conflict_failed})
                continue

        # 单页去页码：page==0 且该 target 基名在批次内唯一 → 视为单页（page=None，不生成 _P0）
        if item.get("page") == 0:
            try:
                _f = nm.build_name(
                    item.get("category"), item.get("subtype") or nm.DEFAULT_SUBTYPE.get(item.get("category")),
                    keywords=item.get("keywords"), dates=item.get("dates"), page=None,
                )
            except (nm.NamingError, Exception):
                _f = None
            if _f and _single_base_counts.get((item.get("category"), _f)) == 1:
                item["page"] = None

        try:
            rel = _target_rel(ent, item)
        except (LibraryError, nm.NamingError) as e:
            results["failed"].append({"seq": seq, "file": it["file"], "error": str(e)})
            continue

        dest = rel_to_path(lib_root(ent), rel)
        dest.parent.mkdir(parents=True, exist_ok=True)

        if dest.exists():
            mode = item.get("on_conflict", "keep_both")
            if mode == "skip":
                results["skipped"].append({"seq": seq, "file": it["file"], "reason": "目标已存在，跳过"})
                continue
            if mode == "trash_old":
                move_to_trash(ent, lib_rel(rel), reason="被新素材覆盖")
                rows[:] = [r for r in rows if norm_rel(r.get("rel_path", "")) != rel]
                index.pop(rel, None)
            else:  # keep_both
                stem, ext = nm.split_ext(dest.name)
                n = 2
                while True:
                    cand = dest.with_name("%s_%d%s" % (stem, n, ext))
                    if not cand.exists():
                        dest = cand
                        break
                    n += 1
                rel = norm_rel(dest.relative_to(lib_root(ent)).as_posix())

        shutil.move(str(src), str(dest))

        cat = item.get("category")
        sub = item.get("subtype") or nm.DEFAULT_SUBTYPE.get(cat, "")
        row = new_ledger_row(
            category=cat,
            subtype=sub,
            rel_path=rel,
            keywords="、".join(item.get("keywords") or []),
            dates="、".join(item.get("dates") or []),
            date_type=item.get("date_type") or nm.CATEGORY_META.get(cat, {}).get("date_label", ""),
            owner=owner,
            upload_date=today_str(),
            original_filename=it.get("original_name", ""),
            source="收件箱",
            group_id=item.get("group_id", ""),
            page_index="" if item.get("page") is None else item.get("page"),
            ext=nm.split_ext(dest.name)[1],
            note=item.get("note", ""),
        )
        rows.append(row)
        index[rel] = row
        handled_files.append(it["file"])
        results["archived"].append({"seq": seq, "rel_path": rel, "id": row["id"]})

    save_ledger(ent, rows)
    inbox.remove_items(handled_files)

    results["summary"] = {
        "archived": len(results["archived"]),
        "skipped": len(results["skipped"]),
        "trashed": len(results["trashed"]),
        "failed": len(results["failed"]),
        "ledger_total": len(rows),
    }
    return results
