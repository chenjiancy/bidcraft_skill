# -*- coding: utf-8 -*-
"""
bidcraft · M6 技术标制作 —— 章节树 / 覆盖矩阵 / 排版预设（F1/F2/F3/F11，无 I/O）

返回约定：校验类 `(ok, issues)`；issues = `[{level, code, message}]`，ok 表示无 error。
F3 返回 `{rows, ok, missing, weak}`（级别 error=未覆盖 / warn=弱覆盖）。
"""
from .rules_base import (
    _err, _warn, _has_error, _is_int, _num, _norm_idx, _cjk_set,
    SCHEMA_ID, BID_MODES, STATUSES, GATES, MAX_LEVEL, NO_PATTERN, ID_PATTERN,
    KEYPOINT_MIN, KEYPOINT_MAX, CHAPTER_WORD_SPLIT, DEPENDS_ENUM,
    DEFAULT_LAYOUT, LAYOUT_ALIAS_KEYS, DECORATION_ALIASES, COVER_RATIO,
)


# ---------------------------------------------------------------------------
# F1 / F2：章节树校验
# ---------------------------------------------------------------------------
def _check_chapters(chapters, score_items, final):
    """章节结构公共校验（F1/F2 共用）。final=True 时追加 status/files 校验。"""
    issues = []
    seen_ids, seen_nos = set(), set()
    rows = []
    for i, ch in enumerate(chapters):
        if not isinstance(ch, dict):
            issues.append(_err("ch.type", "chapters[%d] 必须是对象" % i))
            continue
        rows.append(ch)
        for k in ("id", "no", "title", "level", "scoreRefs", "keyPoints", "wordCnt"):
            if k not in ch:
                issues.append(_err("ch.missing", "chapters[%d].%s 缺失（强制字段）" % (i, k)))
        cid = ch.get("id")
        if not isinstance(cid, str) or not ID_PATTERN.match(cid):
            issues.append(_err("ch.id", "chapters[%d].id 非法（须形如 ch-01）：%r" % (i, cid)))
        elif cid in seen_ids:
            issues.append(_err("ch.id-dup", "章节 id 重复：%s" % cid))
        else:
            seen_ids.add(cid)

        no = ch.get("no")
        if not isinstance(no, str) or not NO_PATTERN.match(no):
            issues.append(_err("ch.no", "chapters[%d].no 非法（dewey 编号，如 1 / 2.1 / 2.1.3）：%r" % (i, no)))
        elif no in seen_nos:
            issues.append(_err("ch.no-dup", "章节编号重复：%s" % no))
        else:
            seen_nos.add(no)

        title = ch.get("title")
        if not isinstance(title, str) or not title.strip():
            issues.append(_err("ch.title", "chapters[%d].title 不能为空" % i))
        elif "\n" in title:
            issues.append(_err("ch.title", "chapters[%d].title 不能含换行" % i))

        level = ch.get("level")
        if not _is_int(level) or not (1 <= level <= MAX_LEVEL):
            issues.append(_err("ch.level", "chapters[%d].level 须为 1~%d 的整数：%r" % (i, MAX_LEVEL, level)))
        elif isinstance(no, str) and NO_PATTERN.match(no) and level != no.count(".") + 1:
            issues.append(_err("ch.level", "chapters[%d].level=%d 与编号 %s 的层级 %d 不一致"
                                % (i, level, no, no.count(".") + 1)))

        kps = ch.get("keyPoints")
        if not isinstance(kps, list) or not kps:
            issues.append(_err("ch.keypoints", "chapters[%d].keyPoints 必须是非空数组" % i))
        else:
            for j, kp in enumerate(kps):
                if not isinstance(kp, str) or not kp.strip():
                    issues.append(_err("ch.keypoint", "chapters[%d].keyPoints[%d] 必须是非空字符串" % (i, j)))
            if not (KEYPOINT_MIN <= len(kps) <= KEYPOINT_MAX):
                issues.append(_warn("ch.keypoint-cnt", "chapters[%d].keyPoints 建议 %d~%d 条（当前 %d）"
                                    % (i, KEYPOINT_MIN, KEYPOINT_MAX, len(kps))))

        wc = ch.get("wordCnt")
        if not _is_int(wc) or wc <= 0:
            issues.append(_err("ch.wordcnt", "chapters[%d].wordCnt 必须是正整数：%r" % (i, wc)))
        elif wc > CHAPTER_WORD_SPLIT:
            issues.append(_warn("ch.wordcnt-split", "chapters[%d].wordCnt=%d 超过 %d，按 P4 需拆小节"
                                % (i, wc, CHAPTER_WORD_SPLIT)))

        issues.extend(_check_score_refs(i, ch.get("scoreRefs"), score_items))

        dep = ch.get("dependsOnMaterials")
        if dep is None:
            issues.append(_warn("ch.depends-missing", "chapters[%d].dependsOnMaterials 缺失（R7）" % i))
        elif not isinstance(dep, list):
            issues.append(_err("ch.depends", "chapters[%d].dependsOnMaterials 必须是数组" % i))
        else:
            for d in dep:
                if d not in DEPENDS_ENUM:
                    issues.append(_err("ch.depends-enum", "chapters[%d].dependsOnMaterials 含非法枚举：%r"
                                        "（允许 %s）" % (i, d, "/".join(DEPENDS_ENUM))))

        if final:
            st = ch.get("status")
            if st not in STATUSES:
                issues.append(_err("ch.status", "chapters[%d].status 非法：%r（允许 %s）"
                                    % (i, st, "/".join(STATUSES))))
            files = ch.get("files")
            if not isinstance(files, dict):
                issues.append(_err("ch.files", "chapters[%d].files 必须是对象（body/meta）" % i))
            else:
                for k, ext in (("body", ".md"), ("meta", ".json")):
                    p = files.get(k)
                    if not isinstance(p, str) or not p:
                        issues.append(_err("ch.files", "chapters[%d].files.%s 缺失" % (i, k)))
                    elif p.startswith(("/", "\\")) or ".." in p.replace("\\", "/").split("/"):
                        issues.append(_err("ch.files-path", "chapters[%d].files.%s 必须是项目内相对路径：%s"
                                            % (i, k, p)))
                    elif not p.lower().endswith(ext):
                        issues.append(_err("ch.files-ext", "chapters[%d].files.%s 应为 %s：%s" % (i, k, ext, p)))
        elif ch.get("status") or ch.get("files"):
            issues.append(_warn("ch.system-field", "chapters[%d] 含 status/files 系统字段——P2 草案不应输出，由脚本回填" % i))

    # 编号连续性：父章存在 + 同父下末位序号连续（1..n）
    issues.extend(_check_numbering(rows))
    return issues


