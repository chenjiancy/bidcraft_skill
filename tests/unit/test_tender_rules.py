# -*- coding: utf-8 -*-
"""L1 单元测试：M4 纯逻辑层（JSON 结构校验 / 命名 / 素材对照三态 / 渲染）。
纯逻辑无 I/O，数量最多、速度最快。"""
import sys
import os
import unittest

_SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scripts")
sys.path.insert(0, os.path.abspath(_SCRIPTS))
from m4_tender import rules  # noqa: E402


# --------------------------------------------------------------------------
# 项目名校验
# --------------------------------------------------------------------------
class TestValidateProjectName(unittest.TestCase):
    def test_valid_cn(self):
        self.assertEqual(rules.validate_project_name("XX安置房项目监理"), (True, ""))

    def test_valid_with_punct(self):
        self.assertEqual(rules.validate_project_name("XX（一期）建设项目-监理"), (True, ""))

    def test_empty(self):
        ok, _ = rules.validate_project_name("")
        self.assertFalse(ok)
        ok, _ = rules.validate_project_name("   ")
        self.assertFalse(ok)

    def test_dot(self):
        self.assertFalse(rules.validate_project_name(".")[0])
        self.assertFalse(rules.validate_project_name("..")[0])

    def test_illegal_chars(self):
        for bad in ["a/b", "a\\b", "a:b", "a*b", 'a"b', "a<b", "a>b", "a|b", "a?b"]:
            self.assertFalse(rules.validate_project_name(bad)[0], bad)


# --------------------------------------------------------------------------
# 产物 JSON 最小结构校验（v2.1：9 模块全覆盖 + diffs 结构）
# --------------------------------------------------------------------------
def _points9(extra=None, **kw):
    """9 模块全集的合法投标要点 JSON。"""
    doc = {"project": "P1", "modules": [
        {"id": "basic", "title": "项目基本信息", "type": "fields"},
        {"id": "qualification", "title": "资格条件", "type": "items"},
        {"id": "staff", "title": "人员配备", "type": "fields"},
        {"id": "project_overview", "title": "项目概况与监理工作内容", "type": "fields"},
        {"id": "scoring", "title": "评分办法", "type": "mixed"},
        {"id": "pricing", "title": "报价要求", "type": "fields"},
        {"id": "submission", "title": "响应文件编制与递交", "type": "fields"},
        {"id": "reject", "title": "废标/否决红线", "type": "items"},
        {"id": "pending", "title": "待确认/缺失项", "type": "items"},
    ]}
    if extra:
        doc["modules"].append(extra)
    doc.update(kw)
    return doc


