# -*- coding: utf-8 -*-
"""
bidcraft · M8 模拟评标 —— 通道B 主观分评审 JSON 结构校验（eval-parse 落盘闸门）
对齐 m7_check/rules.py 的 validate_check_json 风格。
"""
REQUIRED_KEYS = ("project", "channel", "审查日期", "对象", "主观评分", "主观合计", "失分诊断", "结论")
RISK_LEVELS = ("🔴", "🟠", "🟡", "🟢")
PRIORITIES = ("高", "中", "低")
DIM_NAMES = ("完整度", "内容质量", "篇幅合规", "暗标合规", "证据锚点")


def validate_subjective_json(obj):
    """校验通道B 主观评分 JSON → (ok, issues)。"""
    issues = []
    if not isinstance(obj, dict):
        return False, ["主观评分 JSON 顶层必须是对象"]
    for k in REQUIRED_KEYS:
        if k not in obj:
            issues.append("缺少必需字段：%s" % k)
    if obj.get("channel") != "B":
        issues.append("channel 必须为 B（本 JSON 是通道B 主观评审产物）")
    if not issues:
        items = obj.get("主观评分")
        if not isinstance(items, list) or not items:
            issues.append("主观评分 必须是非空数组")
        else:
            for i, it in enumerate(items):
                if not isinstance(it, dict):
                    issues.append("主观评分[%d] 必须是对象" % i)
                    continue
                for k in ("子项", "满分", "预估分", "档次", "证据锚点", "失分原因", "补强建议", "风险"):
                    if k not in it:
                        issues.append("主观评分[%d] 缺少字段：%s" % (i, k))
                risk = it.get("风险")
                if risk and risk not in RISK_LEVELS:
                    issues.append("主观评分[%d] 风险等级非法：%s（须为 🔴/🟠/🟡/🟢）" % (i, risk))
                est = it.get("预估分")
                if isinstance(est, dict):
                    m, x = est.get("min"), est.get("max")
                    if not (isinstance(m, (int, float)) and isinstance(x, (int, float))):
                        issues.append("主观评分[%d] 预估分 min/max 须为数字" % i)
                    elif m > x:
                        issues.append("主观评分[%d] 预估分 min(%s) > max(%s)" % (i, m, x))
                else:
                    issues.append("主观评分[%d] 预估分 须为 {min,max,建议}" % i)
        total = obj.get("主观合计")
        if not isinstance(total, dict):
            issues.append("主观合计 必须是对象")
        elif "满分" not in total or "建议" not in total:
            issues.append("主观合计 缺少 满分/建议")
        for it in obj.get("失分诊断") or []:
            if it.get("优先级") not in PRIORITIES:
                issues.append("失分诊断 优先级非法：%s（须为 高/中/低）" % it.get("优先级"))
    return (not issues), issues
