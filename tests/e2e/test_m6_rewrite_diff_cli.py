# -*- coding: utf-8 -*-
"""M6 T11/T12 端到端测试（L3）：CLI 全链路 —— init→outline→ctx→parse→check→diff→裁决→
rewrite 精修→重新 check→report 确认→export docx。

通过 bidcraft.main 真实入口（--root/--enterprise/子命令 argv），验证命令可组合成
完整精修回路（T11）+ 双通道裁决（T12，V12 不静默）+ 导出闭环。
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "..", "scripts"))

import bidcraft                       # noqa: E402
from m6_tech import store             # noqa: E402

PROJECT = "端到端项目"


def _points():
    return {
        "project": PROJECT,
        "modules": [
            {"id": "scoring", "title": "评分办法", "type": "mixed",
             "method": {"value": "综合评分法", "evidence": "e"},
             "score_items": [{"item": "监理大纲（50分）", "weight": 50, "unit": "分", "evidence": "E1"}]},
            {"id": "reject", "title": "废标红线", "type": "items",
             "items": [{"type": "格式", "rule": "技术标总页数不超过 60 页；按明标编制", "evidence": "e"}]},
        ],
    }


def _draft():
    return {"chapters": [
        {"id": "ch-01", "no": "1", "title": "工程概况与监理范围", "level": 1,
         "scoreRefs": [{"idx": 0, "item": "监理大纲（50分）", "weight": 50}],
         "keyPoints": ["监理大纲"], "wordCnt": 3000, "dependsOnMaterials": []},
    ]}


class RewriteDiffE2ETest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self._init_ent()
        self.proj = self.ent / "项目级" / PROJECT
        self.tdir = self.proj / "招标解析"
        self.tdir.mkdir(parents=True)
        (self.tdir / ("投标要点_%s.json" % PROJECT)).write_text(
            json.dumps(_points(), ensure_ascii=False), encoding="utf-8")
        (self.tdir / ("素材清单_%s.json" % PROJECT)).write_text(
            json.dumps({"project": PROJECT, "personnel": [], "performance": [], "items": []},
                       ensure_ascii=False), encoding="utf-8")
        self.draft = self.proj / "章节树草案.json"
        self.draft.write_text(json.dumps(_draft(), ensure_ascii=False), encoding="utf-8")

    def _init_ent(self):
        # 通过 CLI 初始化企业（真实入口）
        self._run("init-enterprise", "--name", "端到端企业")
        self.ent = self.root / "端到端企业"

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, *argv):
        code = 0
        try:
            bidcraft.main(["--root", str(self.root), "--enterprise", "端到端企业"] + list(argv))
        except SystemExit as e:
            code = e.code or 0
        return code

    def _tech(self):
        return store.tech_path(self.ent, PROJECT)

    def _body(self, chars=2400, tail="", block=True):
        b = ('\n\n<!-- M6-COVERAGE\n'
             '{"keyPoints":[{"point":"监理大纲","covered":true}],'
             '"missingMaterials":[],"notes":"结构完整"}\n-->\n') if block else ""
        return ("# 1 工程概况与监理范围\n\n" + "监理大纲" * (chars // 4) + tail + b)

    def test_full_loop_with_rewrite_and_diff(self):
        # 1) init → outline(闸门①) → ctx → parse
        self.assertEqual(self._run("tech-init", "--project", PROJECT), 0)
        self.assertEqual(self._run("tech-outline", "--project", PROJECT, "--confirm",
                                   "--file", str(self.draft)), 0)
        self.assertEqual(self._run("tech-ctx", "--project", PROJECT, "--chapter", "ch-01"), 0)
        md = self.proj / "初稿_ch-01.md"
        md.write_text(self._body(), encoding="utf-8")
        self.assertEqual(self._run("tech-parse", "--project", PROJECT, "--chapter", "ch-01",
                                   "--file", str(md)), 0)

        # 2) check → diff → 差异未裁决 → export 被 V12 拒绝
        self.assertEqual(self._run("tech-check", "--project", PROJECT), 0)
        self.assertEqual(self._run("tech-diff", "--project", PROJECT), 0)
        self.assertEqual(self._run("tech-export", "--project", PROJECT, "--enterprise", "端到端企业"), 1)

        # 3) rewrite 精修（带 M6-REVISE）→ 状态回 WRITTEN（闸门②不静默）
        rev = ("# 1 工程概况与监理范围\n\n" + "监理组织与任务" * 600 +
               '\n\n<!-- M6-REVISE\n'
               '{"changes":[{"where":"L10","why":"补强监理深度"}],"untouched":"其余段落未改动"}\n-->\n')
        md2 = self.proj / "精修_ch-01.md"
        md2.write_text(rev, encoding="utf-8")
        self.assertEqual(self._run("tech-rewrite", "--project", PROJECT, "--chapter", "ch-01",
                                   "--file", str(md2)), 0)
        self.assertEqual(store.find_chapter(store.read_tree(self._tech()), "ch-01")["status"],
                         "WRITTEN")

        # 4) 重新 check → diff → 逐项裁决 → export 成功
        self.assertEqual(self._run("tech-check", "--project", PROJECT), 0)
        self.assertEqual(self._run("tech-diff", "--project", PROJECT), 0)
        jp = self._tech() / ("检查/双通道差异_%s.json" % PROJECT)
        n = len(json.loads(jp.read_text(encoding="utf-8"))["diffs"])
        vp = self.proj / "裁决.json"
        vp.write_text(json.dumps({"diffs": [{"idx": i, "verdict": "accept"}
                                            for i in range(n)]}, ensure_ascii=False),
                      encoding="utf-8")
        self.assertEqual(self._run("tech-diff", "--project", PROJECT,
                                   "--verdict", str(vp), "--confirm"), 0)
        self.assertEqual(self._run("tech-export", "--project", PROJECT, "--enterprise", "端到端企业"), 0)

        # 5) 产物断言：docx 存在、导出元数据、.rewrite-trash 留痕
        out = self._tech() / "产出" / ("技术标_%s.docx" % PROJECT)
        self.assertTrue(out.is_file(), "端到端导出 docx 缺失")
        meta = self._tech() / "章节" / ".meta" / "export.json"
        self.assertTrue(meta.is_file())
        self.assertTrue((self._tech() / ".rewrite-trash").is_dir())
        tree = store.read_tree(self._tech())
        self.assertEqual(tree["confirmLog"][-1]["gate"], "diff")


if __name__ == "__main__":
    unittest.main()
