# -*- coding: utf-8 -*-
"""
bidcraft · M9 失分补救指引 —— 任务生成引擎

把 M8 模拟评标（通道A 客观/报价失分 + 通道B 主观失分诊断）转成可执行的
『失分补救任务单』：区分能力问题（素材补齐：业绩/职称/荣誉/体系）与
写作/形式问题（内容补强：大纲章节；格式合规：暗标篇幅/空白页/图表位置；
报价策略：低于成本审查/报价区间），每个任务落到 M5 素材库操作与验证闭环。

依据（联网核查 2026-10-18）：
- 国际投标复盘（debrief）实践：把失分映射回文件具体章节，区分"写作问题 vs
  实质性能力问题"（Enable Consulting），反馈转化为企业画像/参考案例更新
  （BidPal.ai），逐项补救再投标（Tender Writing Consultants）。
- 国内：废标常见原因=资格材料不全/报价不一致/签字盖章/逾期递交 → 先做资格
  清单、逐项找证明、缺什么提前补（定西市公共资源交易中心 2026-01 提示）。
"""
import math

# kind → 补救任务类型与素材映射（通道A 客观失分）
RULE = {
    "perf": {
        "类型": "素材补齐", "动作": "补业绩", "素材": {"category": "业绩"},
        "step": "归档 {n} 份满足条件的业绩合同扫描件（金额≥{amount}万/合同签订时间{year}起/类型{type}，单份合同工程施工投资估算价或建安费达标；内容不体现的须附合同甲方盖章证明材料）→ 素材清单 items 增条 → 重跑 eval-run 验证得分",
        "per_note": "每份 +{per} 分，目标补 {n} 份可追至满分",
    },
    "staff_title": {
        "类型": "素材补齐", "动作": "补监理人员职称", "素材": {"category": "人员", "subtype": "监理人员职称证书"},
        "step": "附表7 增列 {n} 名市政工程相关专业中级以上职称监理人员（不含总监）→ 归档职称证书扫描件 → 素材清单 items 增条 → 重跑 eval-run 验证得分",
        "per_note": "每人 +{per} 分，目标补 {n} 人可追至满分",
    },
    "dir_title": {
        "类型": "素材补齐", "动作": "补总监职称", "素材": {"category": "人员", "subtype": "总监职称证书"},
        "step": "核实总监市政工程相关专业中级以上职称证书并归档扫描件（或调整总监人选匹配招标要求）→ 素材清单 items 增条 → 重跑 eval-run 验证得分",
        "per_note": "该项 +{per} 分",
    },
    "honor": {
        "类型": "素材补齐", "动作": "补荣誉", "素材": {"category": "荣誉", "subtype": "先进示范优秀监理企业表彰证书"},
        "step": "归档 {n} 个 2021-01-01（含）以来地级市（含）以上人民政府建设行政主管部门或行业主管协会（民政登记可查）颁发的先进/示范/优秀监理企业表彰证书（认定以证书落款日期）→ 素材清单 items 增条 → 重跑 eval-run 验证得分",
        "per_note": "首个 +{first} 分、后续每个 +{next} 分，目标补 {n} 个可追至满分",
    },
    "iso": {
        "类型": "证据核验", "动作": "核验体系证书有效期", "素材": {"category": "体系认证", "subtype": "ISO三体系认证证书"},
        "step": "逐张核对质量/环境/职业健康安全管理体系认证证书扫描件在有效期内的落款与有效期区间，确认证书随投标文件附扫描件 → 过期即安排续证",
        "per_note": "有效期/扫描件核验（各 1 分，满分 {max} 分）",
    },
    "quote": {
        "类型": "报价策略", "动作": "报价风险处置", "素材": None,
        "step": "按风险清单逐项处置（见风险明细）；报价高于最高限价→废标必须改价；报价明显低于限价50%→准备成本构成说明与证明材料；基准价=有效投标报价算术平均值（对手未知），对照保住各档得分所需基准价区间校准报价",
        "per_note": None,
    },
    "rule": {
        "类型": "格式合规", "动作": "暗标/篇幅/格式合规处置", "素材": None,
        "step": "按暗标约束逐项人工确认：每子评分项篇幅≤10页（含封面目录底页空页）→超限压缩；不设空白页；不得泄露投标人信息（逐页排查，泄露即该评分点0分）；文字不得插入图表（附图附表依次附文末）；格式不符合扣0.2分",
        "per_note": None,
    },
}

PRIORITY_GAP = [(4.0, "高"), (2.0, "中")]  # gap ≥4 高；≥2 中；其余低


