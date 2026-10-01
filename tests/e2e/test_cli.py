# -*- coding: utf-8 -*-
"""L3 端到端测试：CLI 全流程（subprocess 调用，临时素材根，数量最少）。
验证命令契约、退出码约定（0/1/2）与三层落位。"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scripts")
CLI = os.path.join(_SCRIPTS, "bidcraft.py")
ENT = "和县测试监理有限公司"


def run(root, *args):
    return subprocess.run(
        [sys.executable, CLI, "--root", root, "--enterprise", ENT, *args],
        capture_output=True, text=True, encoding="utf-8")


def run_json(root, *args):
    r = run(root, "--json", *args)
    return r, json.loads(r.stdout)


class CliBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="bid_e2e_")
        self.root = Path(self.tmp)
        self.ent_dir = self.root / ENT

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _init(self):
        r = run(str(self.root), "init-enterprise", "--name", ENT)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.lib = self.ent_dir / "企业级" / "业绩库"

    def _seed(self, fname, cat="资质", sub="体系认证", kw=None):
        r = run(str(self.root), "open-inbox", "--note", "b")
        self.assertEqual(r.returncode, 0)
        p = Path(self.root) / fname
        p.write_text("dummy", encoding="utf-8")
        r = run(str(self.root), "upload", "--file", str(p))
        self.assertEqual(r.returncode, 0, r.stderr)
        r = run(str(self.root), "close-inbox")
        self.assertEqual(r.returncode, 0)
        out = self.root / "p.json"
        r = run(str(self.root), "propose", "--out", str(out))
        self.assertEqual(r.returncode, 0, r.stderr)
        prop = json.loads(out.read_text(encoding="utf-8"))
        it = prop["items"][0]
        it["category"], it["subtype"] = cat, sub
        if kw:
            it["keywords"] = [kw]
        out.write_text(json.dumps(prop, ensure_ascii=False, indent=2), encoding="utf-8")
        r = run(str(self.root), "apply", "--proposal", str(out))
        self.assertEqual(r.returncode, 0, r.stderr)


class TestCliInit(CliBase):
    def test_init_creates_three_layer(self):
        self._init()
        self.assertTrue((self.ent_dir / "项目级").is_dir())
        self.assertTrue((self.ent_dir / "企业级" / "模板库").is_dir())
        for s in ["资质", "人员", "业绩", "荣誉", "财务", "收件箱", "回收站"]:
            self.assertTrue((self.lib / s).is_dir(), s)
        self.assertTrue((self.lib / "素材台账.json").exists())

    def test_list_enterprises(self):
        self._init()
        r, obj = run_json(str(self.root), "list-enterprises")
        self.assertEqual(r.returncode, 0)
        self.assertIn(ENT, obj["enterprises"])


class TestCliFlow(CliBase):
    def test_full_flow(self):
        self._init()
        self._seed("ISO9001_20260101.pdf")
        self.assertTrue((self.lib / "资质" / "ISO9001_20260101.pdf").exists())
        r, q = run_json(str(self.root), "query", "--keyword", "ISO9001")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(len(q), 1)
        r, ov = run_json(str(self.root), "overview")
        self.assertEqual(ov["ledger_total"], 1)
        self.assertEqual(ov["path"], str(self.lib))

    def test_name_conflict_unconfirmed_exit2(self):
        self._init()
        self._seed("ISO9001_20260101.pdf")
        # 第二份同关键字 → propose 应标同名冲突
        p = Path(self.root) / "ISO9001_20270101.pdf"
        p.write_text("dummy", encoding="utf-8")
        run(str(self.root), "open-inbox")
        run(str(self.root), "upload", "--file", str(p))
        run(str(self.root), "close-inbox")
        out = self.root / "p2.json"
        run(str(self.root), "propose", "--out", str(out))
        prop = json.loads(out.read_text(encoding="utf-8"))
        self.assertTrue(prop["items"][0]["is_name_conflict"])
        # 未确认 → exit 2
        r = run(str(self.root), "apply", "--proposal", str(out))
        self.assertEqual(r.returncode, 2)
        # 确认 keep_both → 成功
        prop["items"][0]["on_conflict"] = "keep_both"
        out.write_text(json.dumps(prop, ensure_ascii=False, indent=2), encoding="utf-8")
        r = run(str(self.root), "apply", "--proposal", str(out))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_trash_and_cleanup(self):
        self._init()
        self._seed("ISO9001_20260101.pdf")
        r = run(str(self.root), "trash", "--path", "资质/ISO9001_20260101.pdf")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse((self.lib / "资质" / "ISO9001_20260101.pdf").exists())
        r = run(str(self.root), "cleanup-trash", "--days", "0")
        self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == "__main__":
    unittest.main()
