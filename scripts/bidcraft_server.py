#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
bidcraft · 本地只读 HTTP 桥（B 方案：UI/平台工具 ↔ CLI 的只读代理）

职责：只提供**只读**接口（组合清单 / 预设 / F11 校验 / 专家包清单），供
  - 版面设计器-工作台V1.html 等前端 fetch 实时取数；
  - 豆包「已注册工具」/ WorkBuddy「自定义技能」等平台侧以 HTTP 方式调用（须自行完成平台鉴权包装）。

边界（安全设计）：
  - 默认只绑定 127.0.0.1（--host 0.0.0.0 仅内网使用，需自行加鉴权）；
  - **不执行任何写操作**：写/生成一律 405，提示走 CLI + 人工确认闸门——
    `python scripts/bidcraft.py tech-layout --apply-combo <json> --confirm` 等；
  - 数据源与本项目生成链路同源：共享级 `layout-presets.json`（缺失回退内置清单，响应标注 fallback）。

用法：
  python scripts/bidcraft_server.py [--host 127.0.0.1] [--port 8765] [--root <软件根>] [--enterprise <企业>]

接口（全部 GET，返回 JSON）：
  /api/health               存活检查
  /api/layout/groups        十五组（key+中文标签）
  /api/layout/presets       预设全文精简：source/fallback/default/recommendedCombos/groups
  /api/layout/validate?<key>=<id>&...   十五组 id F11 校验（缺省回填默认；bidMode=明标|暗标）
  /api/layout/packs         专家包清单（id/name/description/layoutCombo/bidType）
  /api/capabilities         项目能力清单（动态）：layoutGroups / commands / moduleEntries / endpoints / presetsVersion