def _priority_for_gap(gap):
    if gap is None:
        return "中"
    for th, p in PRIORITY_GAP:
        if gap >= th:
            return p
    return "低"


def _params(item, standard):
    """评分项 params 抽取：优先 issue 自带，否则按 kind 从 standard.items 匹配（真实产物 issues 无 params）。"""
    p = dict(item.get("params") or {})
    if not p:
        for s in (standard.get("items") or []):
            if s.get("kind") == item.get("kind"):
                p = dict(s.get("params") or {})
                break
    return {
        "per": p.get("per"), "max": p.get("max"),
        "amount": p.get("require_type"), "year": (p.get("year_start") or "2021-01-01")[:4] if p.get("year_start") else "2021",
        "type": "市政公用工程" if item.get("kind") == "perf" else "",
        "first": p.get("first"), "next": p.get("next"),
    }


def gen_tasks(eval_doc, subjective_doc=None):
    """M8 产物 → 失分补救任务单（tasks 列表 + summary）。"""
    tasks, rid = [], 0
    summary = eval_doc.get("summary") or {}
    standard = eval_doc.get("standard") or {}

    # ---- 通道A 客观失分（能力问题：素材补齐） ----
    issues = summary.get("issues") or []
    for it in issues:
        kind, gap = it.get("kind"), it.get("gap")
        if not kind or kind not in RULE:
            continue
        rule = RULE[kind]
        rid += 1
        params = _params(it, standard)
        n = None
        if kind in ("perf", "staff_title") and gap is not None and params["per"]:
            n = int(math.ceil(gap / params["per"]))
        if kind == "honor" and gap is not None and params["next"]:
            # 首个 X 分 + 后续每 Y 分：缺口优先后续
            n = int(math.ceil(gap / params["next"])) if gap > 0 else 0
        steps = []
        if kind == "quote":
            for r in (eval_doc.get("quote") or {}).get("risks", []):
                steps.append("⚠️ %s" % r)
            steps.append(rule["step"])
            # 附加保住各档得分的基准价区间
            for b in (eval_doc.get("quote") or {}).get("bands", []):
                steps.append("- 保住 %.1f 分：基准价 ∈ [%.1f, %.1f] 元" % (b["target"], b["range"][0], b["range"][1]))
        else:
            steps.append(rule["step"].format(
                n=n or "", amount=params["amount"] if params["amount"] is not None else "X",
                year=params["year"], type=params["type"], per=params["per"], first=params["first"], next=params["next"],
                max=params["max"] if params["max"] is not None else "X"))
        per_note = None
        if rule["per_note"] and n is not None and (params["per"] or params["first"]):
            per_note = rule["per_note"].format(n=n, per=params["per"], first=params["first"], next=params["next"])
        elif rule["per_note"] and kind in ("dir_title", "iso") and params["per"]:
            per_note = rule["per_note"].format(per=params["per"], max=params["max"])
        tasks.append({
            "id": "R%02d" % rid,
            "类型": rule["类型"],
            "动作": rule["动作"],
            "标题": "%s（%s 分）" % (it.get("item", "")[:60], ("%.1f" % gap) if gap is not None else "—"),
            "来源": "通道A-客观",
            "评分项": it.get("item", ""),
            "当前状态": it.get("advice", ""),
            "目标状态": ("补齐后可追至满分，预期加分 %.1f 分" % gap) if gap is not None else "核验通过",
            "动作步骤": steps,
            "涉及素材": rule.get("素材"),
            "优先级": "高" if kind == "quote" else _priority_for_gap(gap),
            "预期加分": gap,
            "验证方式": "重跑 eval-run --project … 复核该评分项得分；素材按 M5 归档流程入素材清单",
        })

    # ---- 通道A 未评项中的暗标 rule（格式合规，否决性） ----
    for p in summary.get("unrated", []):
        if p.get("kind") == "rule":
            rid += 1
            tasks.append({
                "id": "R%02d" % rid, "类型": "格式合规", "动作": "暗标/篇幅/格式合规处置",
                "标题": "暗标约束逐项人工确认（否决性：违规该评分点0分/不予评审）",
                "来源": "通道A-规则项", "评分项": p.get("item", ""),
                "当前状态": p.get("note", ""),
                "目标状态": "全部暗标约束人工确认通过（篇幅/空白页/泄露/图表位置/格式）",
                "动作步骤": [RULE["rule"]["step"]], "涉及素材": None,
                "优先级": "高", "预期加分": None,
                "验证方式": "M7 标书检查（check-rule/check-parse）复核 + 人工逐页确认",
            })

    # ---- 通道B 主观失分诊断（写作/形式问题：内容补强 + 合规确认） ----
    if subjective_doc:
        for d in (subjective_doc.get("失分诊断") or []):
            rid += 1
            loss = d.get("失分")
            prio = d.get("优先级", "中")
            tasks.append({
                "id": "R%02d" % rid, "类型": "内容补强" if loss else "合规确认",
                "动作": "主观分补强" if loss else "主观分合规确认",
                "标题": d.get("子项", ""),
                "来源": "通道B-主观", "评分项": d.get("子项", ""),
                "当前状态": d.get("说明", ""),
                "目标状态": ("补强后该子项可追至满分（预期加分 %.1f 分）" % loss) if loss else "人工确认通过",
                "动作步骤": [d.get("说明", "")],
                "涉及素材": None,
                "优先级": "高" if prio == "高" else ("中" if prio == "中" else "低"),
                "预期加分": loss,
                "验证方式": "重跑 eval-report 复核该子项预估分区间；内容按 M6/监理大纲流程修订",
            })

    # ---- summary ----
    total_gain = sum(t["预期加分"] for t in tasks if t.get("预期加分") is not None)
    return {
        "project": eval_doc.get("project", ""),
        "生成依据": "M8 模拟评标_<项目>.json（通道A）+ 主观评审_<项目>.json（通道B）失分诊断",
        "tasks": tasks,
        "summary": {
            "任务总数": len(tasks),
            "可追分合计": total_gain,
            "客观分当前": summary.get("objective_score"),
            "客观分满分": summary.get("objective_max"),
            "主观分": (lambda t: {"min": t.get("min"), "max": t.get("max"), "满分": t.get("满分")})(
                (subjective_doc or {}).get("主观合计") or {}) if subjective_doc else None,
        },
        "分工": "能力问题（素材补齐）→ 走 M5 素材归档流程；写作/形式问题（内容补强/格式合规/报价策略）→ 按任务单修订后重评闭环",
    }


