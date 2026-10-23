# -*- coding: utf-8 -*-
"""M6 T11/T12 单测：tech-rewrite（精修回路）/ tech-diff（双通道差异）/ export V12 闸门。

复用 test_m6_write.py 的 fixture（tech-init → outline --confirm → ctx → parse 全链路）。
"""
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))

sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(_HERE, "..", "..", "scripts"))

import bidcraft                                     # noqa: E402
from _shared import core                            # noqa: E402
from m6_tech import store                           # noqa: E402
from test_m6_write import BLOCK, _body               # noqa: E402
from test_m6_cli import PROJECT, _draft, _material, _points   # noqa: E402

REVISE = ('\n\n<!-- M6-REVISE\n'
          '{"changes":[{"where":"L10","why":"补强监理深度"}],'
          '"untouched":"其余段落未改动"}\n-->\n')


def _revised(tail=""):
    return "# 1 工程概况与监理范围\n\n" + "监理组织与任务" * 600 + tail + REVISE


class RewriteDiffTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.ent, _ = core.Library(self.root).init_enterprise("企业A")
        self.proj = self.ent / "项目级" / PROJECT
        self.tdir = self.proj / "招标解析"
        self.tdir.mkdir(parents=True)
        self._write_points(_points())
        (self.tdir / ("素材清单_%s.json" % PROJECT)).write_text(
            json.dumps(_material(), ensure_ascii=False), encoding="utf-8")
        self.draft_path = self.proj / "章节树草案.json"
        self.draft_path.write_text(json.dumps(_draft(), ensure_ascii=False), encoding="utf-8")
        self.md_path = self.proj / "草稿_ch-01.md"

    def tearDown(self):
        self.tmp.cleanup()

    # -- helpers ---------------------------------------------------------
    def _write_points(self, obj):
        (self.tdir / ("投标要点_%s.json" % PROJECT)).write_text(
            json.dumps(obj, ensure_ascii=False), encoding="utf-8")

    def _run(self, *argv):
        out, err, code = io.StringIO(), io.StringIO(), 0
        with redirect_stdout(out), redirect_stderr(err):
            try:
                bidcraft.main(["--root", str(self.root), "--enterprise", "企业A"] + list(argv))
            except SystemExit as e:
                code = e.code or 0
        return code, out.getvalue(), err.getvalue()

    def _tech(self):
        return store.tech_path(self.ent, PROJECT)

    def _ready(self, bid_mode="明标", confirm=True):
        if bid_mode != "明标":
            self._write_points(_points(bid_mode=bid_mode))
        self.assertEqual(self._run("tech-init", "--project", PROJECT)[0], 0)
        args = ["tech-outline", "--project", PROJECT, "--file", str(self.draft_path)]
        if confirm:
            args.append("--confirm")
        self.assertEqual(self._run(*args)[0], 0)

    def _ctx(self, cid="ch-01"):
        self.assertEqual(self._run("tech-ctx", "--project", PROJECT, "--chapter", cid)[0], 0)

    def _parse(self, text=None):
        self.md_path.write_text(_body() if text is None else text, encoding="utf-8")
        return self._run("tech-parse", "--project", PROJECT, "--chapter", "ch-01",
                         "--file", str(self.md_path))

    def _rewrite(self, text=None):
        self.md_path.write_text(_revised() if text is None else text, encoding="utf-8")
        return self._run("tech-rewrite", "--project", PROJECT, "--chapter", "ch-01",
                         "--file", str(self.md_path))

    def _state(self, cid="ch-01"):
        return store.find_chapter(store.read_tree(self._tech()), cid)["status"]

    def _diff_json(self):
        return self._tech() / ("检查/双通道差异_%s.json" % PROJECT)

    def _verdict_path(self, items):
        p = self.proj / "裁决.json"
        p.write_text(json.dumps({"diffs": items}, ensure_ascii=False), encoding="utf-8")
        return p

    # -- tech-rewrite ----------------------------------------------------
    def test_rewrite_requires_gate(self):
        self._ready(confirm=False)
        code, _, err = self._rewrite()
        self.assertEqual(code, 1)
        self.assertIn("闸门①未确认", err)

    def test_rewrite_requires_existing_body(self):
        self._ready()
        self._ctx()
        code, _, err = self._rewrite()
        self.assertEqual(code, 1)
        self.assertIn("正文不存在", err)

    def test_rewrite_rejects_short_then_recovers(self):
        self._ready()
        self._ctx()
        self.assertEqual(self._parse()[0], 0)
        code, _, err = self._rewrite("# 1 短\n\n内容不足" + REVISE)
        self.assertEqual(code, 1)
        self.assertIn("篇幅不足", err)
        self.assertEqual(self._state(), "FAILED")
        code, out, err = self._rewrite()
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self._state(), "WRITTEN")

    def test_rewrite_rejects_template_placeholder(self):
        self._ready()
        self._ctx()
        self.assertEqual(self._parse()[0], 0)
        code, _, err = self._rewrite(_revised(tail="\n\n{{占位}}\n"))
        self.assertEqual(code, 1)
        self.assertIn("模板占位", err)
        self.assertEqual(self._state(), "FAILED")

    def test_rewrite_rejects_coverage_block(self):
        self._ready()
        self._ctx()
        self.assertEqual(self._parse()[0], 0)
        code, _, err = self._rewrite("# 1 工程概况\n\n" + "监理大纲" * 600 + BLOCK)
        self.assertEqual(code, 1)
        self.assertIn("REVISEBLOCK", err)
        self.assertEqual(self._state(), "FAILED")

    def test_rewrite_rejects_sensitive_in_anbiao(self):
        self._ready(bid_mode="暗标")
        self._ctx()
        self.assertEqual(self._parse()[0], 0)
        code, _, err = self._rewrite(_revised(tail="\n\n本项目由企业A承担。\n"))
        self.assertEqual(code, 1)
        self.assertIn("敏感词", err)
        self.assertEqual(self._state(), "FAILED")

    def test_rewrite_writes_body_revise_and_trash(self):
        self._ready()
        self._ctx()
        self.assertEqual(self._parse()[0], 0)
        tech = self._tech()
        old_text = store.read_chapter_body(tech, store.find_chapter(store.read_tree(tech), "ch-01"))
        code, out, err = self._rewrite()
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self._state(), "WRITTEN")
        self.assertIn("修改", out)
        self.assertIn("M6-REVISE", out)
        ch = store.find_chapter(store.read_tree(tech), "ch-01")
        new_text = store.read_chapter_body(tech, ch)
        self.assertNotIn("M6-REVISE", new_text)
        self.assertNotEqual(old_text, new_text)
        # REVISE 块落盘 .meta/ch-01.revise.json；COVERAGE 未被覆盖
        rv = store.read_revise(tech, "ch-01")
        self.assertEqual(rv["block"], "M6-REVISE")
        self.assertEqual(rv["data"]["changes"][0]["where"], "L10")
        sc = store.read_selfcheck(tech, "ch-01")
        self.assertEqual(sc["block"], "M6-COVERAGE")
        # 旧稿进 .rewrite-trash
        trash = tech / ".rewrite-trash"
        self.assertTrue(trash.is_dir())
        self.assertGreaterEqual(len(list(trash.rglob("ch-01.md"))), 1)

    def test_rewrite_after_confirmed_requires_recheck(self):
        self._ready()
        self._ctx()
        self.assertEqual(self._parse()[0], 0)
        self.assertEqual(self._run("tech-check", "--project", PROJECT)[0], 0)
        self.assertEqual(self._run("tech-report", "--project", PROJECT, "--confirm")[0], 0)
        self.assertEqual(self._state(), "CONFIRMED")
        code, out, err = self._rewrite()
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self._state(), "WRITTEN")     # 闸门②不静默继承
        self.assertIn("tech-check", out)

    # -- tech-diff -------------------------------------------------------
    def test_diff_requires_matrix(self):
        self._ready()
        code, _, err = self._run("tech-diff", "--project", PROJECT)
        self.assertEqual(code, 1)
        self.assertIn("覆盖矩阵缺失", err)

    def test_diff_no_selfcheck_but_matrix_exists(self):
        self._ready()
        self._ctx()
        self.assertEqual(self._parse()[0], 0)
        self.assertEqual(self._run("tech-check", "--project", PROJECT)[0], 0)
        code, out, err = self._run("tech-diff", "--project", PROJECT)
        self.assertEqual(code, 0, out + err)
        jp = self._diff_json()
        self.assertTrue(jp.is_file())
        self.assertTrue(self._tech() / ("检查/双通道差异_%s.md" % PROJECT))
        doc = json.loads(jp.read_text(encoding="utf-8"))
        self.assertEqual(doc["schema"], "m6.diff/v1")
        self.assertIsInstance(doc["diffs"], list)

    def test_diff_confirm_without_verdict_rejected(self):
        self._ready()
        self._ctx()
        self.assertEqual(self._parse()[0], 0)
        self.assertEqual(self._run("tech-check", "--project", PROJECT)[0], 0)
        code, _, err = self._run("tech-diff", "--project", PROJECT, "--confirm")
        self.assertEqual(code, 1)
        self.assertIn("不得静默判定", err)

    def test_diff_verdict_count_mismatch_rejected(self):
        self._ready()
        self._ctx()
        self.assertEqual(self._parse()[0], 0)
        self.assertEqual(self._run("tech-check", "--project", PROJECT)[0], 0)
        self.assertEqual(self._run("tech-diff", "--project", PROJECT)[0], 0)
        vp = self._verdict_path([])
        code, _, err = self._run("tech-diff", "--project", PROJECT,
                                 "--verdict", str(vp), "--confirm")
        self.assertEqual(code, 1)
        self.assertIn("差异条数", err)

    def test_diff_verdict_bad_idx_rejected(self):
        self._ready()
        self._ctx()
        self.assertEqual(self._parse()[0], 0)
        self.assertEqual(self._run("tech-check", "--project", PROJECT)[0], 0)
        self.assertEqual(self._run("tech-diff", "--project", PROJECT)[0], 0)
        vp = self._verdict_path([{"idx": 99, "verdict": "accept"}])
        code, _, err = self._run("tech-diff", "--project", PROJECT,
                                 "--verdict", str(vp), "--confirm")
        self.assertEqual(code, 1)
        self.assertIn("idx 越界", err)

    def test_diff_resolve_writes_confirm_log(self):
        self._ready()
        self._ctx()
        self.assertEqual(self._parse()[0], 0)
        self.assertEqual(self._run("tech-check", "--project", PROJECT)[0], 0)
        self.assertEqual(self._run("tech-diff", "--project", PROJECT)[0], 0)
        jp = self._diff_json()
        n = len(json.loads(jp.read_text(encoding="utf-8"))["diffs"])
        vp = self._verdict_path([{"idx": i, "verdict": "accept", "note": "人工核对无误"}
                                 for i in range(n)])
        code, out, err = self._run("tech-diff", "--project", PROJECT,
                                   "--verdict", str(vp), "--confirm")
        self.assertEqual(code, 0, out + err)
        self.assertIn("已落盘", out)
        tree = store.read_tree(self._tech())
        rec = tree["confirmLog"][-1]
        self.assertEqual(rec["gate"], "diff")
        note = json.loads(rec["note"])
        self.assertEqual(note["total"], n)
        self.assertEqual(len(note["items"]), n)

    def test_diff_resolve_verdict_needs_confirm(self):
        self._ready()
        self._ctx()
        self.assertEqual(self._parse()[0], 0)
        self.assertEqual(self._run("tech-check", "--project", PROJECT)[0], 0)
        self.assertEqual(self._run("tech-diff", "--project", PROJECT)[0], 0)
        vp = self._verdict_path([{"idx": 0, "verdict": "accept"}])
        code, out, _ = self._run("tech-diff", "--project", PROJECT,
                                 "--verdict", str(vp))
        self.assertEqual(code, 0, out)
        self.assertIn("需 --confirm", out)

    # -- export V12 ------------------------------------------------------
    def _checked_with_diff(self):
        self._ready()
        self._ctx()
        self.assertEqual(self._parse()[0], 0)
        self.assertEqual(self._run("tech-ctx", "--project", PROJECT, "--chapter", "ch-02")[0], 0)
        self.md_path.write_text(_body(chars=800, tail=""), encoding="utf-8")
        self.assertEqual(self._run("tech-parse", "--project", PROJECT, "--chapter", "ch-02",
                                   "--file", str(self.md_path))[0], 0)
        self.assertEqual(self._run("tech-check", "--project", PROJECT)[0], 0)
        self.assertEqual(self._run("tech-diff", "--project", PROJECT)[0], 0)
        return json.loads(self._diff_json().read_text(encoding="utf-8"))["diffs"]

    def _export(self, force=False):
        argv = ["tech-export", "--project", PROJECT, "--enterprise", "企业A"]
        if force:
            argv.append("--force")
        return self._run(*argv)

    def test_export_blocked_by_unresolved_diff(self):
        diffs = self._checked_with_diff()
        self.assertGreaterEqual(len(diffs), 1)
        code, _, err = self._export()
        self.assertEqual(code, 1)
        self.assertIn("未全部裁决", err)

    def test_export_force_bypasses_unresolved_diff(self):
        self._checked_with_diff()
        code, out, err = self._export(force=True)
        self.assertEqual(code, 0, out + err)

    def test_export_allowed_after_resolved_diff(self):
        diffs = self._checked_with_diff()
        vp = self._verdict_path([{"idx": i, "verdict": "accept"} for i in range(len(diffs))])
        self.assertEqual(self._run("tech-diff", "--project", PROJECT,
                                   "--verdict", str(vp), "--confirm")[0], 0)
        code, out, err = self._export()
        self.assertEqual(code, 0, out + err)


if __name__ == "__main__":
    unittest.main()
