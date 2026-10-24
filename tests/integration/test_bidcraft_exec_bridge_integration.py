# -*- coding: utf-8 -*-
"""执行桥（POST /api/exec）集成测试（L2）：真实起 HTTP 服务，真实调 CLI——
只读命令真实返回（tpl-design--list 模板清单、tech-layout--list 十五组）；
写命令 confirm 门禁（无 confirm 拒绝零执行，有 confirm 真出产物）；
deny 命令拒绝；路径逃逸拒绝。"""
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path
from urllib.error import HTTPError

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scripts"))

from http.server import ThreadingHTTPServer  # noqa: E402
import bidcraft_server                        # noqa: E402

REPO = Path(__file__).resolve().parents[2]
PY = sys.executable
CLI = str(REPO / "scripts" / "bidcraft.py")


def _req(url, method="POST", data=None, timeout=120):
    body = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, method=method, data=body)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


class ExecBridgeIntegrationTest(unittest.TestCase):
    """对真实素材库根（REPO）起服务，验证执行桥真实调 CLI 且门禁生效。"""

    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), bidcraft_server._Handler)
        cls.server.root = str(REPO)
        cls.server.enterprise = None
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = "http://127.0.0.1:%d" % cls.server.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def _exec(self, command, args=None, confirm=False):
        return _req(self.base + "/api/exec",
                    data={"command": command, "args": args or {}, "confirm": confirm})

    # ---- 只读命令真实执行 ----
    def test_read_tpl_design_list(self):
        status, body = self._exec("tpl-design--list")
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"], body.get("error"))
        self.assertEqual(body["mode"], "read")
        self.assertEqual(body["exit"], 0)
        self.assertIsNotNone(body.get("payload"))   # CLI --json 真实输出

    def test_read_tech_layout_list(self):
        status, body = self._exec("tech-layout--list")
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"], body.get("error"))
        # tech-layout --list 输出为文本（排版预设 + 版面范式清单）
        stdout = (body.get("output") or {}).get("stdout") or ""
        self.assertIn("版面范式", stdout)
        self.assertIn("10 种", stdout)

    def test_read_tpl_part_list(self):
        status, body = self._exec("tpl-part--list")
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"], body.get("error"))
        self.assertEqual(body["exit"], 0)

    # ---- 写命令 confirm 门禁 ----
    def test_write_requires_confirm(self):
        status, body = self._exec("m9-evidence", {"project": "不存在项目"})
        self.assertEqual(status, 200)
        self.assertFalse(body["ok"])
        self.assertIn("confirm", body["error"])
        # 门禁在参数校验之前：无 confirm 时连"项目不存在"都不该走到
        self.assertNotIn("不存在", body["error"])

    def test_write_with_confirm_bad_project(self):
        status, body = self._exec("m9-evidence", {"project": "../逃逸"}, confirm=True)
        self.assertEqual(status, 200)
        self.assertFalse(body["ok"])
        self.assertIn("参数校验", body["error"])

    # ---- deny 命令 ----
    def test_deny_command_refused(self):
        status, body = self._exec("tech-export", confirm=True)
        self.assertEqual(status, 200)
        self.assertFalse(body["ok"])
        self.assertIn("高风险", body["error"])
        self.assertIn("CLI", body["hint"])

    # ---- 样张真实产出（写 + confirm，产物落临时目录）----
    def test_specimen_with_confirm_produces_docx(self):
        # 动态取模板清单第一个模板文件名（真实数据源，不写死）
        _s, list_body = self._exec("tpl-design--list")
        self.assertTrue(list_body["ok"], list_body.get("error"))
        templates = (list_body.get("payload") or {}).get("templates") or []
        self.assertTrue(templates, "模板库应为空？")
        fname = templates[0]["file"]           # 文件名（含 .json），specimen 用它定位
        status, body = self._exec("tpl-design--specimen", {"name": fname}, confirm=True)
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"], body.get("error"))
        payload = body.get("payload") or {}
        # CLI 侧 specimen 产物：文件落临时目录并在 payload/out 中披露路径
        self.assertIn("ok", payload)
        self.assertTrue(payload.get("ok"))
        path = payload.get("file") or payload.get("path") or ""
        if path:
            self.assertTrue(Path(path).exists(), "样张 docx 应真实落盘")

    def test_specimen_without_confirm_rejected(self):
        _s, list_body = self._exec("tpl-design--list")
        templates = (list_body.get("payload") or {}).get("templates") or []
        if not templates:
            self.skipTest("模板库为空")
        status, body = self._exec("tpl-design--specimen", {"name": templates[0]["file"]})
        self.assertEqual(status, 200)
        self.assertFalse(body["ok"])
        self.assertIn("confirm", body["error"])


