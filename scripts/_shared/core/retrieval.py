# -*- coding: utf-8 -*-
"""⑤ core 拆包 · 混合检索 + 重排（纯标准库，无第三方依赖）。

背景：core.query 是 in 子串匹配，素材量级上来后召回率会崩——搜「先进监理
企业」漏掉「优秀监理企业」，搜「营业执照」漏掉「营业执照_副本_长期」。

对标企业级 RAG「关键词 + 向量 + 重排」的轻量落地：
  1. 召回（混合）：
     - 关键词层：精确子串命中（rel_path/keywords/subtype/original_filename/note）；
     - 向量层：字符 n-gram 余弦相似度——中文无分词器场景的标准轻量做法，
       2-gram 对「先进监理企业」vs「优秀监理企业」仍有公共片段重合。
  2. 重排：字段权重 rel_path(2.0) > keywords(1.5) > subtype/original_filename(1.0)
     > note(0.5)；精确命中记全分，模糊命中按相似度打折（0.65）；总分降序取 top_k。
  3. 过滤：category/subtype/owner/日期 与 core.query 语义一致，先过滤后打分。

素材规模数百条时逐行打分成本可忽略；CI 双平台（无 numpy/sentence-transformers）
直接可跑。
"""

import math
import re
from collections import Counter

from .ledger import load_ledger

__all__ = ["ngrams", "ngram_cos", "query_hybrid"]

# 字段权重（重排）：命中位置越关键权重越高
FIELD_WEIGHTS = [
    ("rel_path", 2.0),
    ("keywords", 1.5),
    ("subtype", 1.0),
    ("original_filename", 1.0),
    ("note", 0.5),
]
MIN_SIM = 0.22         # n-gram 相似度阈值（低于视为无关）
FUZZY_DISCOUNT = 0.65  # 模糊命中按相似度打折（精确命中记全分）


# --------------------------------------------------------------------------
# 字符 n-gram 相似度（向量层，纯标准库）
# --------------------------------------------------------------------------
def _norm(s):
    """检索归一：去空白/小写。"""
    return re.sub(r"\s+", "", str(s)).lower()


def ngrams(s, n=2):
    """连续 n 字符（bigram 默认）计数。"""
    s = _norm(s)
    if not s:
        return Counter()
    if len(s) < n:
        return Counter([s])
    return Counter(s[i:i + n] for i in range(len(s) - n + 1))


def ngram_cos(a, b):
    """两串字符 n-gram 余弦相似度（0~1）。"""
    ca, cb = ngrams(a), ngrams(b)
    if not ca or not cb:
        return 0.0
    inter = sum((ca & cb).values())
    if not inter:
        return 0.0
    return inter / math.sqrt(sum(ca.values()) * sum(cb.values()))


# --------------------------------------------------------------------------
# 混合检索 + 重排
# --------------------------------------------------------------------------
def _term_score(q, row):
    """单关键词 × 单行：逐字段 精确命中(全分) + n-gram 模糊(打折)，返回总分。"""
    total = 0.0
    for name, weight in FIELD_WEIGHTS:
        text = str(row.get(name) or "").strip()
        if not text:
            continue
        if q in text:
            total += weight * 1.0
            continue
        sim = ngram_cos(q, text)
        if sim >= MIN_SIM:
            total += weight * sim * FUZZY_DISCOUNT
    return total


def query_hybrid(ent, category=None, subtype=None, keyword=None,
                 expires_before=None, expires_after=None, owner=None,
                 top_k=20):
    """混合检索：先按 core.query 语义过滤，再 n-gram 打分重排。

    keyword 可为 str 或 list[str]（多关键词取和）。返回 [{"row": 台账行,
    "score": 总分}]，按 score 降序截断 top_k；无 keyword 时等价 core.query
    （不过滤关键词、不排序）。
    """
    import re as _re
    rows = load_ledger(ent)
    # 与 core.query 一致的过滤语义（先过滤后打分）
    out = []
    for r in rows:
        if category and r.get("category") != category:
            continue
        if subtype and r.get("subtype") != subtype:
            continue
        if owner and owner not in (r.get("owner") or ""):
            continue
        d = r.get("dates", "")
        first = (d.split("、")[0] if d else "") or ""
        dated = bool(_re.match(r"^\d{8}$", first))
        if expires_before or expires_after:
            if not dated:
                continue
        if expires_before and dated and first >= expires_before:
            continue
        if expires_after and dated and first < expires_after:
            continue
        out.append(r)

    if not keyword:
        return [{"row": r, "score": 0.0} for r in out]

    terms = keyword if isinstance(keyword, (list, tuple)) else [keyword]
    terms = [str(t).strip() for t in terms if str(t).strip()]
    if not terms:
        return [{"row": r, "score": 0.0} for r in out]

    scored = []
    for r in out:
        s = sum(_term_score(q, r) for q in terms)
        if s > 0:
            scored.append({"row": r, "score": round(s, 4)})
    scored.sort(key=lambda x: (-x["score"], x["row"].get("dates", "")))
    return scored[: top_k]
