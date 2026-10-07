# -*- coding: utf-8 -*-
"""
bidcraft · M1 素材库 —— 命名规范引擎·日期抽取 / 智能分类（供归档建议使用）。

从 naming.py 拆分（文件行数治理）；由 naming.py 在文件末尾 re-export，
对外接口（nm.extract_date / nm.extract_dates / nm.classify）保持不变。
"""
import re

from .naming_base import LONG_TERM, UNKNOWN_DATE
from .naming import split_ext

__all__ = ["extract_date", "extract_dates", "classify"]


# --------------------------------------------------------------------------
# 日期抽取 / 智能分类（供归档建议使用）
# --------------------------------------------------------------------------
def extract_date(text):
    """从任意文本中抽取第一个日期归一值；支持 长期 / 日期不详。"""
    if text is None:
        return None
    s = str(text)
    if LONG_TERM in s or "长期有效" in s:
        return LONG_TERM
    if UNKNOWN_DATE in s or "不详" in s:
        return UNKNOWN_DATE
    m = re.search(r"(?<!\d)(\d{8})(?!\d)", s)
    if m:
        return m.group(1)
    m = re.search(r"(?<!\d)(\d{4})\s*[-./年]\s*(\d{1,2})\s*[-./月]\s*(\d{1,2})", s)
    if m:
        try:
            return "%04d%02d%02d" % (int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    return None


def extract_dates(text):
    """抽取全部日期归一值（保序、去重）。"""
    if text is None:
        return []
    s = str(text)
    found = re.findall(r"(?<!\d)(\d{8})(?!\d)", s)
    if not found:
        m = re.search(r"(?<!\d)(\d{4})\s*[-./年]\s*(\d{1,2})\s*[-./月]\s*(\d{1,2})", s)
        if m:
            found = ["%04d%02d%02d" % (int(m.group(1)), int(m.group(2)), int(m.group(3)))]
    out = []
    for f in found:
        if f not in out:
            out.append(f)
    return out


# 关键字 → (大类, 子类) 的启发式映射（顺序即优先级）
_HEURISTICS = [
    (("营业执照",), ("资质", "营业执照")),
    (("开户许可证", "基本户", "银行开户"), ("财务", "财务证照")),
    (("ISO", "质量管理体系", "环境管理体系", "职业健康", "体系认证", "认证证书"), ("资质", "体系认证")),
    (("信用", "AAA", "守合同", "重信用", "诚信"), ("资质", "信用证书")),
    (("身份证",), ("人员", "身份证")),
    (("毕业证", "学位证", "学历证书"), ("人员", "毕业证")),
    (("简历",), ("人员", "简历")),
    (("退休",), ("人员", "退休证")),
    (("返聘",), ("人员", "返聘协议")),
    (("优秀",), ("人员", "个人荣誉")),  # 优秀XX工程师/总监/监理员等个人荣誉（置于注册证书之前，避免被"监理工程师"抢判）
    (("劳动模范", "先进工作者", "先进生产者", "优秀共产党员", "先进生产"), ("人员", "个人荣誉")),
    (("注册", "建造师", "监理工程师", "造价工程师", "注册证", "执业"), ("人员", "注册证书")),
    (("岗位", "上岗", "培训", "继续教育"), ("人员", "岗位证书")),
    (("职称", "高级工程师", "中级工程师", "助理工程师", "工程师"), ("人员", "职称证书")),
    (("监理合同", "施工合同", "合同", "协议"), ("业绩", "业绩文件")),
    (("竣工", "验收", "备案", "中标通知书", "结算", "概况", "一览表", "竣工验收记录", "竣工验收报告"), ("业绩", "业绩文件")),
    (("示范工程", "标准化工地", "文明工地", "先进单位", "重合同守信用", "诚信", "AAA", "奖状", "获奖", "荣誉", "牌匾"), ("荣誉", "荣誉证书")),
    (("组织机构图", "组织架构", "机构设置", "企业简介", "管理体系图"), ("企业介绍", "组织架构")),
    (("企业历史", "公司历史", "发展历程", "经营历史"), ("企业介绍", "企业历史")),
    (("中小企业声明函",), ("财务", "中小企业声明函")),
    (("资质", "等级证书", "甲级", "乙级", "丙级"), ("资质", "资质证书")),
]


def classify(filename):
    """
    按文件名启发式判断归属。
    返回 (大类, 子类, 命中的关键字)；判不出返回 (None, None, None)。
    """
    stem, _ = split_ext(filename)
    text = stem
    for keys, target in _HEURISTICS:
        for k in keys:
            if k in text:
                return target[0], target[1], k
    return None, None, None
