# -*- coding: utf-8 -*-
"""unit：m_img img-audit —— 技术标 AI 配图暗标合规审计（只读）：
saved 项逐图检查 文件存在 / AIGC 元数据残留 / subject-style 红线词 / source 标注；
无 OCR 环境披露「图内文字需人工核验」不假装检查。"""

import json
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

from _shared import core          # noqa: E402
import m_img as mimg              # noqa: E402


def _fake_png(data):
    """构造一个可读文件（img-audit 不解析像素，只需字节可读）。"""
    return data


class ImgAuditTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        core.Library(self.root).init_enterprise("审计企业")
        self.ent = self.root / "审计企业"
        self.project = "审计项目"
        proj = self.ent / "项目级" / self.project
        (proj / "配图").mkdir(parents=True, exist_ok=True)
        self.proj = proj
        plan = {"project": self.project, "items": [
            {"id": "img_001", "section": "人员配备", "kind": "框图", "status": "saved",
             "file": "配图/img_001.png", "source": "CodeBuddy", "subject": "监理组织机构框图", "style": "蓝白扁平化"},
            {"id": "img_002", "section": "项目概况", "kind": "示意图", "status": "saved",
             "file": "配图/img_002.png", "source": "豆包", "subject": "项目概况示意", "style": "简洁"},
            {"id": "img_003", "section": "履约保障", "kind": "示意图", "status": "saved",
             "file": "配图/img_003.png", "source": "", "subject": "XX公司资质荣誉示意图", "style": ""},
            {"id": "img_004", "section": "评分办法", "kind": "对照图", "status": "saved",
             "file": "配图/img_004.png", "source": "CodeBuddy", "subject": "评分对照", "style": ""},
        ]}
        plan_name = "配图清单_%s.json" % self.project
        (proj / "配图" / plan_name).write_text(
            json.dumps(plan, ensure_ascii=False), encoding="utf-8")
        # img_001 正常；img_002 正常（AIGC 段在文件头）；img_003 含 AIGC 残留字节 + subject 红线词；
        # img_004 文件缺失（不创建）
        (proj / "配图" / "img_001.png").write_bytes(_fake_png(b"ok-png-body"))
        (proj / "配图" / "img_002.png").write_bytes(_fake_png(b"AIGC{metadata} png-body"))
        (proj / "配图" / "img_003.png").write_bytes(_fake_png(b"AIGC{rest} png-body"))

    def tearDown(self):
        self._tmp.cleanup()

    def _args(self):
        class A:
            root = str(self.root)
            enterprise = None
            project = self.project
            json = True
        return A()

    def _run(self):
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = mimg.cmd_img_audit(self._args())
        return json.loads(buf.getvalue()), rc

    def test_pass_fail_classification(self):
        out, rc = self._run()
        self.assertEqual(rc, 0)
        self.assertEqual(out["saved"], 4)
        by_id = {r["id"]: r for r in out["items"]}
        # img_001：正常 → pass
        self.assertEqual(by_id["img_001"]["status"], "pass")
        self.assertEqual(by_id["img_001"]["issues"], [])
        # img_002：AIGC 残留 → fail
        self.assertEqual(by_id["img_002"]["status"], "fail")
        self.assertTrue(any("AIGC" in i for i in by_id["img_002"]["issues"]))
        # img_003：AIGC 残留 + subject 红线词 + source 空 → fail
        self.assertEqual(by_id["img_003"]["status"], "fail")
        issues = " ".join(by_id["img_003"]["issues"])
        self.assertIn("AIGC", issues)
        self.assertIn("红线词", issues)
        self.assertIn("source", issues)
        # img_004：文件缺失 → fail
        self.assertEqual(by_id["img_004"]["status"], "fail")
        self.assertTrue(any("文件缺失" in i for i in by_id["img_004"]["issues"]))

    def test_ocr_note_when_unavailable(self):
        out, _ = self._run()
        if out["ocr"].startswith("unavailable"):
            for r in out["items"]:
                if r["status"] == "pass":
                    self.assertTrue(any("人工核验" in n for n in r["note"]))
        # OCR 可用时不要求 note（不假装检查的互补断言：至少说明能力）
        self.assertIn("ocr", out)

    # ---- OCR 真扫路径（mock 引擎/文本，验证红线词命中逻辑） ----
    @unittest.mock.patch.object(mimg, "_ocr_engine", return_value=(sys.executable, "paddleocr"))
    def test_ocr_hits_redline_word(self, _me):
        mimg._ocr_texts = unittest.mock.Mock(return_value=["履约保障措施", "XX有限公司", "组织保障"])
        out, _ = self._run()
        by_id = {r["id"]: r for r in out["items"]}
        self.assertTrue(out["ocr"].startswith("available"))
        self.assertEqual(by_id["img_001"]["status"], "fail")
        self.assertTrue(any("图内文字含暗标红线词" in i for i in by_id["img_001"]["issues"]))
        self.assertIn("公司", " ".join(by_id["img_001"]["issues"]))
        # 正常文本 → pass 且 note 附 OCR 文本
        mimg._ocr_texts = unittest.mock.Mock(return_value=["总监理工程师", "专业监理工程师"])
        out, _ = self._run()
        by_id = {r["id"]: r for r in out["items"]}
        self.assertEqual(by_id["img_001"]["status"], "pass")
        self.assertTrue(any("OCR 文本" in n for n in by_id["img_001"]["note"]))

    @unittest.mock.patch.object(mimg, "_ocr_engine", return_value=(sys.executable, "paddleocr"))
    def test_ocr_engine_failure_disclosed(self, _me):
        # OCR 进程失败 → 披露「引擎异常，须人工核验」，不假装通过
        mimg._ocr_texts = unittest.mock.Mock(return_value=None)
        out, _ = self._run()
        by_id = {r["id"]: r for r in out["items"]}
        self.assertEqual(by_id["img_001"]["status"], "pass")
        self.assertTrue(any("OCR 引擎异常" in n for n in by_id["img_001"]["note"]))

    @unittest.mock.patch.object(mimg, "_ocr_engine", return_value=None)
    def test_ocr_unavailable_discloses_manual(self, _me):
        # 引擎缺失 → 每张 pass 图 note「人工核验」，不假装检查
        out, _ = self._run()
        self.assertTrue(out["ocr"].startswith("unavailable"))
        for r in out["items"]:
            if r["status"] == "pass":
                self.assertTrue(any("人工核验" in n for n in r["note"]))


if __name__ == "__main__":
    unittest.main()