def _check_score_refs(i, refs, score_items):
    issues = []
    if not isinstance(refs, list) or not refs:
        return [_err("ch.scorerefs", "chapters[%d].scoreRefs 必须是非空数组" % i)]
    for j, ref in enumerate(refs):
        if not isinstance(ref, dict):
            issues.append(_err("ch.scoreref", "chapters[%d].scoreRefs[%d] 必须是对象" % (i, j)))
            continue
        idx = _norm_idx(ref.get("idx"))
        if idx is None or idx < 0:
            issues.append(_err("ch.scoreref-idx", "chapters[%d].scoreRefs[%d].idx 非法：%r" % (i, j, ref.get("idx"))))
        elif score_items is not None and idx >= len(score_items):
            issues.append(_err("ch.scoreref-range", "chapters[%d].scoreRefs[%d].idx=%d 越界（输入评分项共 %d 条）"
                                % (i, j, idx, len(score_items))))
        item = ref.get("item")
        if not isinstance(item, str) or not item.strip():
            issues.append(_err("ch.scoreref-item", "chapters[%d].scoreRefs[%d].item 不能为空" % (i, j)))
        elif score_items is not None and idx is not None and 0 <= idx < len(score_items):
            src = score_items[idx]
            src_item = src.get("item", "") if isinstance(src, dict) else str(src)
            if src_item and item.strip() not in src_item:
                issues.append(_warn("ch.scoreref-rewrite", "chapters[%d].scoreRefs[%d].item 与评分项原文不一致（疑似改写）：%s"
                                    % (i, j, item)))
        if "weight" in ref and not _num(ref.get("weight")):
            issues.append(_warn("ch.scoreref-weight", "chapters[%d].scoreRefs[%d].weight 应为数值" % (i, j)))
    return issues