class TestValidatePointsJson(unittest.TestCase):
    def test_valid_9modules(self):
        self.assertEqual(rules.validate_points_json(_points9()), (True, []))

    def test_valid_with_extra_module(self):
        doc = _points9(extra={"id": "performance", "title": "补充", "type": "items"})
        self.assertEqual(rules.validate_points_json(doc), (True, []))

    def test_top_not_dict(self):
        self.assertFalse(rules.validate_points_json([])[0])

    def test_modules_missing(self):
        self.assertFalse(rules.validate_points_json({"project": "P1"})[0])

    def test_modules_empty(self):
        self.assertFalse(rules.validate_points_json({"modules": []})[0])

    def test_missing_standard_module(self):
        """v2.1：缺任一标准模块 → 校验失败（9 模块框架强制全覆盖）。"""
        doc = _points9()
        doc["modules"] = [m for m in doc["modules"] if m["id"] != "pending"]
        ok, issues = rules.validate_points_json(doc)
        self.assertFalse(ok)
        self.assertTrue(any("pending" in i for i in issues))

    def test_module_missing_title_type(self):
        doc = _points9()
        doc["modules"][0] = {"id": "basic"}
        ok, issues = rules.validate_points_json(doc)
        self.assertFalse(ok)
        self.assertTrue(any("title" in i for i in issues))
        self.assertTrue(any("type" in i for i in issues))

    def test_duplicate_module_id(self):
        doc = _points9()
        doc["modules"].append({"id": "basic", "title": "重复", "type": "fields"})
        ok, issues = rules.validate_points_json(doc)
        self.assertFalse(ok)
        self.assertTrue(any("重复" in i for i in issues))

    def test_diffs_valid(self):
        """v2.5 裁决检查点：diffs 非空时必须带 verdicts 才通过。"""
        doc = _points9(diffs=[{"解析项": "履约保证金", "通道A": "不采用",
                               "通道B": "承诺递交履约担保", "差异类型": "语义冲突"}],
                       verdicts=[{"item": "履约保证金", "decision": "以招标原文为准，采用通道A",
                                  "date": "2026-10-07"}])
        self.assertEqual(rules.validate_points_json(doc), (True, []))

    def test_diffs_empty_list_ok(self):
        self.assertEqual(rules.validate_points_json(_points9(diffs=[])), (True, []))

    def test_diffs_require_verdicts_gate(self):
        """v2.5 裁决检查点：diffs 非空且 verdicts 缺失/为空 → 拒绝（机器强制，杜绝静默略过）。"""
        doc = _points9(diffs=[{"解析项": "履约保证金", "通道A": "不采用",
                               "通道B": "承诺递交履约担保", "差异类型": "语义冲突"}])
        ok, issues = rules.validate_points_json(doc)
        self.assertFalse(ok)
        self.assertTrue(any("裁决检查点" in i for i in issues))

    def test_diffs_require_verdicts_gate_empty_verdicts(self):
        """diffs 非空 + verdicts 为空数组 → 同样拒绝（空数组=无裁决记录）。"""
        doc = _points9(diffs=[{"解析项": "履约保证金", "通道A": "不采用",
                               "通道B": "承诺递交履约担保", "差异类型": "语义冲突"}],
                       verdicts=[])
        ok, issues = rules.validate_points_json(doc)
        self.assertFalse(ok)
        self.assertTrue(any("裁决检查点" in i for i in issues))

    def test_verdicts_without_diffs_ok(self):
        """diffs 为空 + verdicts 有记录（裁决后差异已移除）→ 通过（golden 语义）。"""
        doc = _points9(diffs=[], verdicts=[{"item": "双通道差异第 1 项", "decision": "实质一致不列示"}])
        self.assertEqual(rules.validate_points_json(doc), (True, []))

    def test_diffs_not_list(self):
        doc = _points9(diffs="x")
        self.assertFalse(rules.validate_points_json(doc)[0])

    def test_diffs_item_missing_parse_item(self):
        doc = _points9(diffs=[{"通道A": "1"}])
        ok, issues = rules.validate_points_json(doc)
        self.assertFalse(ok)
        self.assertTrue(any("解析项" in i for i in issues))

    def test_diffs_bad_type(self):
        doc = _points9(diffs=[{"解析项": "保证金", "差异类型": "其他"}])
        ok, issues = rules.validate_points_json(doc)
        self.assertFalse(ok)
        self.assertTrue(any("差异类型" in i for i in issues))


class TestValidateListJson(unittest.TestCase):
    def _item(self, **kw):
        base = {"category": "资质", "subtype": "企业资质证书", "keywords": ["甲级"],
                "purpose": "资格要求", "required": True, "source": "3.1"}
        base.update(kw)
        return base

    def test_valid(self):
        doc = {"project": "P1", "items": [self._item()]}
        self.assertEqual(rules.validate_list_json(doc), (True, []))

    def test_items_missing_or_empty(self):
        self.assertFalse(rules.validate_list_json({"project": "P1"})[0])
        self.assertFalse(rules.validate_list_json({"items": []})[0])

    def test_item_missing_category(self):
        it = self._item()
        it.pop("category")
        ok, issues = rules.validate_list_json({"items": [it]})
        self.assertFalse(ok)
        self.assertTrue(any("category" in i for i in issues))

    def test_item_required_not_bool(self):
        it = self._item(required="yes")
        ok, issues = rules.validate_list_json({"items": [it]})
        self.assertFalse(ok)
        self.assertTrue(any("required" in i for i in issues))

    def test_item_missing_purpose_source(self):
        it = self._item()
        it.pop("purpose")
        it.pop("source")
        ok, issues = rules.validate_list_json({"items": [it]})
        self.assertFalse(ok)
        self.assertEqual(len(issues), 2)

    def test_item_not_object(self):
        ok, issues = rules.validate_list_json({"items": ["x"]})
        self.assertFalse(ok)


# --------------------------------------------------------------------------
# 规范命名
# --------------------------------------------------------------------------
class TestNaming(unittest.TestCase):
    def test_original_name(self):
        self.assertEqual(rules.original_name("招标文件"), "原文_招标文件.txt")

    def test_bases(self):
        self.assertEqual(rules.points_base("P1"), "投标要点_P1")
        self.assertEqual(rules.list_base("P1"), "素材清单_P1")
        self.assertEqual(rules.check_base("P1"), "素材对照_P1")


