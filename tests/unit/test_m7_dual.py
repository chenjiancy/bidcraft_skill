# -*- coding: utf-8 -*-
"""M7 双通道检查单测：rules 校验/差异比对 + rule_check 四项确定性规则。"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scripts"))

from m7_check import rules as m7rules       # noqa: E402
from m7_check import rule_check             # noqa: E402


def _mk_docx(path, paras=("正文",), table_cells=None):
    from docx import Document
    doc = Document()
    for t in paras:
        doc.add_paragraph(t)
    if table_cells:
        tbl = doc.add_table(1, len(table_cells))
        for i, c in enumerate(table_cells):
            tbl.rows[0].cells[i].text = c
    doc.save(str(path))


class TestValidateCheckJson(unittest.TestCase):
    def _valid(self):
        return {
            "project": "P", "channel": "B", "审查日期": "2026-10-18",
            "结论": "通过",
            "废标红线": [{"条款": "x", "是否响应": "响应", "证据位置": "p1",
                        "风险等级": "🔴", "说明": "y"}],
            "维度明细": [{"维度": "报价", "风险等级": "🟢", "问题描述": "d",
                         "来源追溯": "s", "整改建议": "f"}],
            "整改清单": [{"优先级": "高", "问题": "q", "补正": "c"}],
            "通道A差异说明": "一致", "总结": "ok",
        }

    def test_valid_passes(self):
        ok, issues = m7rules.validate_check_json(self._valid())
        self.assertTrue(ok, issues)

    def test_missing_channel_rejected(self):
        doc = self._valid()
        doc["channel"] = "A"
        ok, issues = m7rules.validate_check_json(doc)
        self.assertFalse(ok)
        self.assertTrue(any("channel" in x for x in issues))

    def test_bad_conclusion_rejected(self):
        doc = self._valid()
        doc["结论"] = "未知"
        ok, issues = m7rules.validate_check_json(doc)
        self.assertFalse(ok)

    def test_bad_risk_level_rejected(self):
        doc = self._valid()
        doc["维度明细"][0]["风险等级"] = "🟣"
        ok, issues = m7rules.validate_check_json(doc)
        self.assertFalse(ok)
        self.assertTrue(any("风险等级" in x for x in issues))

    def test_empty_dimensions_rejected(self):
        doc = self._valid()
        doc["维度明细"] = []
        ok, issues = m7rules.validate_check_json(doc)
        self.assertFalse(ok)


class TestCompareDual(unittest.TestCase):
    def test_omission_hint(self):
        machine = {"检查": [{"id": "quote", "name": "报价一致性", "level": "致命",
                            "category": "报价", "ok": False,
                            "issues": ["投标报价超限价"]}]}
        check = {"维度明细": [{"维度": "资格符合性", "风险等级": "🟢", "问题描述": "无",
                              "来源追溯": "s", "整改建议": ""}]}
        diffs = m7rules.compare_dual(machine, check)
        self.assertTrue(any(d["差异类型"] == "遗漏提示" and d["检查项"] == "报价一致性"
                            for d in diffs))

    def test_conflict_detected(self):
        machine = {"检查": [{"id": "quote", "name": "报价一致性", "level": "致命",
                            "category": "报价", "ok": False,
                            "issues": ["投标报价超限价"]}]}
        check = {"维度明细": [{"维度": "报价", "风险等级": "🟢", "问题描述": "报价无风险",
                              "来源追溯": "s", "整改建议": ""}]}
        diffs = m7rules.compare_dual(machine, check)
        self.assertTrue(any(d["差异类型"] == "结论冲突" for d in diffs))

    def test_semantic_only_dimension(self):
        machine = {"检查": []}
        check = {"维度明细": [{"维度": "签章", "风险等级": "🟠", "问题描述": "签章缺失",
                              "来源追溯": "s", "整改建议": ""}]}
        diffs = m7rules.compare_dual(machine, check)
        self.assertTrue(any(d["差异类型"] == "仅通道B（语义审查）" for d in diffs))


class TestRuleCheckQuote(unittest.TestCase):
    def test_over_limit_flagged(self):
        with tempfile.TemporaryDirectory() as td:
            out, tpl = Path(td) / "out", Path(td) / "tpl"
            out.mkdir(); tpl.mkdir()
            _mk_docx(out / "a.docx", ["投标总价：500000.00 元"])
            material = {"投标报价": "500000.00"}
            points = {"modules": [{"id": "pricing", "type": "fields", "fields": {
                "报价上限（废标线）": {"value": "投标报价高于最高限价（48.86万元）作无效标处理"}}}]}
            ok, issues = rule_check.check_quote(out, tpl, material, points)
            self.assertFalse(ok)
            self.assertTrue(any("最高限价" in x and ">" in x for x in issues))

    def test_ok_within_limit_and_no_diff(self):
        with tempfile.TemporaryDirectory() as td:
            out, tpl = Path(td) / "out", Path(td) / "tpl"
            out.mkdir(); tpl.mkdir()
            _mk_docx(out / "a.docx", ["投标总价：388600.00 元"])
            material = {"投标报价": "388600.00"}
            points = {"modules": [{"id": "pricing", "type": "fields", "fields": {
                "报价上限（废标线）": {"value": "最高限价（48.86万元）"}}}]}
            ok, issues = rule_check.check_quote(out, tpl, material, points)
            self.assertTrue(ok, issues)

    def test_missing_bid_price_skips(self):
        with tempfile.TemporaryDirectory() as td:
            out, tpl = Path(td) / "out", Path(td) / "tpl"
            out.mkdir(); tpl.mkdir()
            ok, issues = rule_check.check_quote(out, tpl, {}, {})
            self.assertTrue(ok)
            self.assertTrue(any("跳过" in x for x in issues))


class TestRuleCheckCert(unittest.TestCase):
    def test_expired_filename_flagged(self):
        material = {"投标截止日期": "2026-08-10 14:00",
                    "personnel": [{"name": "甲", "注册证书": [
                        "E:\\素材\\人员\\甲\\注册证书\\注册监理工程师_20240101_20250101.png"]}]}
        ok, issues = rule_check.check_cert("", "", material, {})
        self.assertFalse(ok)
        self.assertTrue(any("推断到期日" in x for x in issues))

    def test_valid_expiry_passes(self):
        material = {"投标截止日期": "2026-08-10 14:00",
                    "personnel": [{"name": "甲", "注册证书": [
                        "E:\\素材\\人员\\甲\\注册证书\\注册监理工程师_20280123_20270220.png"]}]}
        ok, issues = rule_check.check_cert("", "", material, {})
        self.assertTrue(ok, issues)

    def test_honor_not_checked(self):
        """荣誉=颁发日非到期日，不参与推断（防误报）。"""
        material = {"投标截止日期": "2026-08-10 14:00",
                    "honors": [{"name": "监理示范工程", "path": "E:\\素材\\荣誉\\监理示范工程_20241201.png"}]}
        ok, issues = rule_check.check_cert("", "", material, {})
        self.assertTrue(ok, issues)


class TestRuleCheckMaterial(unittest.TestCase):
    def test_missing_file_flagged(self):
        with tempfile.TemporaryDirectory() as td:
            material = {"qualification_required": [
                {"name": "营业执照", "path": str(Path(td) / "不存在.png")}]}
            ok, issues = rule_check.check_material("", "", material, {})
            self.assertFalse(ok)
            self.assertTrue(any("素材缺失" in x for x in issues))

    def test_all_present_passes(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "证.png"
            p.write_bytes(b"x")
            material = {"qualification_required": [{"name": "营业执照", "path": str(p)}]}
            ok, issues = rule_check.check_material("", "", material, {})
            self.assertTrue(ok, issues)


class TestRuleCheckDeadline(unittest.TestCase):
    def test_missing_keyword_flagged(self):
        with tempfile.TemporaryDirectory() as td:
            out, tpl = Path(td) / "out", Path(td) / "tpl"
            out.mkdir(); tpl.mkdir()
            _mk_docx(out / "a.docx", ["普通正文没有期限表述"])
            points = {"modules": [{"id": "basic", "type": "fields", "fields": {
                "投标有效期": {"value": "递交响应文件截止时间后90天"},
                "服务期": {"value": "监理服务期限自开工至缺陷责任期"}}}]}
            ok, issues = rule_check.check_deadline(out, tpl, {}, points)
            self.assertFalse(ok)
            self.assertTrue(any("未找到" in x for x in issues))

    def test_present_is_info_not_fail(self):
        with tempfile.TemporaryDirectory() as td:
            out, tpl = Path(td) / "out", Path(td) / "tpl"
            out.mkdir(); tpl.mkdir()
            _mk_docx(out / "a.docx", ["投标有效期内遵守承诺 90 天", "服务期：自开工至缺陷责任期"])
            points = {"modules": [{"id": "basic", "type": "fields", "fields": {
                "投标有效期": {"value": "90天"}, "服务期": {"value": "服务期"}}}]}
            ok, issues = rule_check.check_deadline(out, tpl, {}, points)
            self.assertTrue(ok)
            self.assertTrue(all("信息" in x for x in issues))


class TestNamingTag(unittest.TestCase):
    def test_default_no_tag(self):
        self.assertEqual(m7rules.machine_base("P"), "机器检查_P")
        self.assertEqual(m7rules.points_base("P"), "检查要点_P")
        self.assertEqual(m7rules.diff_base("P"), "双通道检查差异_P")
        self.assertEqual(m7rules.report_base("P"), "标书检查报告_P")

    def test_with_tag_appends(self):
        self.assertEqual(m7rules.machine_base("P", "上传版"), "机器检查_P_上传版")
        self.assertEqual(m7rules.points_base("P", "v2"), "检查要点_P_v2")
        self.assertEqual(m7rules.diff_base("P", "上传版"), "双通道检查差异_P_上传版")
        self.assertEqual(m7rules.report_base("P", "上传版"), "标书检查报告_P_上传版")


class TestRuleCheckSingleFile(unittest.TestCase):
    def test_single_docx_out_runs_placeholder_and_skips_template(self):
        """单文件上传场景：占位/敏感真实执行；format/pages/frozen 跳过（无模板对照）。"""
        with tempfile.TemporaryDirectory() as td:
            tdir = Path(td) / "tender"
            tdir.mkdir()
            out = Path(td) / "upload.docx"
            _mk_docx(out, ["投标函【招标人】、【项目名称】", "正文"])
            # M4 产物（空素材/要点，保证标准可读）
            (tdir / ("素材清单_%s.json" % "P")).write_text(
                '{"投标截止日期": "2026-08-10 14:00", "personnel": [], "honors": [],'
                ' "qualification_required": [], "iso_certificates": [],'
                ' "performance": [], "social_security_required": []}',
                encoding="utf-8")
            (tdir / ("投标要点_%s.json" % "P")).write_text(
                '{"modules": []}', encoding="utf-8")
            proj = Path(td) / "P"
            proj.mkdir()
            (proj / "商务标").mkdir()
            res = rule_check.run_rule_checks("ent", proj, out_dir=str(out), tdir=str(tdir), tag="上传版")
            self.assertEqual(res["tag"], "上传版")
            self.assertTrue((proj / "标书检查" / "机器检查_P_上传版.json").is_file())
            by_id = {c["id"]: c for c in res["检查"]}
            # 占位符真实检查出残留
            self.assertFalse(by_id["placeholder"]["ok"])
            self.assertTrue(any("【招标人】" in i for i in by_id["placeholder"]["issues"]))
            # 模板对照类跳过
            for cid in ("format", "pages", "frozen"):
                self.assertTrue(by_id[cid]["ok"], cid)
                self.assertTrue(any("跳过" in i for i in by_id[cid]["issues"]))


if __name__ == "__main__":
    unittest.main()
