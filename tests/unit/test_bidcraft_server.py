# -*- coding: utf-8 -*-
"""bidcraft_server（B 方案：本地只读 HTTP 桥）单测：接口 / 数据同源 / F11 校验 / 只读边界。"""
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scripts"))

from http.server import ThreadingHTTPServer  # noqa: E402
import bidcraft_server                        # noqa: E402

REPO = Path(__file__).resolve().parents[2]


def _req(url, method="GET", timeout=10):
    req = urllib.request.Request(url, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except HTTPError as e:  # 非 2xx 也返回可解析 JSON（本服务所有响应均为 JSON）
        return e.code, json.loads(e.read().decode("utf-8"))


def _get(url, timeout=10):
    return _req(url, method="GET", timeout=timeout)


class ServerTest(unittest.TestCase):
    """对真实素材库根（REPO）起线程服务，验证数据与生成链路同源。"""

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

    # ---- 基础 ----
    def test_health(self):
        status, body = _get(self.base + "/api/health")
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])
        self.assertEqual(body["readonly"], True)

    def test_unknown_route_404(self):
        status, body = _get(self.base + "/api/nope")
        self.assertEqual(status, 404)
        self.assertFalse(body["ok"])

    def test_post_rejected(self):
        status, body = _req(self.base + "/api/layout/packs", method="POST")
        self.assertEqual(status, 405)
        self.assertFalse(body["ok"])
        self.assertIn("tech-layout", body["hint"])  # 引导走 CLI 闭环

    # ---- /api/layout/groups ----
    def test_groups_15(self):
        _s, body = _get(self.base + "/api/layout/groups")
        keys = [g["key"] for g in body["groups"]]
        self.assertEqual(len(keys), 15)
        self.assertIn("headerFooter", keys)
        self.assertIn("palette", keys)

    # ---- /api/layout/presets（与生成链路同源）----
    def test_presets_default_15_and_groups(self):
        _s, body = _get(self.base + "/api/layout/presets")
        self.assertTrue(body["ok"])
        self.assertFalse(body["fallback"])  # 真实预设文件命中
        self.assertEqual(len(body["default"]), 15)
        self.assertEqual(body["default"]["preset"], "single-column")
        self.assertEqual(len(body["groups"]), 15)
        for g in body["groups"]:
            self.assertEqual(len(body["groups"][g]), 10, g)  # 每组 10 套
        self.assertGreaterEqual(len(body["recommendedCombos"]), 5)

    # ---- /api/layout/validate（F11 同源校验）----
    def test_validate_default_ok(self):
        _s, body = _get(self.base + "/api/layout/validate")
        self.assertTrue(body["ok"])
        self.assertEqual(body["issues"], [])

    def test_validate_bad_palette(self):
        _s, body = _get(self.base + "/api/layout/validate?palette=ocean-blue")
        self.assertFalse(body["ok"])
        codes = [i["code"] for i in body["issues"]]
        self.assertIn("layout.unknown", codes)

    def test_validate_dark_requires_dark_safe(self):
        _s, body = _get(self.base + "/api/layout/validate?bidMode=" + quote("暗标"))
        self.assertFalse(body["ok"])  # 默认组合 font=gov-gongwen 违反暗标
        codes = [i["code"] for i in body["issues"]]
        self.assertIn("layout.mixfont", codes)

    def test_validate_dark_ok(self):
        url = (self.base + "/api/layout/validate?bidMode=" + quote("暗标")
               + "&font=dark-safe&imageRatio=none"
               "&pageSetup=p7-hb-25-20&headingSystem=h2-tender-arabic&tocStyle=t3-qinghai-nopage"
               "&tableStyle=tb7-dark-0.5&captionSystem=c9-dark-appendix&paragraphStyle=pa3-hebei-30"
               "&headerFooter=hf9-dark-none")
        _s, body = _get(url)
        self.assertTrue(body["ok"], body["issues"])

    # ---- /api/capabilities（项目能力清单：功能入口动态化唯一来源）----
    def test_capabilities_shape(self):
        _s, body = _get(self.base + "/api/capabilities")
        self.assertTrue(body["ok"])
        self.assertEqual(body["server"], "bidcraft-server")
        self.assertEqual(len(body["layoutGroups"]), 15)  # 与生成链路同源
        # commands：bidcraft CLI 子命令表动态提取
        names = [c["name"] for c in body["commands"]]
        self.assertIn("tech-layout", names)
        self.assertIn("tech-outline", names)
        self.assertIn("tech-export", names)
        # moduleEntries：按前缀归并，M6 应含 tech-* 命令
        m6 = next((m for m in body["moduleEntries"] if m["name"] == "M6 技术标"), None)
        self.assertIsNotNone(m6)
        self.assertIn("tech-layout", m6["commands"])
        # endpoints 覆盖自身全部只读接口
        for ep in ("/api/health", "/api/layout/presets", "/api/layout/packs", "/api/capabilities"):
            self.assertIn(ep, body["endpoints"])
        self.assertEqual(body["presetsVersion"], "1.4")  # 与预设文件实时一致


class PacksEndpointTest(unittest.TestCase):
    """/api/layout/packs：临时根下的专家包扫描（只读 manifest，不校验）。"""

    def test_packs_empty_and_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = root / "共享资源" / "技术标风格" / "专家包"
            server = ThreadingHTTPServer(("127.0.0.1", 0), bidcraft_server._Handler)
            server.root = str(root)
            server.enterprise = None
            t = threading.Thread(target=server.serve_forever, daemon=True)
            t.start()
            try:
                base_url = "http://127.0.0.1:%d" % server.server_address[1]
                _s, body = _get(base_url + "/api/layout/packs")
                self.assertEqual(body["packs"], [])  # 空根 → 空清单

                pdir = base / "custom-a-b"
                pdir.mkdir(parents=True)
                (pdir / "包.json").write_text(json.dumps({
                    "schema": "m6.expert-pack/v1", "id": "custom-a-b", "name": "自定义组合",
                    "layoutCombo": {"preset": "single-column", "palette": "steel-cyan"},
                }, ensure_ascii=False), encoding="utf-8")
                _s, body = _get(base_url + "/api/layout/packs")
                self.assertEqual(len(body["packs"]), 1)
                self.assertEqual(body["packs"][0]["id"], "custom-a-b")
                self.assertEqual(body["packs"][0]["layoutCombo"]["palette"], "steel-cyan")
            finally:
                server.shutdown()
                server.server_close()


if __name__ == "__main__":
    unittest.main()
