# -*- coding: utf-8 -*-
"""执行桥（bidcraft_server v3.0 POST /api/exec）单测：白名单解析 / 参数校验 / 注入拒绝 /
confirm 门禁 / deny 拒绝 / 路径边界 / 超时档位。"""
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scripts"))

from http.server import ThreadingHTTPServer  # noqa: E402
import bidcraft_server                        # noqa: E402

REPO = Path(__file__).resolve().parents[2]


def _req(url, method="POST", data=None, timeout=15):
    body = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, method=method, data=body)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


def _exec(base, command, args=None, confirm=False):
    return _req(base + "/api/exec", data={"command": command, "args": args or {},
                                          "confirm": confirm})


class ExecBridgeUnitTest(unittest.TestCase):
    """纯逻辑校验：参数校验器 / 白名单装配 / 门禁（不起服务，不执行真实命令）。"""

    def setUp(self):
        self.root = str(REPO)
        self.enterprise = None

    # ---- _simple_value 防注入 ----
    def test_simple_value_ok(self):
        for v in ("监理大纲", "custom-01", "A4-竖向", "k=v;b=2"):
            self.assertTrue(bidcraft_server._simple_value(v), v)

    def test_simple_value_rejects_path_traversal(self):
        for v in ("../x", "a/../b", "..", "x..y"):
            self.assertFalse(bidcraft_server._simple_value(v), v)

    def test_simple_value_rejects_drive_and_abs(self):
        for v in ("C:\\evil.docx", "D:/x", "/etc/passwd", "\\server\\share"):
            self.assertFalse(bidcraft_server._simple_value(v), v)

    def test_simple_value_rejects_ctrl_and_long(self):
        self.assertFalse(bidcraft_server._simple_value("a\x00b"))
        self.assertFalse(bidcraft_server._simple_value("x" * 300))

    # ---- _project_dir 目录边界 ----
    def test_project_dir_valid(self):
        # REPO 下有企业级目录结构；构造一个临时企业+项目验证
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ent = root / "执行桥单测企业"
            proj = ent / "项目级" / "示例项目"
            proj.mkdir(parents=True)
            resolved = bidcraft_server._project_dir(str(root), "执行桥单测企业", "示例项目")
            self.assertIsNotNone(resolved)
            # CI runner 的 Temp 可能解析为 8.3 短路径（RUNNER~1 vs runneradmin），两侧统一 resolve 后比较
            self.assertEqual(Path(resolved).resolve(), proj.resolve())

    def test_project_dir_rejects_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "企业A").mkdir()
            for bad in ("../企业A", "..", "企业A/../项目级"):
                self.assertIsNone(bidcraft_server._project_dir(str(root), "企业A", bad), bad)

    def test_project_dir_rejects_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "企业A").mkdir()
            self.assertIsNone(bidcraft_server._project_dir(str(root), "企业A", "不存在项目"))

    # ---- _validate_exec_args 装配 ----
    def test_assembly_read_command(self):
        entry = bidcraft_server.EXEC_COMMANDS["tpl-design--show"]
        argv, err = bidcraft_server._validate_exec_args(entry, {"name": "示例模板"}, self.root, None)
        self.assertIsNone(err)
        self.assertEqual(argv, ["tpl-design", "--show", "示例模板"])

    def test_assembly_write_with_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            proj = root / "企业X" / "项目级" / "项目甲"
            proj.mkdir(parents=True)
            entry = bidcraft_server.EXEC_COMMANDS["m9-verify"]
            argv, err = bidcraft_server._validate_exec_args(entry, {"project": "项目甲"},
                                                            str(root), "企业X")
            self.assertIsNone(err)
            # CLI 契约：--project 传「项目名」（目录存在性已校验），不是绝对路径
            self.assertEqual(argv, ["m9-verify", "--project", "项目甲"])

    def test_assembly_rejects_bad_project(self):
        entry = bidcraft_server.EXEC_COMMANDS["tech-status"]
        argv, err = bidcraft_server._validate_exec_args(entry, {"project": "../逃逸"}, self.root, None)
        self.assertIsNotNone(err)
        self.assertIn("__INVALID__", argv)

    def test_assembly_optional_omitted(self):
        entry = bidcraft_server.EXEC_COMMANDS["tech-layout--preview"]
        argv, err = bidcraft_server._validate_exec_args(entry, {}, self.root, None)
        self.assertIsNone(err)
        self.assertEqual(argv, ["tech-layout", "--preview"])

    def test_assembly_optional_fill(self):
        entry = bidcraft_server.EXEC_COMMANDS["tpl-design--specimen"]
        argv, err = bidcraft_server._validate_exec_args(entry, {"name": "模板1", "fill": "a=1;b=2"},
                                                        self.root, None)
        self.assertIsNone(err)
        self.assertEqual(argv, ["tpl-design", "--specimen", "模板1", "--fill", "a=1;b=2"])

    # ---- 白名单结构 ----
    def test_whitelist_modes(self):
        for key, entry in bidcraft_server.EXEC_COMMANDS.items():
            self.assertIn(entry["mode"], ("read", "write"))
            self.assertGreater(entry["timeout"], 0)
            self.assertIn("cmd", entry)

    def test_deny_commands_disjoint_from_whitelist(self):
        self.assertFalse(bidcraft_server.EXEC_DENY_COMMANDS & set(bidcraft_server.EXEC_COMMANDS))

    def test_high_risk_commands_are_denied(self):
        for cmd in ("tech-export", "fill-tpl", "remedy-archive", "tpl-design--apply",
                    "tpl-part--scan", "tech-layout--apply", "tech-report", "assets-archive"):
            self.assertIn(cmd, bidcraft_server.EXEC_DENY_COMMANDS, cmd)


