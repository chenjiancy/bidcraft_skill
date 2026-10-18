# -*- coding: utf-8 -*-
"""
bidcraft · M7 标书检查 —— 命名/校验/双通道差异比对（纯逻辑，无 I/O）

v2.0 双通道检查（对齐 M4 招标解析双通道架构）：
  - 通道A：check-rule 机器检查规则引擎（确定性规则，代码控制正确性）
  - 通道B：check-parse agent 语义审查（按 references/M7-标书检查-提示词.md，
           消费 M4 解析产物，不再重复提取标准）
  - 差异：check-diff 双通道差异比对 → 人工裁决
  - 报告：check-report HTML 渲染（人工确认闸门）

产物落位：<企业>/项目级/<项目>/标书检查/
  - 机器检查_<项目>.json/.md            （通道A）
  - 检查要点_<项目>.json/.md            （通道B，agent 产出双份落盘）
  - 双通道检查差异_<项目>.json/.md      （check-diff）
  - 标书检查报告_<项目>.html            （check-report）
"""

# 通道A 检查项类别 ↔ 通道B 维度枚举 对齐映射（差异比对用）
# 通道A category → 通道B 应报告的维度名；A 检出问题而 B 未报告该维度 → 差异
CATEGORY_DIMENSION = {
    "报价": "报价",
    "证书": "证书",
    "期限": "期限",
    "完整性": "完整性",
    "格式": "排版",
    "占位": "占位",
    "敏感": "敏感",
    "页数": "排版",
    "冻结": "冻结",
    "可打开性": "可打开性",
}

# 通道B 维度明细「维度」枚举（提示词输出 schema 强制）
DIMENSIONS = [
    "资格符合性", "人员配置", "报价", "证书", "期限", "完整性", "签章",
    "暗标", "一致性", "排版", "占位", "敏感", "冻结", "可打开性", "废标红线",
]

RISK_LEVELS = ("🔴", "🟠", "🟡", "🟢")


# --------------------------------------------------------------------------
# 命名基础（与 m4_tender/rules.py 同风格）
# --------------------------------------------------------------------------
def check_subdir():
    """标书检查产物子目录名（项目级/<项目>/标书检查/）。"""
    return "标书检查"


def machine_base(project):
    """通道A 机器检查文件名基：机器检查_<项目>"""
    return "机器检查_%s" % project


def points_base(project):
    """通道B agent 检查要点文件名基：检查要点_<项目>"""
    return "检查要点_%s" % project


def diff_base(project):
    """双通道检查差异文件名基：双通道检查差异_<项目>"""
    return "双通道检查差异_%s" % project


def report_base(project):
    """标书检查 HTML 报告文件名基：标书检查报告_<项目>"""
    return "标书检查报告_%s" % project


# --------------------------------------------------------------------------
# 通道B 检查要点 JSON 结构校验（agent 产物落盘闸门，对齐 tender-parse）
# --------------------------------------------------------------------------
REQUIRED_KEYS = ("project", "channel", "结论", "废标红线", "维度明细", "整改清单", "总结")


def validate_check_json(obj):
    """校验通道B 检查要点 JSON 最小结构 → (ok, issues)。

    schema（与 M7-标书检查-提示词.md 输出 schema 完全一致）：
      project / channel("B") / 审查日期
      结论        : "通过" | "存在风险"
      废标红线    : [ {条款, 是否响应, 证据位置, 风险等级, 说明} ]
      维度明细    : [ {维度(枚举), 风险等级(🔴🟠🟡🟢), 问题描述, 来源追溯, 整改建议} ]
      整改清单    : [ {优先级(高|中|低), 问题, 补正} ]
      通道A差异说明: str（与机器检查结果对比）
      总结        : str
    """
    issues = []
    if not isinstance(obj, dict):
        return False, ["检查要点 JSON 顶层必须是对象"]
    for k in ("project", "channel"):
        if not obj.get(k):
            issues.append("缺少关键字段：%s" % k)
    if obj.get("channel") not in (None, "B"):
        issues.append("channel 必须是 \"B\"（当前：%r）" % obj.get("channel"))
    if obj.get("结论") not in ("通过", "存在风险"):
        issues.append("结论 必须是 \"通过\" 或 \"存在风险\"（当前：%r）" % obj.get("结论"))
    red = obj.get("废标红线")
    if not isinstance(red, list):
        issues.append("废标红线 必须是非空数组（每条含 条款/是否响应/证据位置/风险等级）")
    dims = obj.get("维度明细")
    if not isinstance(dims, list) or not dims:
        issues.append("维度明细 必须是非空数组")
    else:
        for i, d in enumerate(dims):
            if not isinstance(d, dict) or not d.get("维度"):
                issues.append("维度明细[%d]：缺少「维度」（枚举：%s）"
                              % (i, "|".join(DIMENSIONS)))
            lv = d.get("风险等级") or ""
            if lv and lv not in RISK_LEVELS:
                issues.append("维度明细[%d]：风险等级必须是 %s 之一（当前：%r）"
                              % (i, "/".join(RISK_LEVELS), lv))
            for k in ("问题描述", "来源追溯", "整改建议"):
                if not d.get(k):
                    issues.append("维度明细[%d]：缺少「%s」" % (i, k))
    fixes = obj.get("整改清单")
    if not isinstance(fixes, list):
        issues.append("整改清单 必须是非空数组（每条含 优先级/问题/补正）")
    if not obj.get("总结"):
        issues.append("缺少关键字段：总结")
    return (not issues, issues)


