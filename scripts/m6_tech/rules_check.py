# -*- coding: utf-8 -*-
"""
bidcraft · M6 技术标制作 —— 篇幅 / 敏感词 / 一致性 / 占位 / 状态机 / 双通道（F4–F10，无 I/O）

返回约定：A3–A6 检查返回带 `level`（error/warn）的结构化列表，不抛异常；
F8 `(ok, reason)`；F9 `(info, error)`；F10 差异数组（四类，交用户裁决）。
"""
import json
import math
import re

from .rules_base import (
    _err, _warn, _is_int, _num, _locate, _cjk_set, _norm_idx,
    STATUSES, STATUS_FLOW, CJK_RE, WORD_RE, TABLE_LINE_RE, TABLE_SEP_RE,
    SENSITIVE_BUILTIN, SYNONYM_GROUPS, KNOWN_POSTS,
    PLACEHOLDER_PATTERNS, BLANK_LINE_RE, SELFCHECK_RE,
)


# ---------------------------------------------------------------------------
# F4：字数与页数（A3）
# ---------------------------------------------------------------------------
def count_chars(md):
    """剥离 Markdown 表格/符号后统计：中文按字、西文按词；正文与表格分开。"""
    out = {"body_cjk": 0, "body_words": 0, "table_cjk": 0, "table_words": 0}
    for line in (md or "").splitlines():
        if TABLE_SEP_RE.match(line):
            continue
        is_table = bool(TABLE_LINE_RE.match(line))
        text = line.strip().strip("|").replace("|", " ") if is_table else line
        cjk, words = len(CJK_RE.findall(text)), len(WORD_RE.findall(text))
        if is_table:
            out["table_cjk"] += cjk
            out["table_words"] += words
        else:
            out["body_cjk"] += cjk
            out["body_words"] += words
    out["cjk"] = out["body_cjk"] + out["table_cjk"]
    out["words"] = out["body_words"] + out["table_words"]
    out["body_chars"] = out["body_cjk"] + out["body_words"]
    out["table_chars"] = out["table_cjk"] + out["table_words"]
    return out


def estimate_pages(body_chars, table_chars=0, cfg=None):
    """按正文 charsPerPage（默认 1000）/ 表格 tableCharsPerPage（默认 500）估算页数。"""
    cfg = cfg if isinstance(cfg, dict) else {}
    cpp = cfg.get("charsPerPage") if _is_int(cfg.get("charsPerPage")) and cfg["charsPerPage"] > 0 else 1000
    tpp = cfg.get("tableCharsPerPage") if _is_int(cfg.get("tableCharsPerPage")) and cfg["tableCharsPerPage"] > 0 else 500
    raw = (body_chars or 0) / float(cpp) + (table_chars or 0) / float(tpp)
    return {"pages": int(math.ceil(raw)) if raw > 0 else 0,
            "raw": round(raw, 2), "charsPerPage": cpp, "tableCharsPerPage": tpp}


def judge_pages(pages, page_constraint):
    """V3：超上限 error、不足 60% warn；返回 issue 或 None。"""
    maxp = page_constraint.get("max") if isinstance(page_constraint, dict) else None
    if not _num(maxp) or maxp <= 0 or not _num(pages):
        return None
    if pages > maxp:
        return _err("A3.over", "估算 %s 页 > 页数上限 %s 页（须压缩或拆分）" % (pages, maxp))
    if pages < maxp * 0.6:
        return _warn("A3.short", "估算 %s 页 < 上限 %s 页的 60%%（篇幅偏少，可能失分）" % (pages, maxp))
    return None


# ---------------------------------------------------------------------------
# F5：暗标敏感词（A4，Q3 完整内置表）
# ---------------------------------------------------------------------------
def scan_sensitive(text, vocab=None, bid_mode="暗标"):
    """暗标命中项 → [{level,type,pattern,text,line,col,snippet}]；明标返回空数组。"""
    if bid_mode != "暗标" or not isinstance(text, str) or not text:
        return []
    vocab = vocab if isinstance(vocab, dict) else {}
    rules = list(SENSITIVE_BUILTIN)
    for name in vocab.get("enterprise_names") or []:
        if isinstance(name, str) and name.strip():
            rules.append(("企业名称", re.compile(re.escape(name))))
    for name in vocab.get("brands") or []:
        if isinstance(name, str) and name.strip():
            rules.append(("品牌/商标", re.compile(re.escape(name), re.I)))
    for addr in vocab.get("addresses") or []:
        if isinstance(addr, str) and addr.strip():
            rules.append(("地址", re.compile(re.escape(addr))))
    if vocab.get("personnelWriteMode", "post-only") != "with-name":
        for name in vocab.get("persons") or []:
            if isinstance(name, str) and len(name.strip()) >= 2:
                rules.append(("人员姓名", re.compile(re.escape(name.strip()))))
    hits, seen = [], set()
    for typ, rx in rules:
        for m in rx.finditer(text):
            if (typ, m.start()) in seen:
                continue
            seen.add((typ, m.start()))
            line, col, snippet = _locate(text, m.start(), m.end())
            hits.append({"level": "error", "type": typ, "pattern": rx.pattern, "text": m.group(0),
                         "line": line, "col": col, "snippet": snippet})
    return sorted(hits, key=lambda h: (h["line"], h["col"]))