def _check_numbering(rows):
    """父章存在 + 兄弟序号连续（1..n）。"""
    issues = []
    nos = [r.get("no") for r in rows if isinstance(r.get("no"), str) and NO_PATTERN.match(r["no"])]
    no_set = set(nos)
    groups = {}
    for no in nos:
        parent, _, last = no.rpartition(".")
        if no.count(".") == 0:
            parent, last = "", no
        if parent and parent not in no_set:
            issues.append(_err("ch.parent", "章节 %s 的父章 %s 不存在" % (no, parent)))
        groups.setdefault(parent, []).append(int(last))
    for parent, seq in groups.items():
        label = ("顶层" if not parent else "%s 下" % parent)
        want = list(range(1, len(seq) + 1))
        if sorted(seq) != want:
            issues.append(_err("ch.sequence", "%s 章节编号不连续（实际 %s，应为 1~%d）"
                                % (label, sorted(seq), len(seq))))
    return issues


def validate_chapters_draft(obj, score_items=None):
    """F1：P2 产出的章节树草案校验 → (ok, issues)。score_items 传入时校验 idx 范围。"""
    if not isinstance(obj, dict):
        return False, [_err("draft.type", "章节树草案顶层必须是对象")]
    chapters = obj.get("chapters")
    if not isinstance(chapters, list) or not chapters:
        return False, [_err("draft.empty", "chapters 必须是非空数组")]
    issues = []
    notes = obj.get("notes")
    if notes is not None and not isinstance(notes, list):
        issues.append(_warn("draft.notes", "notes 应为数组（编制说明）"))
    for k in ("status", "files", "layout", "estimate", "pageConstraint"):
        if k in obj:
            issues.append(_warn("draft.system-field", "P2 草案不应包含系统字段 %s（由脚本回填）" % k))
    issues.extend(_check_chapters(chapters, score_items, final=False))
    return (not _has_error(issues)), issues