"""

import argparse
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit, parse_qs

# 保证 scripts/ 可被导入（与 bidcraft.py 相同的路径处理）
sys.path.insert(0, str(Path(__file__).resolve().parent))

from m6_tech import layout as m6layout          # noqa: E402
from m6_tech import sources                     # noqa: E402
from m6_tech.rules_chapters import validate_layout  # noqa: E402

try:  # Windows 控制台中文输出
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

SERVER_NAME = "bidcraft-server"
SERVER_VERSION = "2.0"
PACK_BASE_REL = Path("共享资源") / "技术标风格" / "专家包"
# 命令前缀 → 模块归属（能力清单的 moduleEntries 推导依据；随项目扩展在此增行即可，UI 入口自动长出来）
MODULE_PREFIX = (
    ("env", "M0 环境体检"), ("asset", "M1 素材库"), ("tpl", "M2 模板库"),
    ("tender", "M4 招标解析"), ("fill", "M5 商务标"), ("proj", "M5 商务标"),
    ("tech", "M6 技术标"), ("check", "M7 标书检查"), ("eval", "M8 模拟评标"),
    ("remedy", "M10 失分补救"), ("docx", "共享 docx 工具"),
)
ENDPOINTS = (
    "/api/health", "/api/layout/groups", "/api/layout/presets",
    "/api/layout/validate", "/api/layout/packs", "/api/capabilities",
)
WRITE_HINT = ("bidcraft server 为只读代理，不执行写操作；写/生成请走 CLI 并保留人工确认闸门："
              "python scripts/bidcraft.py tech-layout --apply-combo <组合补丁.json> --confirm（生成专家包）/"
              "tech-outline --project <项目> --file <草案.json> --expert-pack <id> --confirm（章节树落盘）/"
              "tech-export --confirm（docx 导出）")


def _make_args(root, enterprise):
    """构造 layout.* 需要的命令行命名空间（args.root / args.enterprise / args.confirm 等惰性字段）。"""
    return SimpleNamespace(
        root=root,
        enterprise=enterprise or None,
        confirm=False, json=True, preview="", apply_combo="", pack_id="",
    )


class _Handler(BaseHTTPRequestHandler):
    server_version = "bidcraft-server/1.0"

    # ---- 基础 ----------------------------------------------------------
    def log_message(self, fmt, *args):  # 简短请求日志
        print("[req] %s %s" % (self.command, self.path), flush=True)

    def _send(self, code, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        # 只读接口；跨域仅限本机/内网场景（--host 0.0.0.0 时自行加鉴权）
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):  # CORS preflight
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        split = urlsplit(self.path)
        path, query = split.path, parse_qs(split.query)
        try:
            if path == "/api/health":
                self._send(200, {"ok": True, "server": SERVER_NAME,
                                 "version": SERVER_VERSION,
                                 "readonly": True})
            elif path == "/api/layout/groups":
                self._send(200, {"ok": True,
                                 "groups": [{"key": k, "label": v} for k, v in m6layout.GROUPS]})
            elif path == "/api/layout/presets":
                self._send(200, self._presets())
            elif path == "/api/layout/validate":
                self._send(200, self._validate(query))
            elif path == "/api/layout/packs":
                self._send(200, self._packs())
            elif path == "/api/capabilities":
                self._send(200, self._capabilities())
            else:
                self._send(404, {"ok": False, "error": "未知接口：%s（可用：/api/health /api/layout/groups "
                                                        "/api/layout/presets /api/layout/validate /api/layout/packs "
                                                        "/api/capabilities）" % path})
        except Exception as e:  # noqa: BLE001 —— 兜底，保证响应始终是 JSON
            self._send(500, {"ok": False, "error": "%s: %s" % (type(e).__name__, e)})

    def do_POST(self):
        self._send(405, {"ok": False, "error": "该接口只读，不支持写操作", "hint": WRITE_HINT})

    do_PUT = do_DELETE = do_PATCH = do_POST

    # ---- 业务 ----------------------------------------------------------
    def _presets(self):
        args = _make_args(self.server.root, self.server.enterprise)
        path = m6layout.find_presets(args)
        doc = m6layout.load_presets(args)
        fallback = doc is None
        groups = {g: m6layout.entries(doc, g) for g, _ in m6layout.GROUPS}
        payload = {
            "ok": True, "source": str(path) if path else "", "fallback": fallback,
            "schema": m6layout.PRESETS_SCHEMA, "version": (doc or {}).get("version", ""),
            "default": m6layout.default_entry(doc),
            "recommendedCombos": (doc or {}).get("recommendedCombos", []),
            "fontDefaults": (doc or {}).get("fontDefaults", {}),
            "darkInject": dict(sources.DARK_LAYOUT_INJECT),
            "groups": groups,
        }
        return payload

    def _validate(self, query):
        args = _make_args(self.server.root, self.server.enterprise)
        doc = m6layout.load_presets(args)
        defaults = m6layout.default_entry(doc)
        combo = {}
        for g, _label in m6layout.GROUPS:
            vals = query.get(g)
            combo[g] = (vals[0] if vals else "").strip() or defaults.get(g, "")
        bid_mode = (query.get("bidMode") or [""])[0].strip() or "明标"
        ok, issues = validate_layout(combo, doc, bid_mode)
        return {"ok": ok, "bidMode": bid_mode, "layout": combo,
                "issues": issues, "fallback": doc is None}

    def _packs(self):
        args = _make_args(self.server.root, self.server.enterprise)
        base = sources.lib_root(args) / PACK_BASE_REL
        out, errors = [], []
        if base.is_dir():
            for pdir in sorted(base.iterdir()):
                mf = pdir / "包.json"
                if not mf.is_file():
                    continue
                try:
                    manifest = json.loads(mf.read_text(encoding="utf-8"))
                except (OSError, ValueError) as e:
                    errors.append({"id": pdir.name, "error": "%s: %s" % (type(e).__name__, e)})
                    continue
                out.append({
                    "id": manifest.get("id", pdir.name),
                    "name": manifest.get("name", ""),
                    "description": manifest.get("description", ""),
                    "bidType": manifest.get("bidType", []),
                    "layoutCombo": manifest.get("layoutCombo", {}),
                })
        payload = {"ok": True, "base": str(base), "packs": out, "errors": errors}
        return payload

    def _capabilities(self):
        """项目能力清单（动态）：UI「功能入口」与实时状态的唯一来源。
        commands 由 bidcraft CLI 的 argparse 子命令表推导——新增命令自动出现在清单里；
        moduleEntries 按命令前缀归并；layoutGroups 来自 layout.GROUPS。"""
        commands, module_map = [], {}
        try:
            import bidcraft  # 惰性导入：仅本接口触发全量模块加载
            parser = bidcraft.build_parser()
            # argparse 3.11+：p._subparsers 是子命令分组（_ArgumentGroup），
            # 真正的 _SubParsersAction 在其 _group_actions 中（含 _choices_actions 命令表）
            sp = next(a for a in parser._subparsers._group_actions  # noqa: SLF001
                      if hasattr(a, "_choices_actions"))
            for act in sp._choices_actions:  # noqa: SLF001
                name, help_text = act.dest, act.help or ""
                commands.append({"name": name, "help": help_text})
                for prefix, mod in MODULE_PREFIX:
                    if name.startswith(prefix + "-"):
                        module_map.setdefault(mod, []).append(name)
                        break
                else:
                    module_map.setdefault("其他", []).append(name)
        except Exception as e:  # noqa: BLE001 —— 命令表解析失败不拖垮整个接口
            commands, module_map = [], {"其他": []}
            commands_error = "%s: %s" % (type(e).__name__, e)
        module_entries = [{"id": mod, "name": mod, "commands": sorted(names)}
                          for mod, names in sorted(module_map.items())]
        args = _make_args(self.server.root, self.server.enterprise)
        doc = m6layout.load_presets(args)
        payload = {
            "ok": True,
            "server": SERVER_NAME, "serverVersion": SERVER_VERSION,
            "presetsVersion": (doc or {}).get("version", ""),
            "layoutGroups": [{"key": k, "label": v} for k, v in m6layout.GROUPS],
            "commands": commands,
            "moduleEntries": module_entries,
            "endpoints": list(ENDPOINTS),
            "commandsError": commands_error if "commands_error" in dir() else None,
        }
        return payload


def main(argv=None):
    p = argparse.ArgumentParser(prog="bidcraft_server", description="bidcraft 本地只读 HTTP 桥（B 方案）")
    p.add_argument("--host", default="127.0.0.1", help="监听地址（默认 127.0.0.1；0.0.0.0 仅限内网且需自行鉴权）")
    p.add_argument("--port", type=int, default=8765, help="监听端口（默认 8765）")
    p.add_argument("--root", help="软件根目录（默认：BIDCRAFT_LIB_ROOT 或 ./素材库）")
    p.add_argument("--enterprise", help="企业目录名")
    args = p.parse_args(argv)

    server = ThreadingHTTPServer((args.host, args.port), _Handler)
    server.root = args.root
    server.enterprise = args.enterprise
    url = "http://%s:%d" % ("127.0.0.1" if args.host in ("0.0.0.0", "::") else args.host, server.server_address[1])
    print("bidcraft-server 只读桥已启动：%s" % url)
    print("只读接口：/api/health /api/layout/groups /api/layout/presets /api/layout/validate /api/layout/packs /api/capabilities")
    print("写操作一律走 CLI（本服务 405 拒绝）。Ctrl+C 停止。")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
        server.server_close()


if __name__ == "__main__":
    main()
