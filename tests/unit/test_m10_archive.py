# -*- coding: utf-8 -*-
"""M10 T21 补救→M5 归档联动 纯逻辑单测：
gen_archive_entries（已完成+素材类过滤/known 去重/无涉及素材跳过）与
apply_archive（items 结构落点、fill-tpl 分键落点 performance/personnel/honors/iso_certificates、
同类别去重跳过、来源/归档时间标记）；另补 recheck to_md 含 new_tasks 分支不崩（T18 潜伏修复覆盖）。
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scripts"))

from m10_remedy import remedy   # noqa: E402
from m10_remedy import recheck  # noqa: E402


def _task_doc(tasks):
    return {"project": "P", "tasks": tasks}


def _done(tid, typ="素材补齐", act="补业绩", mat=None):
    t = {"id": tid, "类型": typ, "动作": act, "标题": "%s标题" % act, "来源": "通道A-客观",
         "评分项": "%s评分项" % act, "完成状态": "已完成"}
    if mat is not None:
        t["涉及素材"] = mat
    return t


class GenArchiveEntriesTest(unittest.TestCase):
    def test_filters_done_archive_types_only(self):
        doc = _task_doc([
            _done("R01", mat={"category": "业绩", "subtype": "近年同类监理业绩"}),
            _done("R02", typ="证据核验", act="核验体系证书有效期",
                  mat={"category": "体系认证", "subtype": "ISO三体系认证证书"}),
            _done("R03", typ="内容补强", mat=None),
            _done("R04", typ="格式合规", mat=None),
            dict(id="C01", 类型="格式合规", 动作="技术标检查整改", 标题="T",
                 来源="M7-技术标", 评分项="S", 涉及素材=None, 完成状态="进行中"),
        ])
        entries = remedy.gen_archive_entries(doc)
        self.assertEqual([e["任务ID"] for e in entries], ["R01", "R02"])
        self.assertEqual(entries[0]["类别"], "业绩")
        self.assertEqual(entries[1]["类别"], "体系认证")

    def test_known_dedup_and_missing_mat(self):
        doc = _task_doc([
            _done("R01", mat={"category": "荣誉", "subtype": "先进示范优秀监理企业表彰证书"}),
            _done("R02", mat={"category": "业绩", "subtype": "近年同类监理业绩"}),
            _done("R03", typ="素材补齐", act="补总监职称", mat=None),
        ])
        entries = remedy.gen_archive_entries(doc, known_task_ids=("R01",))
        self.assertEqual([e["任务ID"] for e in entries], ["R02"])

    def test_target_key_mapping(self):
        self.assertEqual(remedy._archive_target_key("业绩"), "performance")
        self.assertEqual(remedy._archive_target_key("人员"), "personnel")
        self.assertEqual(remedy._archive_target_key("荣誉"), "honors")
        self.assertEqual(remedy._archive_target_key("体系认证"), "iso_certificates")
        self.assertEqual(remedy._archive_target_key("其他"), "items")


class ApplyArchiveTest(unittest.TestCase):
    def test_items_structure_append(self):
        mat = {"project": "P", "items": [{"category": "业绩", "subtype": "旧业绩", "purpose": "x", "path": "x.pdf"}]}
        e = {"任务ID": "R01", "类别": "业绩", "素材名": "近年同类监理业绩",
             "建议落点": remedy._archive_target_key("业绩")}
        mat2, applied, skipped = remedy.apply_archive(mat, [e])
        self.assertEqual(len(applied), 1)
        self.assertEqual(skipped, [])
        items = mat2["items"]
        self.assertEqual(len(items), 2)
        self.assertEqual(items[1]["category"], "业绩")
        self.assertEqual(items[1]["subtype"], "近年同类监理业绩")
        self.assertTrue(items[1]["来源"].startswith("M10补救任务-R01"))
        self.assertIn("归档时间", items[1])

    def test_duplicate_skipped(self):
        mat = {"project": "P", "performance": [{"name": "近年同类监理业绩", "paths": ["a.pdf"]}]}
        e = {"任务ID": "R01", "类别": "业绩", "素材名": "近年同类监理业绩",
             "建议落点": "performance"}
        _, applied, skipped = remedy.apply_archive(mat, [e])
        self.assertEqual(applied, [])
        self.assertEqual(len(skipped), 1)
        self.assertIn("已存在", skipped[0]["结果"])

    def test_fulldict_targets(self):
        mat = {"project": "P", "personnel": [], "iso_certificates": [],
               "honors": [], "performance": []}
        entries = [
            {"任务ID": "R1", "类别": "业绩", "素材名": "业绩A", "建议落点": "performance"},
            {"任务ID": "R2", "类别": "人员", "素材名": "总监职称证书", "建议落点": "personnel"},
            {"任务ID": "R3", "类别": "荣誉", "素材名": "先进示范优秀监理企业表彰证书", "建议落点": "honors"},
            {"任务ID": "R4", "类别": "体系认证", "素材名": "ISO三体系认证证书", "建议落点": "iso_certificates"},
        ]
        mat2, applied, _ = remedy.apply_archive(mat, entries)
        self.assertEqual(len(applied), 4)
        self.assertEqual(mat2["performance"][0]["name"], "业绩A")
        self.assertEqual(mat2["personnel"][0]["role"], "项目总监")
        self.assertEqual(mat2["personnel"][0]["职称"], [])
        self.assertEqual(mat2["honors"][0]["name"], "先进示范优秀监理企业表彰证书")
        self.assertEqual(mat2["iso_certificates"][0]["name"], "ISO三体系认证证书")
        for it in (mat2["performance"][0], mat2["personnel"][0],
                   mat2["honors"][0], mat2["iso_certificates"][0]):
            self.assertTrue(it["来源"].startswith("M10补救任务-"))

    def test_unknown_category_falls_to_items(self):
        mat = {"project": "P", "items": []}
        e = {"任务ID": "R1", "类别": "其他", "素材名": "某素材", "建议落点": "items"}
        mat2, applied, _ = remedy.apply_archive(mat, [e])
        self.assertEqual(len(applied), 1)
        self.assertEqual(mat2["items"][0]["target"], "items")
        self.assertEqual(mat2["items"][0]["path"], "待归档（人工补充扫描件路径）")


class RecheckMdNewTasksCoverTest(unittest.TestCase):
    def test_to_md_with_new_tasks_ok(self):
        """T18 潜伏修复：recheck.to_md 含 new_tasks 分支不得抛 append 双参数 TypeError。"""
        out = {"results": [{"任务ID": "R01", "验证": "通过", "证据": "新检查全部 ok"}],
               "new_tasks": [{"id": "R05", "类型": "素材补齐", "动作": "补业绩",
                              "标题": "新发现问题（2.0 分）", "优先级": "中",
                              "预期加分": 2.0, "来源": "新检查"}],
               "summary": {"已勾选任务": 1, "验证通过": 1, "未通过": 0, "需人工复核": 0, "新增问题": 1},
               "重检时间": "2026-10-24 10:00", "结论": "部分通过"}
        md = recheck.to_md(out)
        self.assertIn("## 新增问题任务", md)
        self.assertIn("R05", md)


if __name__ == "__main__":
    unittest.main()