class ExecBridgeTenderRuleTempRootTest(unittest.TestCase):
    """tender-rule 挪入 write 白名单后的真实执行验证：
    临时软件根 + 独立 server，fixture 由 CLI（tender-init/tender-extract）准备，
    再经 HTTP /api/exec 调 tender-rule（confirm:true）——验证真实落盘 文档解析_<项目>.json。
    不污染仓库根。"""

    ENTERPRISE = "集成测试企业"
    PROJECT = "临时招标项目"

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="bidcraft_exec_tenderrule_")
        cls.root = Path(cls.tmp.name)
        cls._cli(["init-enterprise", "--name", cls.ENTERPRISE])
        cls._cli(["tender-init", "--project", cls.PROJECT])
        # 放原文并 tender-extract（通道A 规则引擎的输入）
        orig = cls.root / "招标文件.txt"
        orig.write_text(
            "第一章 招标公告\n"
            "项目编号：TMP-TR-2026-001\n"
            "最高投标限价：12.00万元\n"
            "投标截止时间：2026年12月31日 09:00\n",
            encoding="utf-8")
        cls._cli(["tender-extract", "--project", cls.PROJECT, "--file", str(orig)])
        # 起独立 server（root=临时根）
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), bidcraft_server._Handler)
        cls.server.root = str(cls.root)
        cls.server.enterprise = cls.ENTERPRISE
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = "http://127.0.0.1:%d" % cls.server.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.tmp.cleanup()

    @classmethod
    def _cli(cls, argv):
        # 全局参数（--root/--enterprise）在子命令前；argv 为 [子命令, ...] 或 [--name, ...] 等
        r = subprocess.run([PY, "-X", "utf8", CLI, "--root", str(cls.root),
                            "--enterprise", cls.ENTERPRISE] + argv,
                           capture_output=True, text=True, timeout=180,
                           cwd=str(REPO))
        if r.returncode != 0:
            raise RuntimeError("CLI 失败 %r: %s" % (argv, r.stderr[-800:]))

    def _exec(self, command, args=None, confirm=False):
        body = json.dumps({"command": command, "args": args or {}, "confirm": confirm}).encode("utf-8")
        req = urllib.request.Request(self.base + "/api/exec", data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                return r.status, json.loads(r.read().decode("utf-8"))
        except HTTPError as e:
            return e.code, json.loads(e.read().decode("utf-8"))

    def test_tender_rule_in_whitelist_and_runs(self):
        # 白名单结构：tender-rule 属 write，且不在 deny
        self.assertIn("tender-rule", bidcraft_server.EXEC_COMMANDS)
        self.assertEqual(bidcraft_server.EXEC_COMMANDS["tender-rule"]["mode"], "write")
        self.assertNotIn("tender-rule", bidcraft_server.EXEC_DENY_COMMANDS)
        # 无 confirm → 拒绝（门禁）
        status, body = self._exec("tender-rule", {"project": self.PROJECT})
        self.assertEqual(status, 200)
        self.assertFalse(body["ok"])
        self.assertIn("confirm", body["error"])
        # confirm:true → 真实执行并落盘
        status, body = self._exec("tender-rule", {"project": self.PROJECT}, confirm=True)
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"], body.get("error"))
        self.assertEqual(body["exit"], 0)
        # 产物真实落盘：<根>/<企业>/项目级/<项目>/招标解析/文档解析_<项目>.json
        tdir = self.root / self.ENTERPRISE / "项目级" / self.PROJECT / "招标解析"
        rule_p = tdir / ("文档解析_%s.json" % self.PROJECT)
        self.assertTrue(rule_p.exists(), "tender-rule 产物应真实落盘")
        self.assertIn("TMP-TR-2026-001", rule_p.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
