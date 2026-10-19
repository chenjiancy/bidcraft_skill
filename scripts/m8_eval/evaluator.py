# -*- coding: utf-8 -*-
"""
bidcraft · M8 AI模拟评标 —— 通道A 客观分计算器 + 报价分反推（确定性规则）

设计约定：
  - 客观分证据 = M4 素材清单（items 按 category/subtype 定位）+ 评分项规则参数
  - 确定性可判项做硬结论；数量/有效期/时间等语义脆弱项标「参考，须人工核对」
  - 报价金额铁律：由用户 --quote 提供（不自动猜测）；报价分按「反推基准价区间」
    输出——投标人视角最实用（无需对手报价数据）
"""
import re

from _shared import core

_AMOUNT_WAN = re.compile(r"([\d,]+(?:\.\d+)?)\s*万元")

# 素材清单条目定位（category / subtype 关键词）
_CAT_ISO = "体系认证"
_CAT_PERF = "业绩"
_CAT_HONOR = "荣誉"
_SUB_DIR_TITLE = ("总监职称",)
_SUB_STAFF_TITLE = ("监理人员职称",)


def _load_json(path, label):
    doc = core.read_json(str(path), None)
    if not doc:
        raise core.LibraryError("%s JSON 无法读取：%s" % (label, path))
    return doc


def _items_of(mat, category=None, sub_kw=()):
    """素材清单 items 中按 category 与 subtype 关键词过滤。"""
    out = []
    for it in (mat.get("items") or []):
        cat = it.get("category") or ""
        sub = it.get("subtype") or ""
        if category is not None and cat != category:
            continue
        if sub_kw and not any(k in sub for k in sub_kw):
            continue
        out.append(it)
    return out


def _normalize_mat(mat):
    """素材清单结构归一：fill-tpl 版（personnel/iso_certificates/honors/performance）→
    旧 items[].category 结构；旧结构（items 含 category）原样返回（向后兼容）。
    M5 fill-tpl（2026-10-19）素材清单已改用人员/资质/体系/荣誉/业绩分键结构，
    M8 evaluator 数据源须与其对齐。"""
    items = mat.get("items") or []
    if items and any(it.get("category") for it in items):
        return mat
    out = []
    for it in mat.get("personnel") or []:
        sub = "总监职称" if (it.get("role") or "") == "项目总监" else "监理人员职称"
        for p in (it.get("职称") or []):
            out.append({"category": "人员", "subtype": sub,
                        "purpose": (it.get("name") or "") + " 职称", "path": p})
    for it in mat.get("iso_certificates") or []:
        out.append({"category": "体系认证", "subtype": "",
                    "purpose": it.get("name") or "", "path": it.get("path") or ""})
    for it in mat.get("performance") or []:
        if it.get("paths"):
            out.append({"category": "业绩", "subtype": "",
                        "purpose": it.get("name") or "", "path": it.get("paths")[0]})
    for it in mat.get("honors") or []:
        out.append({"category": "荣誉", "subtype": "",
                    "purpose": it.get("name") or "", "path": it.get("path") or ""})
    return {"items": out}


def _iso_sys_count(purpose):
    """从素材条目 purpose 命中的 ISO 体系词数（质量/环境/职业健康，上限3）。"""
    n = 0
    for kw in ("质量", "环境", "职业健康"):
        if kw in purpose:
            n += 1
    return n or 3


# --------------------------------------------------------------------------
# 客观分计算
# --------------------------------------------------------------------------
def calc_objective(standard, mat):
    """按评分项逐条计算客观分 → [{score, max, detail, level}]。"""
    mat = _normalize_mat(mat)
    results = []
    for p in standard["items"]:
        kind = p["kind"]
        if kind not in ("iso", "perf", "dir_title", "staff_title", "honor"):
            continue
        r = _calc_one(kind, p, mat)
        results.append(r)
    return results


