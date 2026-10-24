# -*- coding: utf-8 -*-
"""integration：AI 配图全链路（tender-parse → img-plan → img-save → img-status）。"""

import base64
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PY = sys.executable
CLI = REPO / "scripts" / "bidcraft.py"

TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")

POINTS = {
    "project": "配图集成项目",
    "modules": [
        {"id": "basic", "title": "项目基本信息", "type": "fields", "items": []},
        {"id": "qualification", "title": "资格条件", "type": "items",
         "items": [{"name": "资质等级", "value": "甲级", "source": "P1"}]},
        {"id": "staff", "title": "人员配备", "type": "fields", "items": []},
        {"id": "project_overview", "title": "项目概况与监理工作内容", "type": "fields", "items": []},
        {"id": "scoring", "title": "评分办法", "type": "mixed", "items": []},
        {"id": "pricing", "title": "报价要求", "type": "fields", "items": []},
        {"id": "submission", "title": "响应文件编制与递交", "type": "fields", "items": []},
        {"id": "reject", "title": "废标红线", "type": "items", "items": []},
        {"id": "pending", "title": "待确认项", "type": "items", "items": []},
    ],
    "diffs": [],
}

LIST = {
    "project": "配图集成项目",
    "items": [
        {"category": "资质", "name": "营业执照", "required": True,
         "purpose": "资格审查", "source": "P1"},
        {"category": "业绩", "name": "监理业绩", "required": True,
         "purpose": "评分", "source": "P1"},
    ],
}


class ImgPipelineIntegration(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = str(Path(self._tmp.name))
        self.proj = "配图集成项目"

    def tearDown(self):
        self._tmp.cleanup()

    def run_cli(self, *args, expect=0):
        r = subprocess.run(
            [PY, "-X", "utf8", str(CLI), *args],
            capture_output=True, text=True, encoding="utf-8",
            env={"BIDCRAFT_LIB_ROOT": self.root, "PATH": ""},
        )
        if expect is not None:
            self.assertEqual(r.returncode, expect, "CLI %s 失败：%s" % (args[0], r.stderr[-500:]))
        return r

    def test_full_pipeline(self):
        # 1) 企业 + 项目目录
        self.run_cli("init-enterprise", "--name", "配图集成企业")
        self.run_cli("tender-init", "--project", self.proj)

        # 2) 落盘投标要点 + 素材清单（tender-parse 校验）
        base = self._tmp.name
        p_md = str(Path(base) / "points.md")
        p_json = str(Path(base) / "points.json")
        l_md = str(Path(base) / "list.md")
        l_json = str(Path(base) / "list.json")
        Path(p_md).write_text("# 投标要点\n", encoding="utf-8")
        Path(p_json).write_text(json.dumps(POINTS, ensure_ascii=False), encoding="utf-8")
        Path(l_md).write_text("# 素材清单\n", encoding="utf-8")
        Path(l_json).write_text(json.dumps(LIST, ensure_ascii=False), encoding="utf-8")
        self.run_cli("tender-parse", "--project", self.proj,
                     "--points-md", p_md, "--points-json", p_json,
                     "--list-md", l_md, "--list-json", l_json)

        # 3) img-plan：生成 4 项配图清单
        r = self.run_cli("img-plan", "--project", self.proj)
        self.assertIn("新增 4 项", r.stdout)
        plan_json = Path(self.root) / "配图集成企业" / "项目级" / self.proj / "配图" / ("配图清单_%s.json" % self.proj)
        self.assertTrue(plan_json.exists())
        doc = json.loads(plan_json.read_text(encoding="utf-8"))
        self.assertEqual(len(doc["items"]), 4)

        # 4) img-save：落盘 1 张并回填
        img = Path(base) / "t.png"
        img.write_bytes(TINY_PNG)
        r = self.run_cli("img-save", "--project", self.proj,
                         "--id", "img_001", "--file", str(img), "--source", "CodeBuddy")
        self.assertIn("配图已落盘", r.stdout)
        doc = json.loads(plan_json.read_text(encoding="utf-8"))
        item = next(it for it in doc["items"] if it["id"] == "img_001")
        self.assertEqual(item["status"], "saved")
        self.assertEqual(item["source"], "CodeBuddy")
        self.assertTrue((Path(self.root) / "配图集成企业" / "项目级" / self.proj / "配图" / "img_001.png").exists())

        # 5) img-status --json：saved 1 / pending 3
        r = self.run_cli("img-status", "--project", self.proj, "--json")
        st = json.loads(r.stdout)
        self.assertEqual(st["counts"]["saved"], 1)
        self.assertEqual(st["counts"]["pending"], 3)

        # 6) 非法图片被拒（不落盘）
        bad = Path(base) / "t.gif"
        bad.write_bytes(TINY_PNG)
        r = subprocess.run(
            [PY, "-X", "utf8", str(CLI), "img-save", "--project", self.proj,
             "--id", "img_002", "--file", str(bad)],
            capture_output=True, text=True, encoding="utf-8",
            env={"BIDCRAFT_LIB_ROOT": self.root, "PATH": ""},
        )
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("不支持的图片格式", r.stderr)
        doc = json.loads(plan_json.read_text(encoding="utf-8"))
        self.assertEqual(next(it for it in doc["items"] if it["id"] == "img_002")["status"], "pending")


if __name__ == "__main__":
    unittest.main()
