# -*- coding: utf-8 -*-
"""键名规范表（v2.4）：fill-tpl 文字占位键的权威登记与白名单校验依据。

模板制作（人工）与填充（fill-tpl）都以本表为唯一键源：
- 机器键（英文/既有中文键）→ 素材清单字段取值（fill-tpl V 字典）；
- 中文别名 → 模板可写别名或机器键，填充时统一解析；
- 不在本表 + 行级键（ROW_KEYS）之外出现的 {{ }} 键 = 未知键 → 填充后披露（不静默）。

平台无关：仅标准库，供 scripts/m5_project/fill_from_tpl.py 引用。
"""

# 键名规范表：机器键 → {"别名": 中文别名或 None, "说明": 取值来源/用途}
# 以 fill-tpl V 字典现行键为基准登记（2026-10-20 v2.4；规范《_模板制作规范.md》§3.1 同步）
KEY_SPEC = {
    "project_name": {"别名": "项目名称", "说明": "项目名称"},
    "project_code": {"别名": "招标编号", "说明": "招标编号/项目编号"},
    "bid_date": {"别名": "投标截止日期", "说明": "投标截止日期（格式化）"},
    "buyer_name": {"别名": "招标人", "说明": "招标人名称"},
    "bid_bond_cn": {"别名": "投标保证金", "说明": "投标保证金（大写中文）"},
    "company_name": {"别名": "企业名称", "说明": "投标人名称"},
    "company_nature": {"别名": "单位性质", "说明": "单位性质"},
    "company_address": {"别名": "企业地址", "说明": "企业地址"},
    "company_zip": {"别名": "企业邮编", "说明": "邮编"},
    "company_phone": {"别名": "企业联系电话", "说明": "联系电话"},
    "company_fax": {"别名": "企业传真", "说明": "传真"},
    "bank_name": {"别名": "开户银行", "说明": "开户银行"},
    "bank_account": {"别名": "开户账号", "说明": "开户账号"},
    "company_founded": {"别名": "成立时间", "说明": "成立时间"},
    "company_term": {"别名": "经营期限", "说明": "经营期限"},
    "industry": {"别名": "所属行业", "说明": "所属行业"},
    "日期": {"别名": None, "说明": "投标截止日期（既有中文键）"},
    "姓名": {"别名": "法定代表人姓名", "说明": "法定代表人姓名"},
    "性别": {"别名": None, "说明": "法定代表人性别（既有中文键）"},
    "年龄": {"别名": None, "说明": "法定代表人年龄（既有中文键）"},
    "职务": {"别名": None, "说明": "法定代表人职务（既有中文键）"},
    "agent_name": {"别名": "委托代理人姓名", "说明": "委托代理人姓名"},
    "agent_gender": {"别名": "委托代理人性别", "说明": "委托代理人性别"},
    "agent_age": {"别名": "委托代理人年龄", "说明": "委托代理人年龄"},
    "agent_title": {"别名": "委托代理人职务", "说明": "委托代理人职务"},
    "agent_job": {"别名": None, "说明": "委托代理人职务（既有兼容键）"},
    "agent_id": {"别名": "委托代理人身份证号", "说明": "委托代理人身份证号"},
    "license_no": {"别名": "统一社会信用代码", "说明": "统一社会信用代码"},
    "staff_count": {"别名": "从业人员", "说明": "从业人员数"},
    "tech_count": {"别名": "技术人员", "说明": "技术人员数"},
    "mgmt_count": {"别名": "管理人员", "说明": "管理人员数"},
    "revenue": {"别名": "营业收入", "说明": "营业收入"},
    "assets": {"别名": "资产总额", "说明": "资产总额"},
    "enterprise_scale": {"别名": "企业规模", "说明": "企业规模"},
    "legal_phone": {"别名": "法定代表人电话", "说明": "法定代表人电话"},
    "agent_phone": {"别名": "委托代理人手机号", "说明": "委托代理人手机号"},
    "项目说明": {"别名": None, "说明": "项目说明（既有中文键）"},
    "supervisor_name": {"别名": "拟派总监姓名", "说明": "拟派总监姓名（采购式）"},
    "supervisor_major": {"别名": "拟派总监专业", "说明": "拟派总监专业（采购式）"},
    "bid_price_num": {"别名": "投标报价", "说明": "投标报价（小写，采购式）"},
}

# 行级键（样板行/页复制后按素材对象填值，不做全局替换；与 fill_from_tpl.ROW_KEYS 同源）
PERSON_ROW_KEYS = {
    "人员姓名", "人员年龄", "人员出生年月", "人员学历", "人员专业",
    "人员职称", "人员职务", "人员身份证", "人员经历时间", "人员经历项目",
}
PERF_ROW_KEYS = {
    "业绩业主单位", "业绩项目名称", "业绩合同金额", "业绩起止时间",
    "业绩监理服务期", "业绩监理人员数量", "业绩联系人", "业绩联系电话",
}
ROW_KEYS = PERSON_ROW_KEYS | PERF_ROW_KEYS


def aliases():
    """返回 {别名: 机器键}（仅登记了别名的键）。"""
    return {spec["别名"]: mk for mk, spec in KEY_SPEC.items() if spec.get("别名")}


def is_registered(key):
    """键是否合法：机器键 / 中文别名 / 行级键。"""
    if key in ROW_KEYS:
        return True
    if key in KEY_SPEC:
        return True
    return key in aliases()


def registered_keys():
    """全部合法键（机器键 + 别名 + 行级键）。"""
    return set(KEY_SPEC) | set(aliases()) | ROW_KEYS


def check_spec():
    """自检：别名冲突/别名与机器键撞名；返回问题清单（空=通过）。"""
    issues = []
    keys = set(KEY_SPEC)
    al = aliases()
    for alias, mk in al.items():
        if alias in keys and alias != mk:
            issues.append("别名 %r 与机器键撞名（%s）" % (alias, mk))
    seen = {}
    for mk, spec in KEY_SPEC.items():
        al2 = spec.get("别名")
        if al2 and al2 in seen:
            issues.append("别名 %r 被 %s 与 %s 共用" % (al2, seen[al2], mk))
        if al2:
            seen[al2] = mk
    return issues
