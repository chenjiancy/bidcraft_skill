# -*- coding: utf-8 -*-
"""
B. 标书匠 UI 本地联调桥（本地模式 CLI 调用链）

单文件 HTML 无法直接执行 Python CLI；本桥在 127.0.0.1 上提供两个端点，
让 UI（file:// 打开亦可，CORS 放开）真正执行 scripts/bidcraft.py 并读回产物路径。

端点：
  GET  /health            → {"ok":true,"root":<软件根>}
  POST /exec              → body {"cmd":[<argv...>], "root":<软件根 可选>}
                             执行 subprocess: python scripts/bidcraft.py <argv>
                             返回 {"code":0,"out":...,"err":...,"artifacts":[产物路径...]}

用法：
  python dev/prototypes/ui_cli_bridge.py [--port 8765] [--root E:\\bidcraft_skill]
"""
import argparse
import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PY = sys.executable
SCRIPT = REPO / "scripts" / "bidcraft.py"


class Handler(BaseHTTPRequestHandler):
    server_version = "bidcraft-bridge/1.0"

    def _send(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self._send({}, 204)

    def do_GET(self):
        if self.path.startswith("/health"):
            return self._send({"ok": True, "root": str(REPO), "script": str(SCRIPT)})
        self._send({"ok": False, "error": "not found"}, 404)

    def do_POST(self):
        if not self.path.startswith("/exec"):
            return self._send({"ok": False, "error": "not found"}, 404)
        try:
            n = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
        except Exception as e:
            return self._send({"ok": False, "error": "bad json: %s" % e}, 400)
        cmd = payload.get("cmd") or []
        if not isinstance(cmd, list) or not cmd:
            return self._send({"ok": False, "error": "cmd 需为非空数组，如 ['tech-status','--project','X']"}, 400)
        root = payload.get("root") or str(REPO)
        argv = [PY, str(SCRIPT)]
        if payload.get("enterprise"):
            argv += ["--enterprise", str(payload["enterprise"])]
        argv += [str(a) for a in cmd]
        try:
            proc = subprocess.run(argv, cwd=root, capture_output=True, timeout=300, encoding="utf-8", errors="replace")
            artifacts = self._collect_artifacts(cmd, root)
            return self._send({"ok": True, "code": proc.returncode,
                               "out": proc.stdout, "err": proc.stderr,
                               "artifacts": artifacts})
        except subprocess.TimeoutExpired:
            return self._send({"ok": False, "error": "命令超时（>300s）"}, 504)
        except Exception as e:
            return self._send({"ok": False, "error": "exec 失败: %s" % e}, 500)

    @staticmethod
    def _collect_artifacts(cmd, root):
        """按命令类型回读产物路径（与 M6 契约产物目录一致）。"""
        root_p = Path(root)
        arts = []
        name = cmd[0] if cmd else ""
        if name in ("tech-export", "tech-report"):
            project = ""
            if "--project" in cmd:
                project = cmd[cmd.index("--project") + 1] if cmd.index("--project") + 1 < len(cmd) else ""
            if project:
                tech = root_p / "项目级" / project / "技术标"
                out_d = tech / "产出"
                for f in sorted(out_d.glob("技术标_*.docx")) if out_d.exists() else []:
                    arts.append(str(f))
                rep = tech / "检查"
                for f in sorted(rep.glob("技术标检查报告_*.html")) if rep.exists() else []:
                    arts.append(str(f))
        elif name == "tech-status":
            arts.append(str(root_p / "项目级"))
        return arts

    def log_message(self, fmt, *args):
        sys.stderr.write("bridge %s\n" % (fmt % args))


def main():
    ap = argparse.ArgumentParser(description="标书匠 UI 本地联调桥")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--root", default=str(REPO), help="软件根（默认 %(default)s）")
    args = ap.parse_args()
    httpd = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print("标书匠 UI 联调桥已启动：http://127.0.0.1:%d （root=%s）" % (args.port, args.root))
    print("  GET /health | POST /exec {\"cmd\":[...]}   Ctrl+C 退出")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
