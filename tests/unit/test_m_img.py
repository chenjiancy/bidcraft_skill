# -*- coding: utf-8 -*-
"""unit：m_img —— img-plan 规则匹配/幂等、img-save 校验与回填、img-status。"""

import base64
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

from m4_tender import rules as m4_rules   # noqa: E402
from m4_tender import tender as m4_tender  # noqa: E402
from _shared import core                   # noqa: E402
import m_img                               # noqa: E402

# 1x1 红色 PNG
TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")

POINTS = {
    "project": "配图单测项目",
    "modules": [
        {"id": "basic", "title": "项目基本信息", "type": "fields", "items": []},
        {"id": "qualification", "title": "资格条件", "type": "items",
         "items": [{"name": "资质等级", "value": "甲级", "source": "P1"}]},
        {"id": "staff", "title": "人员配备", "type": "fields", "items": []},
        {"id": "project_overview", "title": "项目概况与监理工作内容", "type": "fields", "items": []},
        {"id": "scoring", "title": "评分办法", "type": "mixed", "items": []},
        {"id": "pricing", "title": "报价要求", "type": "fields", "items": []},
        {"id": "reject", "title": "废标红线", "type": "items", "items": []},
        {"id": "pending", "title": "待确认项", "type": "items", "items": []},
    ],
    "diffs": [],
}


class MImgBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        core.Library(self.root).init_enterprise("配图企业")  # 建合法企业台账（三层结构）
        self.ent = self.root / "配图企业"
        self.project = "配图单测项目"
        self.args = self._mk_args()

    def tearDown(self):
        self._tmp.cleanup()

    def _mk_args(self, **kw):
        class A:
            pass
        a = A()
        a.root = str(self.root)
        a.enterprise = None
        a.project = self.project
        a.source = ""
        a.file = ""
        a.temp = ""
        for k, v in kw.items():
            setattr(a, k, v)
        return a

    def _write_points(self):
        tdir = m4_tender.project_tender_dir(self.ent, self.project)
        tdir.mkdir(parents=True, exist_ok=True)
        (tdir / (m4_rules.points_base(self.project) + ".json")).write_text(
            json.dumps(POINTS, ensure_ascii=False), encoding="utf-8")
        (tdir / (m4_rules.points_base(self.project) + ".md")).write_text("# 投标要点\n", encoding="utf-8")


class ImgPlanTest(MImgBase):
    def test_plan_generates_expected_items(self):
        self._write_points()
        m_img.cmd_img_plan(self.args)
        doc = m_img._load_plan(self.ent, self.project)
        ids = [it["id"] for it in doc["items"]]
        self.assertIn("img_001", ids)  # qualification
        self.assertIn("img_002", ids)  # staff
        self.assertIn("img_003", ids)  # project_overview
        self.assertIn("img_004", ids)  # scoring
        for it in doc["items"]:
            self.assertEqual(it["status"], "pending")
            self.assertTrue(it["subject"])

    def test_plan_idempotent(self):
        self._write_points()
        m_img.cmd_img_plan(self.args)
        m_img.cmd_img_plan(self.args)  # 再次运行不重复
        doc = m_img._load_plan(self.ent, self.project)
        self.assertEqual(len(doc["items"]), 4)

    def test_plan_missing_points(self):
        with self.assertRaises(core.LibraryError):
            m_img.cmd_img_plan(self.args)