def _calc_one(kind, p, mat):
    item, params = p["item"], p["params"]
    mx = params.get("max") or p["weight"] or 0.0

    if kind == "iso":
        its = _items_of(mat, category=_CAT_ISO)
        sys_total = sum(_iso_sys_count(it.get("purpose") or "") for it in its)
        score = min(sys_total, mx)
        return {
            "kind": kind, "item": item, "max": mx, "score": score,
            "evidence": "素材清单体系认证条目 %d 条（命中体系词合计 %d）" % (len(its), sys_total),
            "level": "参考" if sys_total < mx else "已计算",
            "note": p["note"] + "；命中体系词：%d/%d" % (sys_total, mx),
        }

    if kind == "perf":
        its = _items_of(mat, category=_CAT_PERF)
        per, cap = params.get("per") or 4.0, mx
        score = min(len(its) * per, cap)
        return {
            "kind": kind, "item": item, "max": mx, "score": score,
            "evidence": "素材清单业绩条目 %d 条 × 每条 %s 分（上限 %s）" % (len(its), per, cap),
            "level": "参考",
            "note": p["note"] + "；条目数=%d（金额≥%s万/年限%s起须逐份人工核对）"
                    % (len(its), params.get("require_type") or "?",
                       params.get("year_start") or "?"),
        }

    if kind == "dir_title":
        its = _items_of(mat, category="人员", sub_kw=_SUB_DIR_TITLE)
        score = mx if its else 0.0
        return {
            "kind": kind, "item": item, "max": mx, "score": score,
            "evidence": "素材清单总监职称证书条目 %d 条" % len(its),
            "level": "已计算" if its else "缺失",
            "note": p["note"] + "；" + ("已归档" if its else "素材库未见总监职称证书（失分1分）"),
        }

    if kind == "staff_title":
        its = _items_of(mat, category="人员", sub_kw=_SUB_STAFF_TITLE)
        per, cap = params.get("per") or 1.0, mx
        score = min(len(its) * per, cap)
        return {
            "kind": kind, "item": item, "max": mx, "score": score,
            "evidence": "素材清单监理人员职称条目 %d 条 × 每人 %s 分（上限 %s）" % (len(its), per, cap),
            "level": "参考",
            "note": p["note"] + "；条目=%d（附表7实际人数须人工核对，可追至上限 %s 分）" % (len(its), cap),
        }

    if kind == "honor":
        its = _items_of(mat, category=_CAT_HONOR)
        first, nxt, cap = params.get("first") or 3.0, params.get("next") or 2.0, mx
        n = len(its)
        score = 0.0
        if n >= 1:
            score = first + nxt * (n - 1)
        score = min(score, cap)
        return {
            "kind": kind, "item": item, "max": mx, "score": score,
            "evidence": "素材清单荣誉条目 %d 个（首个 %s 分 + 后续每 %s 分，上限 %s）" % (n, first, nxt, cap),
            "level": "参考" if n else "缺失",
            "note": p["note"] + "；条目=%d（落款日期/颁发单位须人工核对）" % n,
        }

    return None  # pragma: no cover


# --------------------------------------------------------------------------
# 报价分（反推基准价区间）
# --------------------------------------------------------------------------
def parse_cap(pricing_mod):
    """从 pricing 模块提取最高限价（元）；找不到返回 None。"""
    fields = (pricing_mod or {}).get("fields") or {}
    for key in ("报价上限（废标线）", "报价上限", "最高限价"):
        f = fields.get(key)
        if f:
            m = _AMOUNT_WAN.search(f.get("value") or "")
            if m:
                return float(m.group(1).replace(",", "")) * 10000.0
    return None


