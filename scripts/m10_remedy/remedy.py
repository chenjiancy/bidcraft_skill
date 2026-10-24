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


def gen_check_tasks(check_doc):
    """M7 机器检查 json（含技术标检查 kind=tech）→ 检查整改任务（T17：与失分补救并列来源）。

    确定性映射：检查项 ok=False 且 issues 非空 → 一条「格式合规/标书检查整改」任务，
    动作步骤=修复 issues 逐条，验证方式=重跑 check-rule + check-report 人工确认闸门。
    不臆造：仅把机器已检出的问题转成任务，不做语义判断。
    """
    tasks = []
    is_tech = (check_doc or {}).get("kind") == "tech"
    for c in (check_doc or {}).get("检查") or []:
        if c.get("ok"):
            continue
        iss = c.get("issues") or []
        if not iss:
            continue
        name = c.get("name") or c.get("id") or "?"
        act = "技术标检查整改" if is_tech else "标书检查整改"
        src = "M7-%s" % (check_doc.get("tag") or "机器检查")
        tasks.append({
            "id": "C%02d" % len(tasks),
            "类型": "格式合规",
            "动作": act,
            "标题": "%s（%d 处问题）" % (name, len(iss)),
            "来源": src,
            "评分项": name,
            "当前状态": iss[0] + ((" 等 %d 条" % len(iss)) if len(iss) > 1 else ""),
            "目标状态": "整改后重跑 check-rule --kind tech 复核通过（check-report 人工确认闸门）" if is_tech
                        else "整改后重跑 check-rule 复核通过（check-report 人工确认闸门）",
            "动作步骤": ["修复：%s" % x for x in iss[:6]],
            "涉及素材": None,
            "优先级": "高",
            "预期加分": None,
            "验证方式": ("重跑 check-rule --project <项目> --out 技术标/产出/技术标_<项目>.docx --kind tech"
                          "；check-report 人工确认闸门") if is_tech
                        else "重跑 check-rule --project <项目>；check-report 人工确认闸门",
            "检查快照": {"id": c.get("id") or "", "name": name, "issues": iss},   # T18：remedy-recheck 复核基准
        })
    return tasks


def mark_done(doc, task_id, note=""):
    """任务单勾选完成（T18）：按 id 定位任务 → 标 完成状态/完成时间/完成备注；id 不存在报错不静默。"""
    for t in doc.get("tasks") or []:
        if t.get("id") == task_id:
            import datetime as _dt
            t["完成状态"] = "已完成"
            t["完成时间"] = _dt.datetime.now().strftime("%Y-%m-%d %H:%M")
            t["完成备注"] = (note or "").strip() or "人工确认完成"
            return {"task": t, "found": True}
    return {"found": False}