# --------------------------------------------------------------------------
# 双通道差异比对（对齐 m4_tender.rules.compare_dual 思路）
# --------------------------------------------------------------------------
def _normalize(text):
    """问题文本归一化：去空白/标点，仅留中英文与数字（主题词比较用）。"""
    import re
    s = (text or "").strip()
    s = re.sub(r"[\s，。；：、（）()【】\[\]「」\"'“”‘’\-—·]+", "", s)
    return s


def compare_dual(machine_doc, check_doc):
    """通道A 机器检查 vs 通道B 检查要点 → 差异清单。

    差异类型：
      - 遗漏提示：通道A 某类别检查未通过，而通道B 维度明细未报告该类别任何问题
        （人工裁决：A 机器检出是否真实 / B 是否遗漏）
      - 冲突：通道A 检出严重问题，而通道B 同类别维度标「无问题/通过」
      - 仅通道B：通道B 报告的语义维度（A 设计上不覆盖）——列为说明，不算差异
    返回 [{差异类型, 检查项/维度, 通道A, 通道B, 建议}]。
    """
    diffs = []
    if not machine_doc or not check_doc:
        return diffs
    a_checks = machine_doc.get("检查") or []
    b_dims = check_doc.get("维度明细") or []

    # 通道B 已报告的维度集合（有非空问题描述即记录；🟢 无风险也是"报告了该维度"）
    b_reported = {}
    for d in b_dims:
        dim = d.get("维度") or ""
        lv = d.get("风险等级") or "🟢"
        desc = _normalize(d.get("问题描述"))
        if desc:
            b_reported.setdefault(dim, []).append((lv, desc))

    # 通道A 各检查项
    for c in a_checks:
        if c.get("ok"):
            continue
        cat = c.get("category") or ""
        dim = CATEGORY_DIMENSION.get(cat, cat)
        issues = c.get("issues") or []
        if not issues:
            continue
        # A 该类别存在非零问题 → 是否在 B 中出现
        b_hits = b_reported.get(dim) or []
        b_has_severe = any(lv in ("🔴", "🟠") for lv, _ in b_hits)
        # 冲突：A 致命/严重级问题 vs B 同维度无严重级报告（🟢🟡 或无问题描述）
        if c.get("level") in ("致命", "严重") and b_hits and not b_has_severe:
            diffs.append({
                "差异类型": "结论冲突",
                "检查项": c.get("name") or c.get("id"),
                "维度": dim,
                "通道A": "%s：%s" % (c.get("level", ""), issues[0][:120]),
                "通道B": "同维度仅报 %s 级问题（%d 条）" %
                         (b_hits[0][0] if b_hits else "🟢", len(b_hits)),
                "建议": "人工核对：通道A 机器判定与通道B 语义审查结论相反，须回原文件裁决",
            })
            continue
        if not b_hits:
            diffs.append({
                "差异类型": "遗漏提示",
                "检查项": c.get("name") or c.get("id"),
                "维度": dim,
                "通道A": "%s：%s" % (c.get("level", ""), issues[0][:120]),
                "通道B": "（通道B 未报告该维度任何问题）",
                "建议": "核对通道A 是否误报，或通道B 是否遗漏该维度（人工裁决）",
            })

    # 通道B 语义维度说明（A 设计上不覆盖 → 说明项）
    for d in b_dims:
        dim = d.get("维度") or ""
        if dim in ("资格符合性", "人员配置", "签章", "暗标", "一致性", "废标红线"):
            lv = d.get("风险等级") or "🟢"
            if lv in ("🔴", "🟠"):
                diffs.append({
                    "差异类型": "仅通道B（语义审查）",
                    "检查项": dim,
                    "维度": dim,
                    "通道A": "（通道A 规则引擎不覆盖语义维度）",
                    "通道B": "%s：%s" % (lv, _normalize(d.get("问题描述"))[:120]),
                    "建议": "该维度仅由 agent 语义审查，须人工核对证据位置后确认",
                })
    return diffs