def validate_chapters_final(obj, presets=None):
    """F2：落盘版章节树校验（结构 + 状态 + 路径 + 闸门记录）→ (ok, issues)。"""
    if not isinstance(obj, dict):
        return False, [_err("tree.type", "章节树顶层必须是对象")]
    issues = []
    if obj.get("schema") != SCHEMA_ID:
        issues.append(_err("tree.schema", "schema 必须为 %s：%r" % (SCHEMA_ID, obj.get("schema"))))
    if not isinstance(obj.get("project"), str) or not obj.get("project").strip():
        issues.append(_err("tree.project", "project 不能为空"))
    if obj.get("bidMode") not in BID_MODES:
        issues.append(_err("tree.bidmode", "bidMode 必须是 %s 之一：%r" % ("/".join(BID_MODES), obj.get("bidMode"))))

    pc = obj.get("pageConstraint")
    if not isinstance(pc, dict):
        issues.append(_err("tree.pages", "pageConstraint 必须是对象（max/estimate/charsPerPage/source）"))
    else:
        if not _is_int(pc.get("max")) or pc.get("max") <= 0:
            issues.append(_err("tree.pages-max", "pageConstraint.max 必须是正整数：%r" % (pc.get("max"),)))
        if not _num(pc.get("estimate")) or pc.get("estimate") < 0:
            issues.append(_err("tree.pages-est", "pageConstraint.estimate 必须是非负数：%r" % (pc.get("estimate"),)))
        if not _is_int(pc.get("charsPerPage")) or pc.get("charsPerPage") <= 0:
            issues.append(_err("tree.pages-cpp", "pageConstraint.charsPerPage 必须是正整数：%r"
                                % (pc.get("charsPerPage"),)))
        if not isinstance(pc.get("source"), str):
            issues.append(_warn("tree.pages-source", "pageConstraint.source 应为字符串（约束来源）"))

    st = obj.get("style")
    if not isinstance(st, dict):
        issues.append(_err("tree.style", "style 必须是对象（id/name/promptRef）"))
    else:
        for k in ("id", "name", "promptRef"):
            if not isinstance(st.get(k), str) or not st.get(k).strip():
                issues.append(_err("tree.style", "style.%s 不能为空" % k))

    term = obj.get("terminology")
    if not isinstance(term, dict) or not term:
        issues.append(_err("tree.terminology", "terminology 必须是非空对象（招标人/项目名称/服务期等）"))
    else:
        for k, v in term.items():
            if not isinstance(v, str) or not v.strip():
                issues.append(_err("tree.terminology", "terminology.%s 不能为空" % k))

    personnel = obj.get("personnel")
    if not isinstance(personnel, list):
        issues.append(_err("tree.personnel", "personnel 必须是数组（可为空）"))
    else:
        for i, p in enumerate(personnel):
            if not isinstance(p, dict):
                issues.append(_err("tree.personnel", "personnel[%d] 必须是对象" % i))
                continue
            for k in ("name", "post"):
                if not isinstance(p.get(k), str) or not p.get(k).strip():
                    issues.append(_err("tree.personnel", "personnel[%d].%s 不能为空" % (i, k)))
            if not p.get("source"):
                issues.append(_warn("tree.personnel", "personnel[%d].source 缺失（须可追溯到素材清单）" % i))

    layout = obj.get("layout")
    if not isinstance(layout, dict):
        issues.append(_err("tree.layout", "layout 必须是对象（preset/palette/cover/decoration）"))
    else:
        issues.extend(validate_layout(layout, presets, obj.get("bidMode"))[1])

    issues.extend(_check_confirm_log(obj.get("confirmLog")))

    chapters = obj.get("chapters")
    if not isinstance(chapters, list) or not chapters:
        issues.append(_err("tree.empty", "chapters 必须是非空数组"))
    else:
        issues.extend(_check_chapters(chapters, None, final=True))
    return (not _has_error(issues)), issues


def _check_confirm_log(log):
    if log is None:
        return []
    if not isinstance(log, list):
        return [_err("tree.confirmlog", "confirmLog 必须是数组")]
    issues, seen = [], set()
    for i, it in enumerate(log):
        if not isinstance(it, dict):
            issues.append(_err("tree.confirmlog", "confirmLog[%d] 必须是对象" % i))
            continue
        if it.get("gate") not in GATES:
            issues.append(_err("tree.confirmlog-gate", "confirmLog[%d].gate 非法：%r（允许 %s）"
                                % (i, it.get("gate"), "/".join(GATES))))
        elif it.get("gate") in seen:
            issues.append(_warn("tree.confirmlog-dup", "confirmLog 闸门重复记录：%s" % it["gate"]))
        else:
            seen.add(it["gate"])
        if not it.get("at"):
            issues.append(_warn("tree.confirmlog-time", "confirmLog[%d].at 缺失（确认时间）" % i))
    return issues


