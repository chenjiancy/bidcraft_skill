# -*- coding: utf-8 -*-
"""⑦ filler 拆包 · 文字占位填充 + 通用 docx 文本工具。"""
import re

from _shared import docx_util as _docx_util

from .fill_common import DATE_RE
from .fill_combo import _cert_major, _qual_level_from_mat  # noqa: F401

__all__ = [
    "TEXT_KEY_MAP", "_mat_value", "_fmt_date", "_para_full_text", "_para_runs",
    "_set_para_text", "_iter_doc_paragraphs", "_scan_remaining_placeholders",
    "_fill_text_placeholders",
]


# ---------------------------------------------------------------------------
# 文字占位 → 素材字段映射（KEY 取素材清单顶层字段或「企业基础信息」子字段）
# 值可为字符串/数字；占位符在段落或表格单元格中整体替换
# ---------------------------------------------------------------------------
def _mat_value(material, biz, key):
    """返回 (值, 是否待补)。key: 素材清单顶层键 或 企业基础信息.<子键>。"""
    if key.startswith("biz."):
        return biz.get(key[4:], ""), False
    if key in ("project", "project_id", "招标人", "投标截止日期"):
        return str(material.get(key, "")), False
    return str(material.get(key, "")), False


TEXT_KEY_MAP = {
    "【项目名称】": ("project", "素材清单.project"),
    "【项目编号】": ("project_id", "素材清单.project_id"),
    "【日期】": ("投标截止日期", "投标截止日期（2026-10-09）"),
    "【招标人】": ("招标人", "招标人"),
    "【招标人名称】": ("招标人", "招标人"),
    "【投标人名称】": ("biz.投标人名称", "企业基础信息.投标人名称"),
    "【统一社会信用代码】": ("biz.统一社会信用代码", "企业基础信息.统一社会信用代码"),
    "【企业地址】": ("biz.企业地址", "企业基础信息.企业地址"),
    "【邮编】": ("biz.邮编", "企业基础信息.邮编"),
    "【联系电话】": ("biz.联系电话", "企业基础信息.联系电话"),
    "【法定代表人联系电话】": ("biz.联系电话", "企业基础信息.联系电话"),
    "【传真】": ("biz.传真", "企业基础信息.传真"),
    "【开户银行】": ("biz.开户银行", "企业基础信息.开户银行"),
    "【开户账号】": ("biz.开户账号", "企业基础信息.开户账号"),
    "【成立时间】": ("biz.成立时间", "企业基础信息.成立时间"),
    "【经营期限】": ("biz.经营期限", "企业基础信息.经营期限"),
    "【单位性质】": ("biz.单位性质", "企业基础信息.单位性质"),
    "【法定代表人姓名】": ("biz.法定代表人姓名", "企业基础信息.法定代表人姓名"),
    "【性别】": ("biz.性别", "企业基础信息.性别"),
    "【年龄】": ("biz.年龄", "企业基础信息.年龄"),
    "【职务】": ("biz.职务", "企业基础信息.职务"),
    "【身份证号】": ("biz.身份证号", "企业基础信息.身份证号"),
    "【投标保证金金额（大写）】": ("_bail_cap", "壹万元整（固定值）"),
    "【总监姓名】": ("_director", "personnel[0].name"),
    "【总监专业】": ("_director_major", "市政公用工程（招标要求）"),
    "【企业资质等级】": ("_qual_level", "资质证书扫描件"),
    "【业主名称】": ("招标人", "招标人"),
    "【投标总价（元）】": ("_pending", "报价策略待定（素材清单 pending）"),
    "【授权代理人姓名】": ("_pending", "授权委托书待制作"),
    "【监理经历：（国内）X年（国际）X年】": ("_pending", "企业监理经历年限待补"),
    "【职工总人数X人 / 技术人员X人 / 管理人员X人】": ("_pending", "企业职工人数待补"),
}


def _fmt_date(deadline):
    """2026-10-09 09:00 → 2026年10月9日"""
    m = DATE_RE.match(str(deadline or "").strip())
    if not m:
        return ""
    y, mo, d = m.groups()
    return "%s年%d月%d日" % (y, int(mo), int(d))


# ---------------------------------------------------------------------------
# 通用 docx 工具（委托 _shared.docx_util，跨 run 安全）
# ---------------------------------------------------------------------------
def _para_full_text(p):
    return _docx_util.para_text(p)


def _para_runs(p):
    return _docx_util.para_runs(p)


def _set_para_text(p, text):
    """整段替换为 text，保留首 run 的 rPr（样式）。委托公共工具。"""
    return _docx_util.set_para_text(p, text)


def _iter_doc_paragraphs(doc):
    """正文段落 + 表格内段落（含嵌套表格）。"""
    for p in doc.paragraphs:
        yield p
    for t in doc.tables:
        for row in t.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    yield p


def _scan_remaining_placeholders(doc, fname, pending):
    """填充后残留【xxx】扫描 → 待补清单（未映射/缺值的占位符）。"""
    seen = set()
    for p in _iter_doc_paragraphs(doc):
        for ph in re.findall(r"【[^】]+】", _para_full_text(p)):
            if ph not in seen:
                seen.add(ph)
                pending.append("%s：残留占位符（%s）" % (ph, fname))
    return len(seen)


def _fill_text_placeholders(doc, material, biz, deadline, pending):
    """段落级文字占位：映射有值则替换；无映射/值空 → pending 保留占位。"""
    filled = 0
    # 正文括注占位（非【】格式）：中小企业声明函「承接企业为（企业名称）」
    biz_name = biz.get("投标人名称", "") or ""
    if biz_name:
        for p in _iter_doc_paragraphs(doc):
            t = _para_full_text(p)
            if "（企业名称）" in t:
                _set_para_text(p, t.replace("（企业名称）", biz_name))
                filled += 1
    for p in _iter_doc_paragraphs(doc):
        t = _para_full_text(p)
        if "【" not in t:
            continue
        for ph, (key, note) in TEXT_KEY_MAP.items():
            if ph not in t:
                continue
            if key == "_pending":
                pending.append("%s → %s（保留占位待补）" % (ph, note))
                continue
            if key == "_director":
                ps = material.get("personnel", [])
                v = ps[0].get("name", "") if ps else ""
            elif key == "_director_major":
                # ⑧ 数据驱动：素材清单「投标资格专业」优先，其次 personnel[0].cert 括注
                v = material.get("投标资格专业") or _cert_major(material)
            elif key == "_qual_level":
                v = _qual_level_from_mat(material)
            elif key == "_bail_cap":
                v = "壹万元整"
            elif key == "投标截止日期":
                v = _fmt_date(deadline)
            else:
                v, _ = _mat_value(material, biz, key)
            if not v:
                pending.append("%s → %s（值缺失，保留占位待补）" % (ph, note))
                continue
            _set_para_text(p, t.replace(ph, v))
            filled += 1
            t = _para_full_text(p)
    return filled