def quote_analysis(quote, cap, params):
    """
    报价分反推（投标人视角，无需对手报价）：
      score(B) = max(0, max - 偏高%(B<X)*hi_punish - 偏低%(B>X)*lo_punish)
      返回：采样曲线（B∈[0.6·cap, cap]）+ 保住 D 分所需基准价区间 + 风险提示
    """
    if not quote or quote <= 0:
        return {"provided": False,
                "note": "未提供报价（铁律：报价金额由用户提供，--quote 传入），报价 30 分未评"}
    mx = params.get("max") or 30.0
    hi = params.get("hi_punish") or 0.2
    lo = params.get("lo_punish") or 0.1

    if cap:
        b_max = cap                       # 高于限价无有效投标，曲线止于限价
        b_min = min(cap * 0.6, quote * 0.5)   # 至少覆盖报价半价以下，保证满分点(B=X)在曲线内
    else:
        b_min, b_max = quote * 0.5, quote * 2.0

    def score_at(b):
        if b <= 0:
            return 0.0
        dev = (quote - b) / b * 100.0
        if dev > 0:      # 报价高于基准价 → 偏高
            return max(0.0, mx - dev * hi)
        return max(0.0, mx - (-dev) * lo)   # 偏低

    curve = []
    step = max(1, int((b_max - b_min) / 300))   # 300 段采样，报价-基准价曲线精度 ~0.3%
    b = b_min
    while b <= b_max + 1e-9:
        curve.append({"base": round(b, 2), "score": round(score_at(b), 2)})
        b += step
    if not curve or curve[-1]["base"] < b_max:
        curve.append({"base": round(b_max, 2), "score": round(score_at(b_max), 2)})

    # 保住 D 分所需基准价区间（B ≥ X 偏低侧扣 lo，B < X 偏高侧扣 hi；裁剪到最高限价内）
    bands = []
    for d in (mx * 0.9, mx * 0.8, mx * 0.7):  # 90%/80%/70% 三档
        d = round(d, 1)
        lo_hi = (mx - d) / lo / 100.0      # (B-X)/B ≤ 该值 → B ≤ X/(1-值)
        hi_lo = (mx - d) / hi / 100.0      # (X-B)/B ≤ 该值 → B ≥ X/(1+值)
        if lo_hi < 1.0 and hi_lo >= 0:
            b_low = quote / (1.0 + hi_lo)
            b_high = quote / (1.0 - lo_hi)
            if cap:
                b_high = min(b_high, cap)   # 高于限价的基准价无实际意义（限价内才有效投标）
            if b_low <= b_high:
                bands.append({"target": d, "range": [round(b_low, 2), round(b_high, 2)]})

    risks = []
    if cap and quote > cap:
        risks.append("报价 %s 元高于最高限价 %s 元 → 无效投标（废标）" % (int(quote), int(cap)))
    if cap and quote < cap * 0.5:
        risks.append("报价明显低于限价 50%%，可能触发『低于成本审查』：须提供成本构成说明与证明材料")
    risks.append("报价与基准价关系未知：基准价=有效投标报价算术平均值，对手报价未知，本区间为反推参考")

    return {
        "provided": True,
        "quote": quote,
        "cap": cap,
        "max": mx,
        "hi_punish": hi,
        "lo_punish": lo,
        "curve": curve,
        "bands": bands,
        "risks": risks,
        "note": "基准价=%s；得分=满分 - 偏高1%%扣%s分 - 偏低1%%扣%s分，扣完为止"
                % ((params.get("base_desc") or "按招标文件"), hi, lo),
    }


# --------------------------------------------------------------------------
# 汇总
# --------------------------------------------------------------------------
def build_summary(standard, objective, quote, quote_analysis):
    """失分诊断 + 汇总。"""
    obj_score = sum(r["score"] for r in objective)
    issues = []
    for r in objective:
        if r["score"] < r["max"] - 1e-9:
            issues.append({
                "kind": r["kind"], "item": r["item"], "score": r["score"], "max": r["max"],
                "gap": r["max"] - r["score"],
                "advice": "补齐/核对证据后最多可加 %.1f 分（%s）" % (r["max"] - r["score"], r["note"]),
            })
    if quote and quote_analysis.get("provided"):
        qmax = quote_analysis["max"]
        issues.append({
            "kind": "quote", "item": "报价分（反推）",
            "score": None, "max": qmax, "gap": None,
            "advice": "报价 %s 元：保住 %.1f 分需基准价 ∈ %s；详见报价分析"
                      % (int(quote_analysis["quote"]),
                         qmax * 0.8,
                         next((b["range"] for b in quote_analysis["bands"] if abs(b["target"] - qmax * 0.8) < 0.1), "?"))
        })
    unrated = [p for p in standard["items"]
               if p["kind"] == "outline" or p["kind"] == "unknown"]
    return {
        "objective_score": round(obj_score, 2),
        "objective_max": standard["objective_total"],
        "quote_total": standard["quote_total"],
        "subjective_total": standard["subjective_total"],
        "unrated": [{"kind": p["kind"], "item": p["item"], "max": p["weight"], "note": p["note"]}
                    for p in unrated],
        "issues": sorted(issues, key=lambda x: -(x.get("gap") or 99)),
        "disclaimer": "本结果为投标前自检参考，非专家评审结论；客观分证据以素材清单为据，数量/有效期/时间须人工核对；主观分待 M6 交付后精评；最终以评标委员会评审为准",
    }