# ---------------------------------------------------------------------------
# F3：评分点覆盖矩阵（A1，Q2 名义 + 实覆盖双判）
# ---------------------------------------------------------------------------
def build_coverage(score_items, chapters):
    """评分项 × 章节覆盖 → {rows, ok, missing, weak}。"""
    rows = []
    chapters = [c for c in (chapters or []) if isinstance(c, dict)]
    for pos, si in enumerate(score_items or []):
        if not isinstance(si, dict):
            rows.append({"idx": pos, "item": str(si), "weight": None, "kind": None,
                         "enforced": True, "covered": False, "weak": False, "ratio": 0.0,
                         "chapters": [], "level": "error", "note": "评分项不是对象"})
            continue
        idx = _norm_idx(si.get("idx"))
        idx = pos if idx is None else idx
        item = si.get("item", "")
        kind = si.get("kind")
        hits = []
        for ch in chapters:
            for ref in (ch.get("scoreRefs") or []):
                if isinstance(ref, dict) and _norm_idx(ref.get("idx")) == idx:
                    hits.append(ch)
                    break
        covered = bool(hits)
        ratio = 1.0 if not _cjk_set(item) else 0.0
        if covered:
            item_chars = _cjk_set(item)
            kp_chars = set()
            for ch in hits:
                for kp in (ch.get("keyPoints") or []):
                    if isinstance(kp, str):
                        kp_chars |= _cjk_set(kp)
            ratio = (len(item_chars & kp_chars) / float(len(item_chars))) if item_chars else 1.0
        enforced = kind in (None, "", "outline", "subjective", "主观", "主观分")
        weak = covered and enforced and ratio < COVER_RATIO
        level = "error" if (enforced and not covered) else ("warn" if weak else None)
        note = ""
        if not covered and not enforced:
            note = "非主观分项（kind=%s），不强制覆盖" % kind
        elif weak:
            note = "名义覆盖但 keyPoints 与评分项汉字交集 %.2f < %.2f（疑似答非所问）" % (ratio, COVER_RATIO)
        elif not covered:
            note = "未命中任何章节 scoreRefs"
        rows.append({"idx": idx, "item": item, "weight": si.get("weight"), "kind": kind,
                     "enforced": enforced, "covered": covered, "weak": weak,
                     "ratio": round(ratio, 4), "chapters": [c.get("id") for c in hits],
                     "level": level, "note": note})
    missing = [r["idx"] for r in rows if r["level"] == "error"]
    weak = [r["idx"] for r in rows if r["level"] == "warn"]
    return {"rows": rows, "ok": not missing, "missing": missing, "weak": weak}


# ---------------------------------------------------------------------------
# F11：排版预设校验（D8）
# ---------------------------------------------------------------------------
def _preset_ids(presets, group):
    """预设清单 → id 列表；兼容字符串数组 / 对象数组({id:...}) / dict 三写法。"""
    src = presets if isinstance(presets, dict) else {}
    for key in LAYOUT_ALIAS_KEYS[group]:
        val = src.get(key)
        ids = []
        if isinstance(val, list):
            for v in val:
                if isinstance(v, str):
                    ids.append(v)
                elif isinstance(v, dict) and isinstance(v.get("id"), str) and v["id"]:
                    ids.append(v["id"])
        elif isinstance(val, dict):
            ids = [k for k in val.keys() if isinstance(k, str)]
        if ids:
            return ids
    return list(DEFAULT_LAYOUT[group])


def validate_layout(layout, presets=None, bid_mode="明标"):
    """四组预设 id 合法性 + 暗标禁用 image-underlay → (ok, issues)。"""
    if not isinstance(layout, dict):
        return False, [_err("layout.type", "layout 必须是对象")]
    issues = []
    chosen = {}
    for group in ("preset", "palette", "cover", "decoration"):
        val = layout.get(group)
        if not isinstance(val, str) or not val.strip():
            issues.append(_err("layout.missing", "layout.%s 缺失或为空" % group))
            continue
        val = DECORATION_ALIASES.get(val, val) if group == "decoration" else val
        chosen[group] = val
        allowed = _preset_ids(presets, group)
        if val not in allowed:
            issues.append(_err("layout.unknown", "layout.%s=%r 不在预设清单（允许 %s）"
                                % (group, val, "/".join(allowed))))
    if bid_mode == "暗标":
        if chosen.get("cover") == "image-underlay":
            issues.append(_err("layout.mixcover", "暗标禁用封面 image-underlay（图底压字可能泄露企业信息）"))
        if str(chosen.get("palette", "")).lower().startswith("enterprise"):
            issues.append(_warn("layout.enterprise-color", "暗标建议不使用企业配色：%s" % chosen["palette"]))
    overrides = layout.get("overrides")
    if overrides is not None:
        if not isinstance(overrides, dict):
            issues.append(_warn("layout.overrides", "layout.overrides 应为对象"))
        else:
            for k in overrides:
                if k not in ("headingFont", "bodyFont"):
                    issues.append(_warn("layout.overrides-key", "未知字体覆盖项：%s" % k))
    return (not _has_error(issues)), issues
