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
# 产物 JSON 最小结构校验
# --------------------------------------------------------------------------
class TestValidatePointsJson(unittest.TestCase):
    def test_valid(self):
        doc = {"project": "P1", "modules": [{"id": "m1", "title": "项目概况", "type": "fields"}]}
        self.assertEqual(rules.validate_points_json(doc), (True, []))

    def test_top_not_dict(self):
        self.assertFalse(rules.validate_points_json([])[0])

    def test_modules_missing(self):
        self.assertFalse(rules.validate_points_json({"project": "P1"})[0])

    def test_modules_empty(self):
        self.assertFalse(rules.validate_points_json({"modules": []})[0])


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


if __name__ == "__main__":
    unittest.main()