# ---------------------------------------------------------------------------
# F6：术语 / 人员一致性（A5，warn）
# ---------------------------------------------------------------------------
def check_consistency(text, terminology, personnel, mode="明标"):
    """术语同义词混用 + 人员/岗位与素材清单一致性 → [{level, code, message}]。"""
    issues = []
    if not isinstance(text, str) or not text:
        return issues
    for canonical, synonyms in SYNONYM_GROUPS:
        found = [s for s in synonyms if s in text]
        if not found:
            continue
        if canonical in text:
            issues.append(_warn("A5.term", "术语混用：已用「%s」，同时出现 %s（应统一为「%s」）"
                                % (canonical, "/".join(found), canonical)))
        else:
            issues.append(_warn("A5.term-missing", "未使用术语表称谓「%s」，仅出现 %s"
                                % (canonical, "/".join(found))))
    staff = [p for p in (personnel or []) if isinstance(p, dict)]
    posts = [p.get("post") for p in staff if isinstance(p.get("post"), str) and p.get("post")]
    if mode != "暗标":
        for p in staff:
            name, post = p.get("name"), p.get("post")
            if isinstance(name, str) and name and isinstance(post, str) and post and name in text and post not in text:
                issues.append(_warn("A5.person", "人员「%s」在正文出现，但岗位「%s」未出现（与素材清单可能不一致）"
                                    % (name, post)))
    if posts:
        present = [p for p in KNOWN_POSTS if p in text]
        for post in present:
            # 被更长的岗位名覆盖时跳过（如“总监理工程师代表”内含“总监理工程师”）
            if any(post != other and post in other for other in present):
                continue
            if post not in posts:
                issues.append(_warn("A5.post", "正文出现素材清单未列的岗位「%s」" % post))
    return issues


# ---------------------------------------------------------------------------
# F7：占位 / 垃圾残留（A6，warn）
# ---------------------------------------------------------------------------
def scan_placeholders(text):
    """扫描 {{待填}} / {{模板占位}} / TODO / XXX / 纯空格段落 → 命中数组。"""
    if not isinstance(text, str) or not text:
        return []
    hits, spans = [], []

    def add(typ, start, end, raw):
        line, col, snippet = _locate(text, start, end)
        hits.append({"level": "warn", "code": "A6.%s" % typ, "type": typ,
                     "line": line, "col": col, "text": raw, "snippet": snippet})

    for typ, rx in PLACEHOLDER_PATTERNS:
        for m in rx.finditer(text):
            if any(a <= m.start() < b for a, b in spans):
                continue
            spans.append((m.start(), m.end()))
            add(typ, m.start(), m.end(), m.group(0))
    for m in BLANK_LINE_RE.finditer(text):
        add("空白段落", m.start(), m.end(), m.group(0))
    return sorted(hits, key=lambda h: (h["line"], h["col"]))


# ---------------------------------------------------------------------------
# F8：状态机
# ---------------------------------------------------------------------------
def validate_transition(from_state, to_state):
    """状态迁移合法性 → (ok, reason)。"""
    if from_state not in STATUSES:
        return False, "未知起始状态：%r" % (from_state,)
    if to_state not in STATUSES:
        return False, "未知目标状态：%r" % (to_state,)
    if (from_state, to_state) in STATUS_FLOW:
        return True, ""
    allowed = [t for f, t in STATUS_FLOW if f == from_state]
    return False, "非法迁移：%s → %s（允许：%s）" % (from_state, to_state,
                                                    "/".join(allowed) if allowed else "无（终态）")


def next_states(cur):
    """当前状态允许到达的状态列表（按迁移表顺序）。"""
    return [t for f, t in STATUS_FLOW if f == cur]


