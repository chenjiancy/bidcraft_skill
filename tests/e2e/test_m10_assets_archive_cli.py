# -*- coding: utf-8 -*-
"""M10 T22 端到端测试（L3）：assets-archive CLI 行为 ——
任务单无已归档素材任务 → 拒绝并提示先 apply --confirm；
--task 指定单任务生成申请单；无企业（--enterprise 不存在）报错；申请单写后回读。
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

ENT = "T22端到端企业"
PROJECT = "T22端到端项目"


class M10AssetsArchiveE2ETest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self._run("init-enterprise", "--name", ENT)
        self.proj = self.root / ENT / "项目级" / PROJECT
        self.sdir = self.proj / "模拟评标"
        self.sdir.mkdir(parents=True)

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

    def test_assets_archive_cli_behavior(self):
        # 1) 无任务单 → 拒绝
        code, _, err = self._run("assets-archive", "--project", PROJECT)
        self.assertNotEqual(code, 0)
        self.assertIn("任务单不存在", err)

        # 2) 任务单有已归档素材任务 → 生成申请单（写后回读）
        (self.sdir / ("失分补救任务单_%s.json" % PROJECT)).write_text(json.dumps(
            {"project": PROJECT, "tasks": [
                {"id": "R01", "类型": "素材补齐", "动作": "补荣誉", "标题": "先进示范表彰（2.0 分）",
                 "来源": "通道A-客观", "评分项": "先进示范表彰",
                 "涉及素材": {"category": "荣誉", "subtype": "先进示范优秀监理企业表彰证书"},
                 "完成状态": "已完成", "归档状态": "已归档"},
                {"id": "R02", "类型": "素材补齐", "动作": "补业绩", "标题": "未归档任务",
                 "来源": "通道A-客观", "评分项": "S",
                 "涉及素材": {"category": "业绩", "subtype": "S"}, "完成状态": "已完成"},
            ]}), encoding="utf-8")
        code, out, err = self._run("assets-archive", "--project", PROJECT)
        self.assertEqual(code, 0, "%s | %s" % (out, err))
        inbox = self.root / ENT / "企业级" / "素材库" / "收件箱"
        files = list(inbox.glob("补救入库申请_*.json"))
        self.assertEqual(len(files), 1)
        adoc = json.loads(files[0].read_text(encoding="utf-8"))
        self.assertEqual(adoc["project"], PROJECT)
        self.assertEqual(len(adoc["entries"]), 1)  # 仅 R01 已归档；R02 未归档排除
        self.assertEqual(adoc["entries"][0]["任务ID"], "R01")
        self.assertEqual(adoc["entries"][0]["状态"], "待入库")

        # 3) --task 指定未归档任务 → 拒绝
        code, _, err = self._run("assets-archive", "--project", PROJECT, "--task", "R02")
        self.assertNotEqual(code, 0)
        self.assertIn("未归档", err)

        # 4) 企业不存在 → 报错
        code, _, err = self._run("assets-archive", "--project", PROJECT)
        self.assertEqual(code, 0, err)
        code, _, err = self._run("assets-archive", "--project", PROJECT, "--enterprise", "不存在企业")
        self.assertNotEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
