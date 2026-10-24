# -*- coding: utf-8 -*-
"""执行桥 e2e（L3）：真实进程起 bidcraft_server（子进程）→ HTTP 全链路：
health 状态 → capabilities 清单 → 只读命令真实执行 → 写命令 confirm 门禁 →
deny 命令拒绝 → 注入/路径逃逸拒绝 → 进程优雅停止。"""
import json
import os
import subprocess
import sys
import time
import unittest
import urllib.request
from pathlib import Path
from urllib.error import HTTPError, URLError

_HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(_HERE, "..", "..", "scripts")
REPO = Path(_HERE).resolve().parents[2]
PORT = 18765


def _wait_health(base, tries=30):
    for _ in range(tries):
        try:
            with urllib.request.urlopen(base + "/api/health", timeout=3) as r:
                return json.loads(r.read().decode("utf-8"))
        except (URLError, OSError):
            time.sleep(0.5)
    return None


class ExecBridgeE2ETest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.proc = subprocess.Popen(
            [sys.executable, "-X", "utf8", os.path.join(SCRIPTS, "bidcraft_server.py"),
             "--host", "127.0.0.1", "--port", str(PORT), "--root", str(REPO)],
            cwd=SCRIPTS, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8")
        cls.base = "http://127.0.0.1:%d" % PORT
        health = _wait_health(cls.base)
        if health is None:
            out = ""
            try:
                out = cls.proc.stdout.read() if cls.proc.stdout else ""
            except Exception:
                pass
            cls.proc.kill()
            raise RuntimeError("server 未就绪：%s" % out[:500])

    @classmethod
    def tearDownClass(cls):
        if cls.proc.poll() is None:
            cls.proc.terminate()
            try:
                cls.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                cls.proc.kill()

    def _req(self, url, method="GET", data=None, timeout=120):
        body = json.dumps(data).encode("utf-8") if data is not None else None
        req = urllib.request.Request(url, method=method, data=body)
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, json.loads(r.read().decode("utf-8"))
        except HTTPError as e:
            return e.code, json.loads(e.read().decode("utf-8"))

    def test_full_chain(self):
        # 1) health：执行桥开启
        _s, health = self._req(self.base + "/api/health")
        self.assertTrue(health["execBridge"])
        self.assertFalse(health["readonly"])
        # 2) capabilities：白名单可见
        _s, caps = self._req(self.base + "/api/capabilities")
        keys = [c["key"] for c in caps["execCommands"]]
        self.assertIn("tpl-design--list", keys)
        self.assertIn("tech-export", caps["denyCommands"])
        # 3) 只读命令真实执行（真实数据源）
        _s, body = self._req(self.base + "/api/exec", method="POST",
                             data={"command": "tpl-design--list", "args": {}, "confirm": False})
        self.assertTrue(body["ok"])
        self.assertIsNotNone(body.get("payload"))
        # 4) 写命令无 confirm 拒绝（零执行）
        _s, body = self._req(self.base + "/api/exec", method="POST",
                             data={"command": "m9-evidence", "args": {"project": "任意"},
                                   "confirm": False})
        self.assertFalse(body["ok"])
        self.assertIn("confirm", body["error"])
        # 5) deny 命令拒绝（即使 confirm）
        _s, body = self._req(self.base + "/api/exec", method="POST",
                             data={"command": "tech-export", "args": {}, "confirm": True})
        self.assertFalse(body["ok"])
        self.assertIn("高风险", body["error"])
        # 6) 路径逃逸拒绝
        _s, body = self._req(self.base + "/api/exec", method="POST",
                             data={"command": "tech-status",
                                   "args": {"project": "..\\..\\逃逸"}, "confirm": False})
        self.assertFalse(body["ok"])
        self.assertIn("参数校验", body["error"])
        # 7) 未知命令拒绝
        _s, body = self._req(self.base + "/api/exec", method="POST",
                             data={"command": "rm -rf /", "args": {}, "confirm": True})
        self.assertFalse(body["ok"])
        self.assertIn("白名单", body["error"])


if __name__ == "__main__":
    unittest.main()
