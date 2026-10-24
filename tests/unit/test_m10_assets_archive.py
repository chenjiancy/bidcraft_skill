# -*- coding: utf-8 -*-
"""M10 T22 补救素材→企业素材库入库申请 纯逻辑单测：
_archived_entries（仅已归档+涉及素材非空过滤 / --task 指定 / 未归档排除）、
_M1_CATEGORY 类别映射、_to_md_assets 渲染（含已在库命中不崩）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scripts"))

from m10_remedy import archive  # noqa: E402


def _tdoc(tasks):
    return {"project": "P", "tasks": tasks}


def _task(tid, archived=True, mat={"category": "业绩", "subtype": "近年同类监理业绩"}):
    t = {"id": tid, "类型": "素材补齐", "动作": "补业绩", "标题": "T", "来源": "通道A-客观",
         "评分项": "S", "涉及素材": mat, "完成状态": "已完成"}
    if archived:
        t["归档状态"] = "已归档"
    return t


class ArchivedEntriesTest(unittest.TestCase):
    def test_only_archived_with_mat(self):
        doc = _tdoc([
            _task("R01"),
            _task("R02", archived=False),
            _task("R03", mat=None),
            {"id": "C01", "类型": "格式合规", "动作": "技术标检查整改", "标题": "T",
             "来源": "M7-技术标", "评分项": "S", "涉及素材": None, "归档状态": "已归档"},
        ])
        entries = archive._archived_entries(doc)
        self.assertEqual([e["任务ID"] for e in entries], ["R01"])
        self.assertEqual(entries[0]["类别"], "业绩")
        self.assertEqual(entries[0]["素材名"], "近年同类监理业绩")

    def test_task_filter(self):
        doc = _tdoc([_task("R01"), _task("R02", mat={"category": "荣誉", "subtype": "表彰证书"})])
        entries = archive._archived_entries(doc, task_id="R02")
        self.assertEqual([e["任务ID"] for e in entries], ["R02"])
        self.assertEqual(entries[0]["类别"], "荣誉")

    def test_category_mapping(self):
        self.assertEqual(archive._M1_CATEGORY["业绩"], "业绩")
        self.assertEqual(archive._M1_CATEGORY["人员"], "人员")
        self.assertEqual(archive._M1_CATEGORY["荣誉"], "荣誉")
        self.assertEqual(archive._M1_CATEGORY["体系认证"], "资质")
        self.assertEqual(archive._M1_CATEGORY.get("其他", "未分类"), "未分类")


class AssetsMdTest(unittest.TestCase):
    def test_to_md_assets_with_hits(self):
        doc = {"project": "P", "enterprise": "E",
               "生成依据": "T22", "生成时间": "2026-10-24 10:00",
               "summary": {"申请条数": 2, "待入库": 1, "已在库（可复用）": 1},
               "entries": [
                   {"任务ID": "R01", "动作": "补业绩", "类别": "业绩", "素材名": "近年同类监理业绩",
                    "企业类别": "业绩", "状态": "已在库（可复用，跳过入库）", "台账命中": ["业绩/监理合同_近年同类监理业绩.pdf"]},
                   {"任务ID": "R02", "动作": "补荣誉", "类别": "荣誉", "素材名": "先进示范表彰",
                    "企业类别": "荣誉", "状态": "待入库", "台账命中": []},
               ]}
        md = archive._to_md_assets(doc)
        self.assertIn("## 入库申请条目", md)
        self.assertIn("R01", md)
        self.assertIn("已在库", md)
        self.assertIn("open-inbox", md)


if __name__ == "__main__":
    unittest.main()
