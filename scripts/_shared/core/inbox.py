# -*- coding: utf-8 -*-
"""⑦ core 拆包 · 企业归属校验 + 归档（propose / apply / 同名冲突）。"""
import re
import shutil
from collections import defaultdict
from pathlib import Path

from .. import naming as nm

from .basic import (CLASSIFY_DIRS, LibraryError, META_JSON, PERSON_SUBDIRS,
                    _name_tokens, lib_root, norm_rel, now_iso, read_json,
                    rel_to_path, today_str)
from .batch import Inbox
from .ledger import load_ledger, new_ledger_row, save_ledger
from .lib import Library
from .trash import lib_rel, move_to_trash

__all__ = ["ownership_check", "_suggest_fields", "_group_hint", "propose",
           "_target_rel", "_strip_page_suffix", "_ledger_person", "_name_conflict_hit",
           "_recalc_conflict", "apply"]


# --------------------------------------------------------------------------
# 企业归属校验（文件名层）
# --------------------------------------------------------------------------
def ownership_check(ent, filename, extra_text=None):
    """
    依据文件名（及 agent 传入的正文/OCR 文本）判断素材是否疑似属于别的企业。
    返回 {"status": match|conflict|unknown, ...}
    """
    ent = Path(ent)
    meta = read_json(lib_root(ent) / META_JSON, {}) or {}
    my_name = meta.get("name") or ent.name
    my_tokens = _name_tokens(my_name)

    text = "%s %s" % (filename or "", extra_text or "")
    lib = Library(ent.parent)
    for other in lib.enterprises():
        if other == ent.name:
            continue
        other_meta = read_json(lib_root(ent.parent / other) / META_JSON, {}) or {}
        for t in _name_tokens(other_meta.get("name") or other):
            if t and t in text and t not in my_tokens:
                return {"status": "conflict", "other": other, "token": t}
    for t in my_tokens:
        if t and t in text:
            return {"status": "match", "token": t}
    return {"status": "unknown"}


# --------------------------------------------------------------------------
# 归档建议（propose）
# --------------------------------------------------------------------------
def _suggest_fields(filename, category, subtype, today=None):
    """从文件名里尽力抽出关键字与日期（供归档建议；人工/agent 可再修正）。"""
    today = today or today_str()
    stem, ext = nm.split_ext(filename)
    base, page = nm.split_page(stem)
    dates = nm.extract_dates(base)

    # 去掉日期与水印式分隔，切成候选 token
    rest = base
    for d in dates:
        rest = rest.replace(d, "_")
    rest = re.sub(r"[_\-]{2,}", "_", rest).strip("_-")
    tokens = [t for t in re.split(r"[_\-]", rest) if t]

    # 规则里的常量段（如「营业执照」「身份证」「简历」）不应留在关键字里
    try:
        segs = nm.get_rule(category, subtype)["segs"] if (category and subtype) else []
    except nm.NamingError:
        segs = []
    consts = [s[1] for s in segs if s[0] == nm.CONST]

    def strip_consts(ts):
        out = []
        for t in ts:
            v = t
            for c in consts:
                v = v.replace(c, "")
            if v.strip():
                out.append(v.strip())
        return out

    def side_of(text):
        if "国徽" in text or "背面" in text:
            return "国徽面"
        if "人像" in text or "正面" in text:
            return "人像面"
        return None

    keywords = []
    if category == "人员" and subtype == "身份证":
        side = side_of(base)
        keywords = [side] if side else []
        tokens = [t for t in strip_consts(tokens) if not any(k in t for k in ("正面", "背面"))]
    elif category == "人员" and subtype == "简历":
        dates = dates or [today]          # 简历按上传日期
        keywords = []
        tokens = strip_consts(tokens)
    elif subtype == "营业执照":
        keywords = [t for t in tokens if ("正本" in t or "副本" in t)]
        tokens = []
    elif subtype == "退休证":
        keywords = strip_consts(tokens)
        dates = dates or [nm.LONG_TERM]   # 退休证默认长期
        tokens = []
    elif subtype == "返聘协议":
        keywords = strip_consts(tokens)
        tokens = []
    else:
        toks = strip_consts(tokens)
        keywords = [toks[0]] if toks else []
        tokens = toks

    return {
        "keywords": keywords,
        "dates": dates,
        "page": page,
        "ext": ext,
        "stem": base,
        "leftover_tokens": tokens[1:] if (tokens and subtype not in ("营业执照", "退休证", "返聘协议")) else [],
    }


def _group_hint(items):
    """按主体名相似度给出多页归组提示（弱启发，最终由用户圈选）。"""
    buckets = {}
    for it in items:
        stem, _ = nm.split_ext(it.get("original_name", ""))
        base, page = nm.split_page(stem)
        key = re.sub(r"\d+$", "", base).strip("_-（）() ")
        buckets.setdefault(key, []).append(it.get("seq"))
    return {k: v for k, v in buckets.items() if len(v) > 1}