def recheck_tasks(doc, check_new=None, eval_new=None):
    """补救后重检（T18）：对任务单中『已完成』任务自动复核——
    - M7 整改任务（来源 M7-*）：按 检查快照.id/name 匹配新机器检查 → 该项 ok=True 且原问题全部消失 = 通过；
      ok=False → 未通过（仍存在/新增 issues 分别列出）。
    - 失分补救任务（通道A-客观/通道B-主观/通道A-规则项）：重跑 eval-run 后按 kind 对比 gap——
      新 gap < 原预期加分 → 已补回；否则未见改善；规则项按暗标检查项复核。
    - 新问题：新机器检查中 ok=False 且不在原任务单 → 生成新整改任务并入。
    返回 {结果列表, 新问题任务, 汇总, 结论}；纯逻辑无 I/O（写回由 CLI 完成）。
    """
    results, new_tasks = [], []
    now = __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M")
    done = [t for t in (doc.get("tasks") or []) if t.get("完成状态") == "已完成"]

    checks_new = {c.get("id"): c for c in ((check_new or {}).get("检查") or [])}
    checks_new_by_name = {c.get("name"): c for c in ((check_new or {}).get("检查") or [])}

    for t in done:
        src = t.get("来源", "")
        if src.startswith("M7-"):
            snap = t.get("检查快照") or {}
            cid = snap.get("id") or ""
            cname = snap.get("name") or t.get("评分项") or ""
            c = checks_new.get(cid) or checks_new_by_name.get(cname)
            if c is None:
                results.append({"id": t["id"], "标题": t.get("标题", ""), "验证": "无法复核",
                                "证据": "新机器检查中未找到检查项「%s」" % (cname or cid)})
                continue
            old_iss = snap.get("issues") or []
            new_iss = c.get("issues") or []
            if c.get("ok"):
                results.append({"id": t["id"], "标题": t.get("标题", ""), "验证": "通过",
                                "证据": "检查项「%s」已通过，原 %d 处问题全部消除" % (c.get("name"), len(old_iss))})
            else:
                still = [x for x in old_iss if x in new_iss]
                added = [x for x in new_iss if x not in old_iss]
                parts = []
                if still:
                    parts.append("仍存在 %d 处：%s" % (len(still), still[0]))
                if added:
                    parts.append("新增 %d 处：%s" % (len(added), added[0]))
                results.append({"id": t["id"], "标题": t.get("标题", ""), "验证": "未通过",
                                "证据": "检查项「%s」未通过；%s" % (c.get("name"), "；".join(parts) or "问题未消除")})
        else:
            # 失分补救任务：按 kind 对比 新 eval 产物 gap（确定性对比，语义不判）
            kind = t.get("评分项", "")
            old_gap = t.get("预期加分")
            if eval_new is not None:
                gaps = [it.get("gap") for it in ((eval_new.get("summary") or {}).get("issues") or [])
                        if it.get("item") == kind and it.get("gap") is not None]
                new_gap = min(gaps) if gaps else None
                if old_gap is not None and new_gap is not None:
                    back = old_gap - new_gap
                    if back > 0.05:
                        results.append({"id": t["id"], "标题": t.get("标题", ""), "验证": "通过",
                                        "证据": "该评分项失分已由 %.1f 降至 %.1f（补回 %.1f 分）" % (old_gap, new_gap, back)})
                    else:
                        results.append({"id": t["id"], "标题": t.get("标题", ""), "验证": "未通过",
                                        "证据": "该评分项失分仍为 %.1f（未见改善）" % (new_gap if new_gap is not None else old_gap)})
                else:
                    results.append({"id": t["id"], "标题": t.get("标题", ""), "验证": "需人工复核",
                                    "证据": "重跑 eval-run 后该评分项 gap 无法确定性对比，请人工核对 eval-report"})
            else:
                results.append({"id": t["id"], "标题": t.get("标题", ""), "验证": "需人工复核",
                                "证据": "重检未重跑 eval-run（产物缺失），请人工核对 eval-report"})

    # 新问题自动并入（检查项 ok=False 且不在原任务单）
    known = {t.get("评分项") for t in (doc.get("tasks") or [])} | {t.get("标题", "") for t in (doc.get("tasks") or [])}
    fresh_fails = [c for c in ((check_new or {}).get("检查") or [])
                   if not c.get("ok") and (c.get("issues") or [])
                   and c.get("name") not in known]
    if fresh_fails:
        new_tasks = _gen_from_checks(fresh_fails, check_new)

    passed = sum(1 for r in results if r["验证"] == "通过")
    summary = {"已勾选任务": len(done), "验证通过": passed,
               "未通过": sum(1 for r in results if r["验证"] == "未通过"),
               "需人工复核": sum(1 for r in results if r["验证"] in ("需人工复核", "无法复核")),
               "新增问题": len(new_tasks)}
    return {"results": results, "new_tasks": new_tasks, "summary": summary,
            "重检时间": now, "结论": ("补救后重检：%d/%d 已勾选任务验证通过，新增 %d 条问题任务；未通过项见明细，须人工整改后再次勾选重检"
                                     % (passed, len(done), len(new_tasks)))}


def _gen_from_checks(fresh, check_doc):
    """新问题检查项 → 整改任务（与 gen_check_tasks 同构，仅限传入的 fresh 子集）。"""
    tasks, rid = [], 0
    is_tech = (check_doc or {}).get("kind") == "tech"
    for c in fresh:
        iss = c.get("issues") or []
        if not iss:
            continue
        name = c.get("name") or c.get("id") or "?"
        tasks.append({
            "id": "C%02d" % len(tasks), "类型": "格式合规",
            "动作": "技术标检查整改" if is_tech else "标书检查整改",
            "标题": "%s（%d 处问题）" % (name, len(iss)),
            "来源": "M7-%s" % (check_doc.get("tag") or "机器检查"),
            "评分项": name, "当前状态": iss[0],
            "目标状态": "整改后重跑 check-rule 复核通过（check-report 人工确认闸门）",
            "动作步骤": ["修复：%s" % x for x in iss[:6]], "涉及素材": None,
            "优先级": "高", "预期加分": None,
            "验证方式": "重跑 check-rule --kind tech；check-report 人工确认闸门",
            "检查快照": {"id": c.get("id") or "", "name": name, "issues": iss},
        })
    return tasks


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


# ==================== T21 补救→M5 归档自动联动 ====================
_ARCHIVE_TYPES = ("素材补齐", "证据核验")


