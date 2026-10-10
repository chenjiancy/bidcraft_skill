# -*- coding: utf-8 -*-
"""L3 端到端测试：产物反馈机制 CLI（fb-*）冒烟 + proj-gen CLI（真实数据→临时输出）。"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "scripts"
CLI = [sys.executable, str(SCRIPTS / "bidcraft.py")]

# 真实数据路径：默认示例名（公网安全）；本地真实回归通过环境变量注入（同 test_m5_filler）。
REAL_ENT = os.environ.get("BIDCRAFT_TEST_ENT", r"E:\监理标书制作\示例建设工程监理有限公司")
REAL_PROJECT = os.environ.get("BIDCRAFT_TEST_PROJ", "示例化工园尾水水质提升工程（EPC总承包）监理")


def run(*args, root=None, ent=None, **kw):
    cmd = list(CLI)
    if root:
        cmd += ["--root", str(root)]
    if ent:
        cmd += ["--enterprise", ent]
    cmd += list(args)
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", **kw)


def make_ent_skel(root, ent_name):
    """最小可被 Library 识别的企业骨架（企业级/素材库/资质 等分类目录）。"""
    ent = Path(root) / ent_name
    for d in ["企业级/素材库/资质", "企业级/素材库/人员", "企业级/模板库", "项目级/测试项目/项目模板"]:
        (ent / d).mkdir(parents=True, exist_ok=True)
    return ent


class TestFeedbackCli(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="bid_fb_e2e_")
        cls.ent = make_ent_skel(cls.tmp, "测试监理有限公司")
        cls.rel = "项目级/测试项目/项目模板/开标一览表.docx"
        cls.ent_name = cls.ent.name

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _ensure_prod(self, content=b"fake docx bytes 1"):
        p = self.ent / self.rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content)

    def test_fb_baseline_register(self):
        self._ensure_prod()
        r = run("fb-baseline", "--path", self.rel, "--type", "项目模板",
                "--project", "测试项目", root=self.tmp, ent=self.ent_name)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("已登记产物基线", r.stdout)

    def test_fb_status(self):
        self._ensure_prod()
        run("fb-baseline", "--path", self.rel, "--type", "项目模板",
            root=self.tmp, ent=self.ent_name)
        r = run("fb-status", "--json", root=self.tmp, ent=self.ent_name)
        self.assertEqual(r.returncode, 0, r.stderr)
        data = json.loads(r.stdout)
        self.assertEqual(data["baseline_total"], 1)
        self.assertEqual(data["by_type"].get("项目模板"), 1)

    def test_fb_audit_states(self):
        self._ensure_prod()
        run("fb-baseline", "--path", self.rel, "--type", "项目模板",
            root=self.tmp, ent=self.ent_name)
        r = run("fb-audit", "--json", root=self.tmp, ent=self.ent_name)
        self.assertEqual(r.returncode, 0, r.stderr)
        data = json.loads(r.stdout)
        self.assertEqual(len(data["unchanged"]), 1)

        # 修改文件 → modified
        self._ensure_prod(b"fake docx bytes 2")
        r = run("fb-audit", "--full", "--json", root=self.tmp, ent=self.ent_name)
        data = json.loads(r.stdout)
        self.assertEqual(len(data["modified"]), 1)

        # 删除文件 → missing
        (self.ent / self.rel).unlink()
        r = run("fb-audit", "--json", root=self.tmp, ent=self.ent_name)
        data = json.loads(r.stdout)
        self.assertEqual(len(data["missing"]), 1)

    def test_fb_report(self):
        self._ensure_prod()
        run("fb-baseline", "--path", self.rel, "--type", "项目模板",
            root=self.tmp, ent=self.ent_name)
        self._ensure_prod(b"fake docx bytes 3")
        r = run("fb-report", root=self.tmp, ent=self.ent_name)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("评估报告已生成", r.stdout)
        fdir = self.ent / "产物反馈"
        reports = list(fdir.glob("评估报告_*.md"))
        self.assertTrue(reports)
        txt = reports[0].read_text(encoding="utf-8")
        self.assertIn("系统功能更新评估报告", txt)


class TestProjGenCli(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="bid_m5_e2e_")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_proj_gen_cli_json(self):
        # ⑫ 数据前置细化：proj-gen 需要招标解析的格式契约作为输入，
        # 数据被清除/未生成时应跳过而非在 CLI 里报错。
        proj = Path(REAL_ENT) / "项目级" / REAL_PROJECT
        contract = proj / "招标解析" / "内容契约" / "内容契约.json"
        if not (contract.is_file() and (proj / "招标解析" / "素材清单.json").is_file()
                and (proj / "招标解析" / "模板选择.json").is_file()):
            self.skipTest("真实项目数据不存在（内容契约/素材清单/模板选择缺失），跳过")
        out = Path(self.tmp) / "项目模板"
        r = run("proj-gen", "--project", REAL_PROJECT, "--out", str(out),
                "--no-baseline", "--json",
                ent="示例建设工程监理有限公司", root=r"E:\监理标书制作")
        self.assertEqual(r.returncode, 0, r.stderr)
        data = json.loads(r.stdout)
        self.assertIn("目录", data)
        self.assertTrue((Path(data["目录"]) / "生成记录.json").is_file())
        names = {f["文件"] for f in data["文件"]}
        self.assertIn("开标一览表.docx", names)
        self.assertIn("资格证明及辅助资料表.docx", names)


if __name__ == "__main__":
    unittest.main()