def propose(ent, require_closed=True):
    """为收件箱当前批次生成归档建议（供用户确认/修改）。"""
    ent = Path(ent)
    inbox = Inbox(ent)
    batch = inbox.load()
    if not batch:
        raise LibraryError("收件箱为空，无可归档内容（请先 open-inbox → upload → close-inbox）")
    if require_closed and not batch.get("closed_at"):
        raise LibraryError("收件箱尚未关闭（请先执行 close-inbox，再生成归档建议）")

    meta = read_json(lib_root(ent) / META_JSON, {}) or {}
    owner = meta.get("owner") or meta.get("name") or ent.name

    # 已有台账：同类别 → 关键字集合 + 主体（人员类按 rel_path 提取姓名）索引，用于归档时同名判定
    cat_index = defaultdict(list)
    for r in load_ledger(ent):
        c = r.get("category") or ""
        s = r.get("subtype") or ""
        kws = {k.strip() for k in str(r.get("keywords") or "").split("、") if k.strip()}
        rel = r.get("rel_path") or ""
        parts = rel.split("/")
        person = parts[1] if len(parts) > 1 and parts[0] == "人员" else ""
        cat_index[(c, s)].append({"rel_path": rel, "kw": kws, "person": person})

    items_out = []
    for it in inbox.items(order="seq"):
        orig = it.get("original_name", "")
        cat, sub, hit = nm.classify(orig)
        sug = _suggest_fields(orig, cat, sub)
        ownership = ownership_check(ent, orig)

        item = {
            "seq": it.get("seq"),
            "inbox_file": it.get("file"),
            "original_name": orig,
            "written_at": it.get("written_at"),
            "sha256": it.get("sha256"),
            "decision": "archive" if cat else "pending",
            "category": cat or "",
            "subtype": sub or "",
            "classify_hit": hit or "",
            "person": "",
            "project_folder": "",
            "keywords": sug["keywords"],
            "dates": sug["dates"],
            "date_type": nm.CATEGORY_META.get(cat, {}).get("date_label", ""),
            "page": sug["page"],
            "group_id": "",
            "final_name": "",
            "on_conflict": "",
            "ownership": ownership.get("status", "unknown"),
            "ownership_detail": ownership,
            "needs_input": [],
            "note": "",
            "is_name_conflict": False,
            "conflict_with": [],
            "conflict_in_batch": False,
        }
        # 同名检测：同大类 + 同子类；人员类须同人（person 未定时 apply 兜底重算），
        # 关键字排除等级/类型固定词后交集；固定词子类（简历/退休证等）同人即同名；
        # 同一素材的多页分页（同基名仅页码不同）不算冲突。
        if cat and sub:
            my_person = (item.get("person") or "").strip()
            conflict_existing = []
            for e in cat_index.get((cat, sub), []):
                e_item = {"category": cat, "subtype": sub, "person": my_person,
                          "keywords": item.get("keywords"),
                          "rel_path": e["rel_path"]}
                if _name_conflict_hit(e_item, {"category": cat, "subtype": sub,
                                               "keywords": "、".join(sorted(e["kw"])),
                                               "rel_path": e["rel_path"]}):
                    conflict_existing.append(e["rel_path"])
            conflict_in_batch = False
            for other in items_out:
                if other.get("seq") == item["seq"]:
                    continue
                if (other.get("category"), other.get("subtype")) != (cat, sub):
                    continue
                try:
                    my_base = nm.build_name(cat, sub, keywords=item.get("keywords"),
                                            dates=item.get("dates"), page=None)
                    o_base = nm.build_name(cat, sub, keywords=other.get("keywords"),
                                           dates=other.get("dates"), page=None)
                except Exception:
                    my_base = o_base = None
                if my_base and o_base and my_base == o_base:
                    continue   # 同基名不同页码（多页分页）
                if _name_conflict_hit(item, other):
                    conflict_in_batch = True
                    break
            if conflict_existing or conflict_in_batch:
                item["is_name_conflict"] = True
                item["on_conflict"] = ""  # 同名必须由用户确认处理方式（keep_both / skip / trash_old）
                item["conflict_with"] = conflict_existing
                item["conflict_in_batch"] = conflict_in_batch
        if not cat:
            item["needs_input"].append("请指定大类/子类（无法自动识别）")
        if cat == "人员" and sub != "简历":
            item["needs_input"].append("请提供人员姓名（作为人员子目录）")
        if cat == "业绩":
            item["needs_input"].append("请提供项目文件夹名（项目全名关键字_签订日期_总监）")
        if cat and sub:
            try:
                nm.build_name(cat, sub, keywords=item["keywords"], dates=item["dates"], page=item["page"])
            except nm.NamingError as e:
                item["needs_input"].append("字段不足：%s" % e)
        items_out.append(item)

    return {
        "enterprise": ent.name,
        "owner": owner,
        "batch_id": batch.get("batch_id"),
        "created_at": now_iso(),
        "time_collision": inbox.has_time_collision(),
        "group_hint": _group_hint(inbox.items()),
        "items": items_out,
    }


# --------------------------------------------------------------------------
# 归档执行（apply）——拆分至 inbox_apply.py（行数治理），此处 re-export 保持对外接口
# --------------------------------------------------------------------------
from .inbox_apply import (apply, _target_rel, _strip_page_suffix,  # noqa: E402,F401
                          _ledger_person, _name_conflict_hit, _recalc_conflict)



# --------------------------------------------------------------------------
