# -*- coding: utf-8 -*-
"""unit：m_img img-embed —— 技术标 AI 配图嵌入（写操作）：
saved 项按 section 匹配章节树 → 章节标题后插入 ![图题](绝对路径)；
幂等（已含引用则跳过）；未匹配/缺正文/缺图 → 披露不嵌入。"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

from _shared import core          # noqa: E402
from m6_tech import store as tech_store   # noqa: E402
import m_img as mimg              # noqa: E402


class ImgEmbedTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        core.Library(self.root).init_enterprise("嵌入企业")
        self.ent = self.root / "嵌入企业"
        self.project = "嵌入项目"
        proj = self.ent / "项目级" / self.project
        (proj / "招标解析").mkdir(parents=True, exist_ok=True)
        (proj / "配图").mkdir(parents=True, exist_ok=True)
        self.proj = proj
        # 配图清单：2 saved + 1 pending
        plan = {"project": self.project, "items": [
            {"id": "img_001", "section": "人员配备", "kind": "框图", "status": "saved", "file": "配图/img_001.png"},
            {"id": "img_002", "section": "履约保障措施", "kind": "示意图", "status": "saved", "file": "配图/img_002.png"},
            {"id": "img_003", "section": "评分办法", "kind": "对照图", "status": "pending", "file": ""},
        ]}
        plan_name = "配图清单_%s.json" % self.project
        (proj / "配图" / plan_name).write_text(
            json.dumps(plan, ensure_ascii=False), encoding="utf-8")
        (proj / "配图" / "img_001.png").write_bytes(b"x" * 16)
        (proj / "配图" / "img_002.png").write_bytes(b"x" * 16)
        # 技术标章节树 + 章节 md（含 人员配备 章节标题，供 img_001 命中）
        self.tech = tech_store.ensure_tech_dir(self.ent, self.project)
        tree = {
            "schema": "m6.tree/v1", "project": self.project, "bidMode": "明标",
            "pageConstraint": {"max": 100, "estimate": 2, "charsPerPage": 1000, "source": "单测"},
            "style": {"preset": "single-column"}, "layout": {"font": "gov-gongwen"},
            "terminology": {}, "personnel": [],
            "chapters": [
                {"id": "ch01", "no": "1", "title": "人员配备与组织机构", "level": 1, "scoreRefs": [],
                 "keyPoints": [], "wordCnt": 200, "status": "PENDING",
                 "files": {"body": "章节/ch01.md", "meta": "章节/.meta/ch01.json"}},
                {"id": "ch02", "no": "2", "title": "质量进度投资控制措施", "level": 1, "scoreRefs": [],
                 "keyPoints": [], "wordCnt": 200, "status": "PENDING",
                 "files": {"body": "章节/ch02.md", "meta": "章节/.meta/ch02.json"}},
            ],
        }
        tech_store.write_json_inside(self.tech, "章节树.json", tree)
        (self.tech / "章节" / "ch01.md").write_text("# 人员配备与组织机构\n\n正文内容。\n", encoding="utf-8")
        (self.tech / "章节" / "ch02.md").write_text("# 质量进度投资控制措施\n\n正文内容。\n", encoding="utf-8")

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
            rc = mimg.cmd_img_embed(self._args())
        return json.loads(buf.getvalue()), rc

    def test_embed_match_and_idempotent(self):
        out, rc = self._run()
        self.assertEqual(rc, 0)
        self.assertEqual(out["saved"], 2)
        self.assertEqual(out["embedded"], 1)     # 仅 img_001 命中 人员配备
        self.assertEqual(out["unmatched"], 1)     # img_002 履约保障措施 无匹配章节
        ch01 = (self.tech / "章节" / "ch01.md").read_text(encoding="utf-8")
        img_abs = str((self.proj / "配图" / "img_001.png").resolve())
        self.assertIn(img_abs, ch01)
        self.assertIn("![", ch01)
        # 幂等：重跑 embedded=0 skipped=1
        out2, _ = self._run()
        self.assertEqual(out2["embedded"], 0)
        self.assertEqual(out2["skipped"], 1)

    def test_unmatched_disclosed(self):
        out, _ = self._run()
        miss = {m["id"]: m for m in out["details"]["unmatched"]}
        self.assertIn("img_002", miss)
        self.assertIn("无匹配章节", miss["img_002"]["reason"])

    def test_missing_plan_raises(self):
        (self.proj / "配图" / ("配图清单_%s.json" % self.project)).unlink()
        with self.assertRaises(core.LibraryError):
            self._run()

    def test_missing_chapter_body_disclosed(self):
        # img_001 命中 ch01，但删除 ch01.md → 披露不嵌入（不报错）
        (self.tech / "章节" / "ch01.md").unlink()
        out, rc = self._run()
        self.assertEqual(rc, 0)
        self.assertEqual(out["embedded"], 0)
        reason = out["details"]["unmatched"][0]["reason"]
        self.assertIn("章节正文不存在", reason)


if __name__ == "__main__":
    unittest.main()
