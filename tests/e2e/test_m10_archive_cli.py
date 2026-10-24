# -*- coding: utf-8 -*-
"""M10 T21 端到端测试（L3）：remedy-archive CLI 行为 ——
生成申请单（筛选已完成素材类任务、排除未完成/非素材类）；
--apply 无 --confirm 拒绝且零写入；--apply --confirm 应用：
旧 items 结构素材清单 → items 落点；重复应用去重跳过；归档记录 json 写后回读。
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "..", "scripts"))

import bidcraft  # noqa: E402

PROJECT = "T21端到端项目"
ENT = "T21端到端企业"


class M10ArchiveE2ETest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self._run("init-enterprise", "--name", ENT)
        self.proj = self.root / ENT / "项目级" / PROJECT
        self.tdir = self.proj / "招标解析"
        self.tdir.mkdir(parents=True)
        (self.tdir / ("素材清单_%s.json" % PROJECT)).write_text(
            json.dumps({"project": PROJECT,
                        "items": [{"category": "业绩", "subtype": "近年同类监理业绩",
                                   "purpose": "已有", "path": "x.pdf"}]},
                       ensure_ascii=False), encoding="utf-8")
        self.sdir = self.proj / "模拟评标"
        self.sdir.mkdir(parents=True)
        (self.sdir / ("失分补救任务单_%s.json" % PROJECT)).write_text(json.dumps(
            {"project": PROJECT, "tasks": [
                {"id": "R01", "类型": "素材补齐", "动作": "补业绩", "标题": "近年同类监理业绩（3.0 分）",
                 "来源": "通道A-客观", "评分项": "近年同类监理业绩",
                 "涉及素材": {"category": "业绩", "subtype": "近年同类监理业绩"}, "完成状态": "已完成"},
                {"id": "R02", "类型": "素材补齐", "动作": "补荣誉", "标题": "先进示范表彰（2.0 分）",
                 "来源": "通道A-客观", "评分项": "先进示范表彰",
                 "涉及素材": {"category": "荣誉", "subtype": "先进示范优秀监理企业表彰证书"}, "完成状态": "已完成"},
                {"id": "R03", "类型": "素材补齐", "动作": "补业绩", "标题": "未完成任务",
                 "来源": "通道A-客观", "评分项": "S", "涉及素材": {"category": "业绩", "subtype": "S"},
                 "完成状态": "进行中"},
                {"id": "C01", "类型": "格式合规", "动作": "技术标检查整改", "标题": "T",
                 "来源": "M7-技术标", "评分项": "S", "涉及素材": None, "完成状态": "已完成"},
            ]}, ensure_ascii=False), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, *argv):
        import io as _io
        from contextlib import redirect_stdout, redirect_stderr
        out, err, code = _io.StringIO(), _io.StringIO(), 0
        with redirect_stdout(out), redirect_stderr(err):
            try:
                bidcraft.main(["--root", str(self.root), "--enterprise", ENT] + list(argv))
            except SystemExit as e:
                code = e.code or 0
        return code, out.getvalue(), err.getvalue()

    def test_archive_cli_behavior(self):
        # 1) 生成申请单：只含 已完成+素材类（R01/R02；R03 未完成、C01 非素材类 排除）
        code, out, err = self._run("remedy-archive", "--project", PROJECT)
        self.assertEqual(code, 0, err)
        ap = self.sdir / ("归档申请_%s.json" % PROJECT)
        adoc = json.loads(ap.read_text(encoding="utf-8"))
        self.assertEqual({e["任务ID"] for e in adoc["entries"]}, {"R01", "R02"})
        # --task 单条：已收录任务不重复生成（去重 → 拒绝）
        code, _, err = self._run("remedy-archive", "--project", PROJECT, "--task", "R02")
        self.assertNotEqual(code, 0)
        self.assertIn("无符合归档条件", err)
        adoc = json.loads(ap.read_text(encoding="utf-8"))
        self.assertEqual(len(adoc["entries"]), 2)  # R01 + R02，无重复

        # 2) 无 --confirm → 拒绝，素材清单零写入
        code, _, err = self._run("remedy-archive", "--project", PROJECT, "--apply")
        self.assertNotEqual(code, 0)
        self.assertIn("--confirm", err)
        mdoc = json.loads((self.tdir / ("素材清单_%s.json" % PROJECT)).read_text(encoding="utf-8"))
        self.assertEqual(len(mdoc["items"]), 1)

        # 3) --apply --confirm：items 结构落点 + 去重（R01 已有同类业绩 → skipped；R02 写入）
        code, out, err = self._run("remedy-archive", "--project", PROJECT, "--apply", "--confirm")
        self.assertEqual(code, 0, "%s | %s" % (out, err))
        mdoc = json.loads((self.tdir / ("素材清单_%s.json" % PROJECT)).read_text(encoding="utf-8"))
        self.assertEqual(len(mdoc["items"]), 2)
        added = [it for it in mdoc["items"] if it.get("来源", "").startswith("M10补救任务-R02")]
        self.assertEqual(len(added), 1)
        self.assertEqual(added[0]["category"], "荣誉")
        self.assertEqual(added[0]["subtype"], "先进示范优秀监理企业表彰证书")
        # 归档记录写后回读
        rec = json.loads((self.sdir / ("归档记录_%s.json" % PROJECT)).read_text(encoding="utf-8"))
        self.assertEqual(rec["project"], PROJECT)
        self.assertEqual(len(rec["applied"]), 1)
        self.assertEqual(len(rec["skipped"]), 1)
        self.assertIn("已存在", rec["skipped"][0]["结果"])
        # 任务单归档标记
        doc = json.loads((self.sdir / ("失分补救任务单_%s.json" % PROJECT)).read_text(encoding="utf-8"))
        r02 = next(t for t in doc["tasks"] if t["id"] == "R02")
        self.assertEqual(r02["归档状态"], "已归档")

        # 4) 重复应用 → 全部已应用拒绝
        code, _, err = self._run("remedy-archive", "--project", PROJECT, "--apply", "--confirm")
        self.assertNotEqual(code, 0)
        self.assertIn("已全部应用", err)


if __name__ == "__main__":
    unittest.main()