# --------------------------------------------------------------------------
# 素材对照三态
# --------------------------------------------------------------------------
class TestClassifyStatus(unittest.TestCase):
    def test_have(self):
        self.assertEqual(rules.classify_status(2, True), "已有")
        self.assertEqual(rules.classify_status(1, False), "已有")

    def test_missing_required(self):
        self.assertEqual(rules.classify_status(0, True), "缺失·必须")

    def test_missing_bonus(self):
        self.assertEqual(rules.classify_status(0, False), "缺失·加分")


class TestBuildCheckRows(unittest.TestCase):
    def _hit(self, n, paths=()):
        return {"hits": n, "paths": list(paths)}

    def test_status_and_fields(self):
        items = [
            {"category": "资质", "subtype": "企业资质证书", "keywords": ["甲级"],
             "purpose": "资格", "required": True, "source": "3.1"},
            {"category": "业绩", "subtype": "监理合同", "keywords": ["类似业绩"],
             "purpose": "评分", "required": False, "source": "评标办法"},
        ]
        rows = rules.build_check_rows(items, lambda it: self._hit(1, ["资质/甲级.jpg"]) if it["category"] == "资质" else self._hit(0))
        self.assertEqual(rows[0]["status"], "已有")
        self.assertEqual(rows[0]["hits"], 1)
        self.assertEqual(rows[0]["paths"], ["资质/甲级.jpg"])
        self.assertEqual(rows[1]["status"], "缺失·加分")
        self.assertTrue(rows[1]["required"] is False)

    def test_empty_items(self):
        self.assertEqual(rules.build_check_rows([], lambda it: self._hit(0)), [])


class TestSummarize(unittest.TestCase):
    def test_counts_and_redlines(self):
        rows = [
            {"category": "资质", "subtype": "甲", "keywords": [], "purpose": "", "required": True,
             "source": "", "status": "已有", "hits": 1, "paths": [], "suggestion": ""},
            {"category": "业绩", "subtype": "乙", "keywords": [], "purpose": "", "required": True,
             "source": "", "status": "缺失·必须", "hits": 0, "paths": [], "suggestion": ""},
            {"category": "人员", "subtype": "丙", "keywords": [], "purpose": "", "required": False,
             "source": "", "status": "缺失·加分", "hits": 0, "paths": [], "suggestion": ""},
        ]
        s = rules.summarize(rows)
        self.assertEqual(s["total"], 3)
        self.assertEqual(s["have"], 1)
        self.assertEqual(s["missing_required"], 1)
        self.assertEqual(s["missing_bonus"], 1)
        self.assertIn("业绩/乙", s["redlines"])


# --------------------------------------------------------------------------
# 渲染
# --------------------------------------------------------------------------
class TestRender(unittest.TestCase):
    def test_render_points_text(self):
        doc = {"project": "P1", "modules": [
            {"id": "m1", "title": "项目概况", "type": "fields",
             "fields": {"project_name": {"value": "XX项目", "evidence": "第1页"}}},
            {"id": "m4", "title": "评标办法与评分标准", "type": "mixed",
             "method": {"value": "综合评估法"},
             "score_items": [{"item": "监理大纲", "weight": "30", "unit": "分", "evidence": "第8页"}]},
            {"id": "m5", "title": "废标红线", "type": "items",
             "items": [{"type": "资格性", "rule": "未提供营业执照", "evidence": "第9页"}]},
        ]}
        t = rules.render_points_text(doc)
        self.assertIn("XX项目", t)
        self.assertIn("综合评估法", t)
        self.assertIn("未提供营业执照", t)

    def test_render_points_text_bad(self):
        self.assertIn("结构不完整", rules.render_points_text({"project": "P1"}))

    def test_render_check_text_redline(self):
        rows = [
            {"category": "业绩", "subtype": "监理合同", "keywords": [], "purpose": "评分", "required": True,
             "source": "3.3", "status": "缺失·必须", "hits": 0, "paths": [], "suggestion": ""},
        ]
        s = rules.summarize(rows)
        t = rules.render_check_text(rows, s, "P1")
        self.assertIn("废标风险", t)
        self.assertIn("业绩/监理合同", t)