def gen_archive_entries(doc, known_task_ids=()):
    """归档申请条目生成（T21）：任务单中『已完成』且类型为 素材补齐/证据核验 且带涉及素材
    的任务 → 归档申请条目（动作/类别/素材名/来源任务/建议落点）。
    known_task_ids：已生成过申请的任务 id（去重，不重复生成）。纯逻辑无 I/O。"""
    entries = []
    for t in doc.get("tasks") or []:
        if t.get("完成状态") != "已完成":
            continue
        if t.get("类型") not in _ARCHIVE_TYPES:
            continue
        mat = t.get("涉及素材") or {}
        if not mat:
            continue
        if t.get("id") in known_task_ids:
            continue
        category = mat.get("category") or ""
        subtype = mat.get("subtype") or ""
        name = subtype or category or t.get("动作") or "待归档素材"
        entries.append({
            "任务ID": t["id"], "动作": t.get("动作", ""),
            "类别": category, "素材名": name, "来源": t.get("来源", ""),
            "评分项": t.get("评分项", ""),
            "建议落点": _archive_target_key(category),
            "状态": "待确认",
        })
    return entries


def _archive_target_key(category):
    return {"业绩": "performance", "人员": "personnel", "荣誉": "honors",
            "体系认证": "iso_certificates"}.get(category, "items")


def apply_archive(mat_doc, entries):
    """归档申请应用（T21）：按素材清单结构落点写入（M5 归档入口），
    返回 (mat_doc, applied, skipped)。纯逻辑无 I/O。
    旧结构 items[].category（items 含 category）→ 全部落 items 增条；
    fill-tpl 分键结构（performance/personnel/honors/iso_certificates）→ 按类别落点；
    无法映射类别 → items 增条。条目带 来源=任务ID 与 待归档标记，不冒充真实素材。"""
    import datetime as _dt
    mat_doc = dict(mat_doc)
    is_old = any(it.get("category") for it in (mat_doc.get("items") or []))
    applied, skipped = [], []
    now = _dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    for e in entries:
        cat = e.get("类别", "")
        sub = e.get("素材名", "")
        if _duplicate_exists(mat_doc, e):
            skipped.append(dict(e, 结果="已存在，跳过（同类别素材已登记）"))
            continue
        entry = {
            "category": cat, "subtype": sub if sub != cat else "",
            "purpose": "%s（M10 补救任务 %s）" % (e.get("动作", ""), e.get("任务ID", "")),
            "path": "待归档（人工补充扫描件路径）",
            "来源": "M10补救任务-%s" % e.get("任务ID", ""),
            "归档时间": now,
        }
        if is_old:
            mat_doc.setdefault("items", []).append(entry)
            key = "items"
        else:
            target = e.get("建议落点") or _archive_target_key(cat)
            if target == "performance":
                key = "performance"
                mat_doc.setdefault(key, []).append(
                    {"name": sub or "待归档业绩", "paths": [],
                     "来源": entry["来源"], "归档时间": now, "path": entry["path"]})
            elif target == "personnel":
                key = "personnel"
                role = "项目总监" if "总监" in sub else "监理人员"
                mat_doc.setdefault(key, []).append(
                    {"name": "待归档", "role": role, "职称": [],
                     "来源": entry["来源"], "归档时间": now})
            elif target == "honors":
                key = "honors"
                mat_doc.setdefault(key, []).append(
                    {"name": sub or "待归档荣誉", "path": entry["path"],
                     "来源": entry["来源"], "归档时间": now})
            elif target == "iso_certificates":
                key = "iso_certificates"
                mat_doc.setdefault(key, []).append(
                    {"name": sub or "待归档体系证书", "path": entry["path"],
                     "来源": entry["来源"], "归档时间": now})
            else:
                key = "items"
                entry["target"] = "items"
                mat_doc.setdefault("items", []).append(entry)
        applied.append({"任务ID": e.get("任务ID"), "类别": cat, "素材名": sub,
                        "落点": key, "时间": now})
    return mat_doc, applied, skipped


def _duplicate_exists(mat_doc, e):
    """同类别+同素材名 已登记（items 或对应分键）→ 跳过。"""
    cat = e.get("类别", "")
    sub = e.get("素材名", "")
    for it in (mat_doc.get("items") or []):
        if it.get("category") == cat and (it.get("subtype") == sub or (sub and sub == (it.get("subtype") or ""))):
            return True
    for key, name_attr in (("performance", "name"), ("personnel", "name"),
                           ("honors", "name"), ("iso_certificates", "name")):
        for it in (mat_doc.get(key) or []):
            if sub and it.get(name_attr) == sub:
                return True
    return False