class ImgSaveTest(MImgBase):
    def setUp(self):
        super().setUp()
        self._write_points()
        m_img.cmd_img_plan(self.args)

    def test_save_ok(self):
        src = Path(self._tmp.name) / "t.png"
        src.write_bytes(TINY_PNG)
        m_img.cmd_img_save(self._mk_args(id="img_001", file=str(src), source="CodeBuddy"))
        item = next(it for it in m_img._load_plan(self.ent, self.project)["items"] if it["id"] == "img_001")
        self.assertEqual(item["status"], "saved")
        self.assertEqual(item["source"], "CodeBuddy")
        dst = m_img.img_dir(self.ent, self.project) / "img_001.png"
        self.assertTrue(dst.exists())

    def test_save_rejects_unknown_id(self):
        src = Path(self._tmp.name) / "t.png"
        src.write_bytes(TINY_PNG)
        with self.assertRaises(core.LibraryError):
            m_img.cmd_img_save(self._mk_args(id="img_999", file=str(src)))

    def test_save_rejects_bad_ext(self):
        src = Path(self._tmp.name) / "t.gif"
        src.write_bytes(TINY_PNG)
        with self.assertRaises(core.LibraryError):
            m_img.cmd_img_save(self._mk_args(id="img_001", file=str(src)))

    def test_save_rejects_missing_file(self):
        with self.assertRaises(core.LibraryError):
            m_img.cmd_img_save(self._mk_args(id="img_001", file=str(Path(self._tmp.name) / "no.png")))

    def test_save_rejects_duplicate(self):
        src = Path(self._tmp.name) / "t.png"
        src.write_bytes(TINY_PNG)
        m_img.cmd_img_save(self._mk_args(id="img_001", file=str(src)))
        with self.assertRaises(core.LibraryError):
            m_img.cmd_img_save(self._mk_args(id="img_001", file=str(src)))

    def test_save_status_counts(self):
        src = Path(self._tmp.name) / "t.png"
        src.write_bytes(TINY_PNG)
        m_img.cmd_img_save(self._mk_args(id="img_001", file=str(src)))
        doc = m_img._load_plan(self.ent, self.project)
        statuses = [it["status"] for it in doc["items"]]
        self.assertEqual(statuses.count("saved"), 1)
        self.assertEqual(statuses.count("pending"), 3)

    def test_save_via_temp_ok(self):
        tmp = m_img.img_dir(self.ent, self.project) / "临时"
        tmp.mkdir(parents=True, exist_ok=True)
        (tmp / "org.png").write_bytes(TINY_PNG)
        m_img.cmd_img_save(self._mk_args(id="img_002", temp="org.png", source="CodeBuddy"))
        item = next(it for it in m_img._load_plan(self.ent, self.project)["items"] if it["id"] == "img_002")
        self.assertEqual(item["status"], "saved")
        self.assertEqual(item["file"], "配图/img_002.png")
        self.assertTrue((m_img.img_dir(self.ent, self.project) / "img_002.png").exists())

    def test_save_rejects_temp_path_traversal(self):
        tmp = m_img.img_dir(self.ent, self.project) / "临时"
        tmp.mkdir(parents=True, exist_ok=True)
        (tmp / "org.png").write_bytes(TINY_PNG)
        for bad in ("../org.png", "a/b.png", "C:/x.png", "\\x.png"):
            with self.assertRaises(core.LibraryError, msg=bad):
                m_img.cmd_img_save(self._mk_args(id="img_002", temp=bad))

    def test_save_requires_file_or_temp(self):
        with self.assertRaises(core.LibraryError):
            m_img.cmd_img_save(self._mk_args(id="img_001"))

    def test_gen_agent_prompt_contract(self):
        # 不真调 CodeBuddy：验证提示词契约（无公司名/无水印/固定落点）
        tmp = m_img.img_dir(self.ent, self.project) / "临时"
        item = {"id": "img_003", "subject": "项目概况示意", "kind": "示意图", "ratio": "16:9",
                "style": "商务正式、蓝色系", "section": "项目概况"}
        p = m_img._codebuddy_prompt(item, str(tmp / "img_003.png"))
        self.assertIn("不得包含任何水印、AI 生成标识", p)
        self.assertIn("禁止出现真实单位名称/LOGO/人名", p)
        self.assertIn("保存到 %s" % (tmp / "img_003.png"), p)
        self.assertTrue(p.startswith("请使用 ImageGen 工具"))


if __name__ == "__main__":
    unittest.main()
