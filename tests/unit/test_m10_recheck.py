# -*- coding: utf-8 -*-
"""M10 T18 补救→重检闭环单测：mark_done（勾选完成） + recheck_tasks（已勾选任务复核：
M7 检查快照对比通过/未通过/新增问题/无法复核、R 失分任务 gap 对比补回/未改善、新问题自动生成）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scripts"))

from m10_remedy import remedy          # noqa: E402


def _doc(tasks):
    return {"project": "P", "生成依据": "x", "tasks": tasks,
            "summary": {"任务总数": len(tasks), "可追分合计": 0}}


def _c_task(task_id="C01", cid="tech_blank_pages", name="空白页检查", issues=("a", "b"), done=False):
    t = {"id": task_id, "类型": "格式合规", "动作": "技术标检查整改", "标题": "%s（%d 处问题）" % (name, len(issues)),
         "来源": "M7-技术标", "评分项": name, "当前状态": issues[0], "目标状态": "复核通过",
         "动作步骤": ["修复：%s" % x for x in issues], "涉及素材": None, "优先级": "高",
         "预期加分": None, "验证方式": "重跑 check-rule", "检查快照": {"id": cid, "name": name, "issues": list(issues)}}
    if done:
        t["完成状态"] = "已完成"
    return t


def _r_task(task_id="R01", item="监理大纲（50分）", gap=8.0, done=False):
    t = {"id": task_id, "类型": "内容补强", "动作": "主观分补强", "标题": item, "来源": "通道B-主观",
         "评分项": item, "当前状态": "阐述略欠", "目标状态": "补强后满分", "动作步骤": ["补强"], "涉及素材": None,
         "优先级": "高", "预期加分": gap, "验证方式": "重跑 eval-report"}
    if done:
        t["完成状态"] = "已完成"
    return t


def _check(checks):
    return {"kind": "tech", "tag": "技术标", "检查": checks}


class MarkDoneTest(unittest.TestCase):
    def test_marks_completed(self):
        doc = _doc([_c_task()])
        r = remedy.mark_done(doc, "C01", "已删空段")
        self.assertTrue(r["found"])
        self.assertEqual(doc["tasks"][0]["完成状态"], "已完成")
        self.assertEqual(doc["tasks"][0]["完成备注"], "已删空段")
        self.assertIn("完成时间", doc["tasks"][0])

    def test_default_note(self):
        doc = _doc([_c_task()])
        remedy.mark_done(doc, "C01")
        self.assertEqual(doc["tasks"][0]["完成备注"], "人工确认完成")

    def test_missing_id(self):
        doc = _doc([_c_task()])
        r = remedy.mark_done(doc, "R99")
        self.assertFalse(r["found"])


class RecheckM7Test(unittest.TestCase):
    def test_passed_when_check_ok(self):
        doc = _doc([_c_task(done=True)])
        rp = remedy.recheck_tasks(doc, check_new=_check([
            {"id": "tech_blank_pages", "name": "空白页检查", "ok": True, "issues": []}]))
        s = rp["summary"]
        self.assertEqual(s["已勾选任务"], 1)
        self.assertEqual(s["验证通过"], 1)
        self.assertEqual(rp["results"][0]["验证"], "通过")
        self.assertIn("全部消除", rp["results"][0]["证据"])

    def test_failed_with_still_and_added(self):
        doc = _doc([_c_task(done=True)])
        rp = remedy.recheck_tasks(doc, check_new=_check([
            {"id": "tech_blank_pages", "name": "空白页检查", "ok": False, "issues": ["a", "c"]}]))
        self.assertEqual(rp["results"][0]["验证"], "未通过")
        self.assertIn("仍存在 1 处", rp["results"][0]["证据"])
        self.assertIn("新增 1 处", rp["results"][0]["证据"])

    def test_failed_when_issues_unchanged(self):
        doc = _doc([_c_task(done=True)])
        rp = remedy.recheck_tasks(doc, check_new=_check([
            {"id": "tech_blank_pages", "name": "空白页检查", "ok": False, "issues": ["a", "b"]}]))
        self.assertEqual(rp["results"][0]["验证"], "未通过")
        self.assertNotIn("新增", rp["results"][0]["证据"])

    def test_unable_when_check_item_missing(self):
        doc = _doc([_c_task(done=True)])
        rp = remedy.recheck_tasks(doc, check_new=_check([]))
        self.assertEqual(rp["results"][0]["验证"], "无法复核")

    def test_new_issue_tasks_appended(self):
        doc = _doc([_c_task(done=True)])
        rp = remedy.recheck_tasks(doc, check_new=_check([
            {"id": "tech_blank_pages", "name": "空白页检查", "ok": True, "issues": []},
            {"id": "tech_figure_placement", "name": "图表位置合规", "ok": False, "issues": ["图在正文中段"]}]))
        self.assertEqual(len(rp["new_tasks"]), 1)
        self.assertEqual(rp["new_tasks"][0]["评分项"], "图表位置合规")
        self.assertEqual(rp["new_tasks"][0]["来源"], "M7-技术标")
        self.assertEqual(rp["summary"]["新增问题"], 1)

    def test_no_done_tasks(self):
        doc = _doc([_c_task(done=False)])
        rp = remedy.recheck_tasks(doc, check_new=_check([]))
        self.assertEqual(rp["summary"]["已勾选任务"], 0)


class RecheckScoreTest(unittest.TestCase):
    def test_gap_recovered(self):
        doc = _doc([_r_task(gap=8.0, done=True)])
        eval_new = {"summary": {"issues": [{"item": "监理大纲（50分）", "kind": "outline", "gap": 3.0}]}}
        rp = remedy.recheck_tasks(doc, check_new=None, eval_new=eval_new)
        self.assertEqual(rp["results"][0]["验证"], "通过")
        self.assertIn("补回 5.0 分", rp["results"][0]["证据"])

    def test_gap_unchanged(self):
        doc = _doc([_r_task(gap=8.0, done=True)])
        eval_new = {"summary": {"issues": [{"item": "监理大纲（50分）", "kind": "outline", "gap": 8.0}]}}
        rp = remedy.recheck_tasks(doc, check_new=None, eval_new=eval_new)
        self.assertEqual(rp["results"][0]["验证"], "未通过")
        self.assertIn("未见改善", rp["results"][0]["证据"])

    def test_no_eval_manual_review(self):
        doc = _doc([_r_task(gap=8.0, done=True)])
        rp = remedy.recheck_tasks(doc, check_new=None, eval_new=None)
        self.assertEqual(rp["results"][0]["验证"], "需人工复核")


if __name__ == "__main__":
    unittest.main()