def to_md(doc):
    lines = ["# 失分补救任务单 · %s" % doc.get("project", ""), ""]
    s = doc.get("summary", {})
    lines.append("任务总数 **%s** ｜ 可追分合计 **%.1f 分**（客观 %.1f/%.1f%s）" % (
        s.get("任务总数"), s.get("可追分合计") or 0,
        s.get("客观分当前") or 0, s.get("客观分满分") or 0,
        ("；主观 %s" % ("[%s-%s]/%s" % (s["主观分"]["min"], s["主观分"]["max"], s["主观分"]["满分"])) if s.get("主观分") else "；主观未评")))
    lines.append("")
    lines.append("> %s" % doc.get("分工", ""))
    lines.append("")
    lines.append("## 任务清单（按优先级）")
    lines.append("| ID | 类型 | 动作 | 标题 | 优先级 | 预期加分 | 来源 |")
    lines.append("|---|---|---|---|---|---|---|")
    order = {"高": 0, "中": 1, "低": 2}
    for t in sorted(doc["tasks"], key=lambda x: (order.get(x["优先级"], 9), x["id"])):
        lines.append("| %s | %s | %s | %s | %s | %s | %s |" % (
            t["id"], t["类型"], t["动作"], t["标题"].replace("|", "／")[:48],
            t["优先级"], ("%.1f" % t["预期加分"]) if t["预期加分"] is not None else "—", t["来源"]))
    lines.append("")
    for t in sorted(doc["tasks"], key=lambda x: (order.get(x["优先级"], 9), x["id"])):
        lines.append("### %s %s（%s）" % (t["id"], t["动作"], t["优先级"]))
        lines.append("- 评分项：%s" % t["评分项"])
        lines.append("- 当前状态：%s" % t["当前状态"])
        lines.append("- 目标状态：%s" % t["目标状态"])
        lines.append("- 动作步骤：")
        for st in t["动作步骤"]:
            lines.append("  1. %s" % st)
        if t.get("涉及素材"):
            lines.append("- 涉及素材：%s" % "/".join(str(v) for v in t["涉及素材"].values()))
        if t["预期加分"] is not None:
            lines.append("- 预期加分：%.1f" % t["预期加分"])
        lines.append("- 验证方式：%s" % t["验证方式"])
        lines.append("")
    lines.append("> 人工确认闸门：任务单为投标前自检参考；素材补齐须经 M5 素材归档流程（propose/apply），最终以评标委员会评审为准。")
    return "\n".join(lines)