# ---------------------------------------------------------------------------
# F9：自述块解析 / 剥离
# ---------------------------------------------------------------------------
def parse_selfcheck_block(md):
    """解析 `M6-COVERAGE` / `M6-REVISE` 注释块 → (info, error)。info={block,data}。"""
    if not isinstance(md, str):
        return None, "正文必须是字符串"
    found = SELFCHECK_RE.findall(md)
    if not found:
        return None, "未找到自述块（M6-COVERAGE / M6-REVISE）"
    if len(found) > 1:
        return None, "存在多个自述块（%d 个），须只保留一个" % len(found)
    name, raw = found[0][0], found[0][1].strip()
    try:
        data = json.loads(raw)
    except ValueError as e:
        return None, "%s 块 JSON 解析失败：%s" % (name, e)
    if not isinstance(data, dict):
        return None, "%s 块必须是 JSON 对象" % name
    if name == "M6-COVERAGE":
        for k, typ in (("keyPoints", list), ("missingMaterials", list), ("notes", str)):
            if k not in data:
                return None, "M6-COVERAGE 缺字段 %s" % k
            if not isinstance(data[k], typ):
                return None, "M6-COVERAGE.%s 类型错误（应为 %s）" % (k, typ.__name__)
        for i, kp in enumerate(data["keyPoints"]):
            if not isinstance(kp, dict) or not kp.get("point") or "covered" not in kp:
                return None, "M6-COVERAGE.keyPoints[%d] 须含 point/covered" % i
    else:
        if not isinstance(data.get("changes"), list):
            return None, "M6-REVISE.changes 必须是数组"
        for i, ch in enumerate(data["changes"]):
            if not isinstance(ch, dict) or not ch.get("where"):
                return None, "M6-REVISE.changes[%d] 须含 where" % i
        if not isinstance(data.get("untouched"), str):
            return None, "M6-REVISE.untouched 必须是字符串"
    return {"block": name, "data": data}, ""


def strip_selfcheck_block(md):
    """剥离自述块（解析失败也不静默保留——由调用方根据 parse 结果判 FAILED）。"""
    if not isinstance(md, str):
        return ""
    return SELFCHECK_RE.sub("", md).rstrip() + "\n"


# ---------------------------------------------------------------------------
# F10：双通道差异（契约 §6.3 四类）
# ---------------------------------------------------------------------------
def _unwrap_selfcheck(sc):
    if isinstance(sc, dict) and isinstance(sc.get("data"), dict):
        return sc["data"]
    return sc if isinstance(sc, dict) else {}


def compare_dual(machine_doc, selfcheck_docs):
    """通道A 机器结论 vs agent 自述 → 差异数组（四类）。"""
    diffs = []
    machine_doc = machine_doc if isinstance(machine_doc, dict) else {}
    selfcheck_docs = selfcheck_docs if isinstance(selfcheck_docs, dict) else {}
    rows = ((machine_doc.get("coverage") or {}).get("rows") or [])

    def add(typ, chapter, item, detail):
        diffs.append({"type": typ, "chapter": chapter, "item": item, "detail": detail})

    agent_all = {}
    for ch_id, sc in selfcheck_docs.items():
        data = _unwrap_selfcheck(sc)
        kps = [k for k in (data.get("keyPoints") or []) if isinstance(k, dict)]
        all_covered = bool(kps) and all(bool(k.get("covered")) for k in kps)
        agent_all[ch_id] = all_covered
        touched = [r for r in rows if ch_id in (r.get("chapters") or [])]
        machine_bad = [r for r in touched if r.get("level") in ("error", "warn")]
        if machine_bad and all_covered:
            add("覆盖结论冲突", ch_id, ",".join(str(r["idx"]) for r in machine_bad),
                "通道A 判定未覆盖/弱覆盖，agent 自述全部覆盖（须人工裁决）")
        elif touched and not machine_bad and any(not bool(k.get("covered")) for k in kps):
            add("覆盖结论冲突", ch_id, "",
                "通道A 判定已覆盖，agent 自述存在未覆盖要点（须人工裁决）")

        mc = ((machine_doc.get("chapters") or {}).get(ch_id) or {})
        a_chars, b_chars = mc.get("chars"), data.get("wordCnt", data.get("chars"))
        if _num(a_chars) and _num(b_chars) and a_chars > 0:
            dev = abs(a_chars - b_chars) / float(a_chars)
            if dev > 0.2:
                add("篇幅偏差", ch_id, "", "通道A %d 字 vs 自述 %s 字（偏差 %.0f%%）"
                    % (a_chars, b_chars, dev * 100))

        notes = data.get("notes") or ""
        miss = data.get("missingMaterials") or []
        machine_findings = (mc.get("sensitive") or []) + (mc.get("placeholders") or [])
        if (str(notes).strip() or miss) and not machine_findings:
            add("仅通道B发现项", ch_id, "", "agent 标注：%s（通道A 无对应结论）"
                % (str(notes).strip() or "缺料 %s" % miss))
        for hit in machine_findings:
            raw = hit.get("text", "") if isinstance(hit, dict) else str(hit)
            if raw and raw not in str(notes):
                add("仅通道A发现项", ch_id, raw,
                    "通道A 命中（%s）但 agent 自述未提及"
                    % (hit.get("type", "残留") if isinstance(hit, dict) else "残留"))

    # 全局：通道A 判定某些评分项完全未被引用，但有章节自述“全部覆盖”→ 逐项交裁决
    missing_ids = [r["idx"] for r in rows if r.get("level") == "error"]
    if missing_ids and any(agent_all.values()):
        add("覆盖结论冲突", "", ",".join(str(i) for i in missing_ids),
            "通道A 判定这些评分项未覆盖，但有章节自述全部覆盖（须人工裁决）")
    return diffs