# --------------------------------------------------------------------------
# v2.1 响应文件格式章节定位（find_fmt_span / extract_fmt）
# --------------------------------------------------------------------------
class TestFindFmtSpan(unittest.TestCase):
    LINES = [
        "第一章 招标公告",
        "项目编号：HXTD-2026-018",
        "第六章 评标办法",
        "第七章 响应文件格式",
        "一、投标函",
        "（一）投标函格式",
        "法定代表人：",
        "第八章 评标标准",
        "",
        "1",
    ]

    def test_auto_chapter_span(self):
        s, e = rules.find_fmt_span(self.LINES)
        self.assertEqual(s, 4)      # 第七章
        self.assertEqual(e, 8)      # 第八章（不含）

    def test_explicit_span(self):
        s, e = rules.find_fmt_span(self.LINES, start=4, end=7)
        self.assertEqual((s, e), (4, 7))

    def test_no_next_chapter_cleans_tail(self):
        lines = self.LINES[:7] + ["", "", "1"]     # 无后续章 → 文件尾清理
        s, e = rules.find_fmt_span(lines)
        self.assertEqual((s, e), (4, 8))           # 清理尾部空行 + 页码

    def test_extract_fmt_text(self):
        text, s, e = rules.extract_fmt(self.LINES)
        self.assertEqual(s, 4)
        self.assertEqual(e, 8)
        self.assertIn("第七章 响应文件格式", text)
        self.assertIn("法定代表人：", text)
        self.assertNotIn("第八章", text)

    def test_standalone_title(self):
        lines = ["第一章 招标公告", "响应文件格式", "一、投标函", "二、承诺函"]
        s, e = rules.find_fmt_span(lines)
        self.assertEqual(s, 2)
        self.assertEqual(e, 5)      # 内容到最后一行（1 基 4 含）→ end 不含 = 5

    def test_toc_entry_ignored(self):
        """目录条目（带点线页码）在前，正文章节标题在后 → 取正文（最后一个匹配）。"""
        lines = ["第一章 招标公告", "目录", "第七章 响应文件格式.............42",
                 "第七章 响应文件格式", "一、投标函", "二、承诺函", "第八章 评标标准"]
        s, e = rules.find_fmt_span(lines)
        self.assertEqual(s, 4)
        self.assertEqual(e, 7)

    def test_not_found_raises(self):
        with self.assertRaises(ValueError):
            rules.find_fmt_span(["第一章 招标公告", "一、投标函"])

    def test_invalid_span_raises(self):
        with self.assertRaises(ValueError):
            rules.find_fmt_span(self.LINES, start=9, end=3)


# --------------------------------------------------------------------------
# v2.1 双通道字段比对（compare_dual）
# --------------------------------------------------------------------------
class TestDualCompare(unittest.TestCase):
    def test_norm_value(self):
        self.assertEqual(rules.norm_value(" HXTD-2026-018 "), "hxtd-2026-018")
        self.assertEqual(rules.norm_value("４８．８６万元"), "４８．８６万元")  # 全角数字不转换（保真）
        self.assertEqual(rules.norm_value(None), "")

    def test_consistent_not_diff(self):
        fields = {"project_no": {"label": "项目编号", "value": "HXTD-2026-018"}}
        doc = {"modules": [{"id": "basic", "title": "t", "type": "fields",
                            "fields": {"项目编号": {"value": "HXTD-2026-018"}}}]}
        self.assertEqual(rules.compare_dual(fields, doc), [])

    def test_fact_value_diff(self):
        fields = {"budget": {"label": "最高投标限价", "value": "48.86万元"}}
        doc = {"modules": [{"id": "basic", "title": "t", "type": "fields",
                            "fields": {"最高投标限价": {"value": "50万元"}}}]}
        diffs = rules.compare_dual(fields, doc)
        self.assertEqual(len(diffs), 1)
        self.assertEqual(diffs[0]["差异类型"], "事实值不同")
        self.assertEqual(diffs[0]["解析项"], "最高投标限价")

    def test_existence_diff(self):
        fields = {"deposit": {"label": "投标保证金", "value": "无"}}
        doc = {"modules": [{"id": "basic", "title": "t", "type": "fields", "fields": {}}]}
        diffs = rules.compare_dual(fields, doc)
        self.assertEqual(len(diffs), 1)
        self.assertEqual(diffs[0]["差异类型"], "存在性差异")

    def test_multi_value_b_any_match(self):
        fields = {"staff_count": {"label": "人员数量", "value": ["总监理工程师1名"]}}
        doc = {"modules": [{"id": "staff", "title": "t", "type": "fields",
                            "fields": {"人员数量": {"value": "总监理工程师 1 名"}}}]}
        self.assertEqual(rules.compare_dual(fields, doc), [])

    def test_unit_suffix_not_diff(self):
        """单位后缀差异（48.86 vs 48.86万元）→ 数字归一化视为一致，不列差异。"""
        fields = {"budget": {"label": "最高投标限价", "value": "48.86"}}
        doc = {"modules": [{"id": "basic", "title": "t", "type": "fields",
                            "fields": {"最高投标限价": {"value": "48.86 万元"}}}]}
        self.assertEqual(rules.compare_dual(fields, doc), [])

    def test_number_diff_still_diff(self):
        fields = {"budget": {"label": "最高投标限价", "value": "48.86"}}
        doc = {"modules": [{"id": "basic", "title": "t", "type": "fields",
                            "fields": {"最高投标限价": {"value": "50万元"}}}]}
        diffs = rules.compare_dual(fields, doc)
        self.assertEqual(len(diffs), 1)
        self.assertEqual(diffs[0]["差异类型"], "事实值不同")

    def test_empty_fields_no_diff(self):
        self.assertEqual(rules.compare_dual({}, {"modules": []}), [])