class ExecBridgeHttpTest(unittest.TestCase):
    """HTTP 层门禁（不起 CLI 真实执行：只验证 403/400/参数分支在响应层的行为）。"""

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

    def test_exec_unknown_command_403(self):
        status, body = _exec(self.base, "nope-cmd")
        self.assertEqual(status, 200)
        self.assertFalse(body["ok"])
        self.assertIn("白名单", body["error"])

    def test_exec_denied_command_403(self):
        status, body = _exec(self.base, "tech-export")
        self.assertEqual(status, 200)
        self.assertFalse(body["ok"])
        self.assertIn("高风险", body["error"])
        self.assertIn("hint", body)

    def test_exec_write_without_confirm_403(self):
        status, body = _exec(self.base, "m9-evidence", {"project": "任意项目"})
        self.assertEqual(status, 200)
        self.assertFalse(body["ok"])
        self.assertIn("confirm", body["error"])

    def test_exec_bad_json_400(self):
        req = urllib.request.Request(self.base + "/api/exec", method="POST", data=b"{oops",
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                status, body = r.status, json.loads(r.read().decode("utf-8"))
        except HTTPError as e:
            status, body = e.code, json.loads(e.read().decode("utf-8"))
        self.assertEqual(status, 400)
        self.assertFalse(body["ok"])

    def test_exec_empty_body_400(self):
        req = urllib.request.Request(self.base + "/api/exec", method="POST", data=b"")
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                status = r.status
        except HTTPError as e:
            status = e.code
        self.assertEqual(status, 400)

    def test_put_delete_still_405(self):
        for method in ("PUT", "DELETE", "PATCH"):
            req = urllib.request.Request(self.base + "/api/layout/packs", method=method)
            try:
                with urllib.request.urlopen(req, timeout=10) as r:
                    status = r.status
            except HTTPError as e:
                status = e.code
            self.assertEqual(status, 405, method)

    def test_capabilities_lists_exec(self):
        req = urllib.request.Request(self.base + "/api/capabilities", method="GET")
        with urllib.request.urlopen(req, timeout=10) as r:
            body = json.loads(r.read().decode("utf-8"))
        keys = [c["key"] for c in body["execCommands"]]
        self.assertIn("tpl-design--list", keys)
        self.assertIn("m9-evidence", keys)
        m9 = next(c for c in body["execCommands"] if c["key"] == "m9-evidence")
        self.assertEqual(m9["mode"], "write")
        self.assertTrue(m9["confirmRequired"])
        self.assertIn("tech-export", body["denyCommands"])


if __name__ == "__main__":
    unittest.main()