# --------------------------------------------------------------------------
# v2.6 素材缺口收口（validate_gap_json / summarize_gap / render_gap_text）
# --------------------------------------------------------------------------
def _gap_item(gap_id="G01", item="拟派总监理工程师联系电话", gtype="text",
              source="投标要点·模块二·人员红线", status="待补充", value="", note=""):
    return {"gap_id": gap_id, "item": item, "type": gtype, "source": source,
            "status": status, "value": value, "note": note}


class TestValidateGapJson(unittest.TestCase):
    def test_valid_single(self):
        doc = {"project": "P1", "items": [_gap_item()]}
        ok, issues = rules.validate_gap_json(doc)
        self.assertTrue(ok, issues)

    def test_valid_mixed_status(self):
        doc = {"project": "P1", "items": [
            _gap_item("G01", status="已补充", value="13800000000"),
            _gap_item("G02", item="总监理工程师注册证扫描件", gtype="asset",
                      source="响应文件格式·拟派人员表", status="豁免", note="用户无此素材"),
        ]}
        ok, issues = rules.validate_gap_json(doc)
        self.assertTrue(ok, issues)

    def test_missing_gap_id(self):
        it = _gap_item()
        del it["gap_id"]
        ok, issues = rules.validate_gap_json({"items": [it]})
        self.assertFalse(ok)
        self.assertTrue(any("gap_id" in x for x in issues))

    def test_missing_item(self):
        it = _gap_item()
        del it["item"]
        ok, issues = rules.validate_gap_json({"items": [it]})
        self.assertFalse(ok)
        self.assertTrue(any("item" in x for x in issues))

    def test_bad_type(self):
        ok, issues = rules.validate_gap_json({"items": [_gap_item(gtype="file")]})
        self.assertFalse(ok)
        self.assertTrue(any("type" in x for x in issues))

    def test_bad_status(self):
        ok, issues = rules.validate_gap_json({"items": [_gap_item(status="已删除")]})
        self.assertFalse(ok)
        self.assertTrue(any("status" in x for x in issues))

    def test_missing_source(self):
        it = _gap_item()
        del it["source"]
        ok, issues = rules.validate_gap_json({"items": [it]})
        self.assertFalse(ok)
        self.assertTrue(any("source" in x for x in issues))

    def test_empty_items(self):
        ok, issues = rules.validate_gap_json({"items": []})
        self.assertFalse(ok)


class TestGapSummaryAndRender(unittest.TestCase):
    def test_summarize_mixed(self):
        items = [
            _gap_item("G01", status="已补充"),
            _gap_item("G02", status="豁免"),
            _gap_item("G03", status="待补充"),
        ]
        s = rules.summarize_gap(items)
        self.assertEqual(s, {"total": 3, "pending": 1, "done": 1, "waived": 1})

    def test_summarize_all_done(self):
        s = rules.summarize_gap([_gap_item(status="已补充"), _gap_item("G02", status="豁免")])
        self.assertEqual(s["pending"], 0)
        self.assertEqual(s["total"], 2)

    def test_render_gap_text(self):
        items = [_gap_item(status="已补充", value="13800000000")]
        text = rules.render_gap_text(items, "P1")
        self.assertIn("# 素材缺口清单", text)
        self.assertIn("G01", text)
        self.assertIn("已收内容：13800000000", text)
        self.assertIn("文字", text)


if __name__ == "__main__":
    unittest.main()
