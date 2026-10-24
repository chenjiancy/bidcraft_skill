#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
bidcraft · 本地 HTTP 桥 v3.0（只读接口 + 执行桥）

职责：两层接口
  1. **只读接口**（GET）：组合清单 / 预设 / F11 校验 / 专家包 / 模板清单等，供
     版面设计器-工作台V1.html 等前端 fetch 实时取数；
  2. **执行桥**（POST /api/exec）：在**白名单**内真实调用 bidcraft CLI 命令，
     让 UI 具备真实功能（点按钮真跑命令、真出产物），同时守住安全边界：
     只读命令无需确认；写命令必须带 `confirm: true`（由 UI 上的人工确认产生）；
     白名单外命令一律拒绝并引导走 CLI 人工闸门。

边界（安全设计）：
  - 默认只绑定 127.0.0.1（--host 0.0.0.0 仅内网使用，需自行加鉴权）；
  - **白名单唯一入口**：EXEC_COMMANDS 之外任何命令 403；
  - **参数校验**：命令参数走 subprocess 列表传参（无 shell 拼接）；项目名/模板名等
    值经防注入校验（拒绝 `..`、盘符、绝对路径、控制字符、超长）；
  - **写操作确认闸门**：mode=write 命令必须 `confirm:true`，否则 403；
  - **高风险命令永不暴露**：应用类/覆盖类/删除类（fill-tpl、tech-export、
    remedy-archive --apply、tpl-design --apply 等）只走 CLI + 人工确认闸门；
  - 数据源与本项目生成链路同源：共享级 `layout-presets.json`（缺失回退内置清单，响应标注 fallback）。

用法：
  python scripts/bidcraft_server.py [--host 127.0.0.1] [--port 8765] [--root <软件根>] [--enterprise <企业>]

接口（只读全部 GET，返回 JSON）：
  /api/health               存活检查（含 execBridge 状态）
  /api/layout/groups        十五组（key+中文标签）
  /api/layout/presets       预设全文精简：source/fallback/default/recommendedCombos/groups
  /api/layout/validate?<key>=<id>&...   十五组 id F11 校验（缺省回填默认；bidMode=明标|暗标）
  /api/layout/packs         专家包清单（id/name/description/layoutCombo/bidType）
  /api/capabilities         项目能力清单（动态）：layoutGroups / commands / moduleEntries / endpoints / presetsVersion / execCommands
  /api/template/list        模板清单 + 校验状态（tpl-design --list --json 机读）
  /api/template/show?name=X   模板详情（structure/styleRef/placeholders/rules + 暗标派生 15 组 + 校验）
  /api/template/validate?name=X   模板校验问题清单（err/warn；写操作仍走执行桥/CLI）
  /api/template/parts       部件库清单（tpl-part --list --json）
  /api/template/specimen?name=X[&fill=k=v;…]   出样张到临时目录（只读派生，不写项目/模板库）

接口（执行桥 POST /api/exec）：
  body: {"command": "<白名单命令 key>", "args": {"name": "...", "project": "...", "fill": "..."}, "confirm": false}
  响应: {"ok": true, "command": ..., "mode": "read|write", "exit": 0, "payload": {...}|null, "output": {"stdout": ..., "stderr": ...}}
  白名单与说明见 EXEC_COMMANDS；高风险命令清单见 EXEC_DENY_COMMANDS（供 UI 展示）。
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
SERVER_VERSION = "3.2"
EXEC_BRIDGE_VERSION = "3.2"
PACK_BASE_REL = Path("共享资源") / "技术标风格" / "专家包"

# ---- 执行桥：白名单（唯一入口）------------------------------------------
# mode: read=无需确认；write=必须 confirm:true（人工确认闸门）
# json: True=追加 --json 并解析 payload；False=原样返回 stdout 文本
# cmd: "@name"/"@project"/"@fill" 等占位由请求 args 填充；项目名额外做目录边界校验
EXEC_COMMANDS = {
    # —— 只读（UI 实时取数/查询，无副作用）——
    "tpl-design--list":     {"mode": "read",  "json": True,  "timeout": 120, "cmd": ["tpl-design", "--list"]},
    "tpl-design--show":     {"mode": "read",  "json": True,  "timeout": 120, "cmd": ["tpl-design", "--show", "@name"]},
    "tpl-design--validate": {"mode": "read",  "json": True,  "timeout": 120, "cmd": ["tpl-design", "--validate", "@name"]},
    "tpl-part--list":       {"mode": "read",  "json": True,  "timeout": 120, "cmd": ["tpl-part", "--list"]},
    "tpl-part--show":       {"mode": "read",  "json": True,  "timeout": 120, "cmd": ["tpl-part", "--show", "@name"]},
    "tech-layout--list":    {"mode": "read",  "json": False, "timeout": 120, "cmd": ["tech-layout", "--list"]},
    "tech-status":          {"mode": "read",  "json": False, "timeout": 120, "cmd": ["tech-status", "--project", "@project"]},
    "img-status":           {"mode": "read",  "json": True,  "timeout": 120, "cmd": ["img-status", "--project", "@project", "--json"]},
    "img-audit":            {"mode": "read",  "json": True,  "timeout": 120, "cmd": ["img-audit", "--project", "@project", "--json"]},
    "mat-status":           {"mode": "read",  "json": True,  "timeout": 120, "cmd": ["mat-status", "--project", "@project", "--json"]},
    # —— 写（可逆产物，必须 confirm:true；样张/体检/留痕/报告）——
    "img-plan":             {"mode": "write", "json": False, "timeout": 120, "cmd": ["img-plan", "--project", "@project"]},
    "img-gen-agent":        {"mode": "write", "json": False, "timeout": 900, "cmd": ["img-gen-agent", "--project", "@project", "--id", "@id"]},
    "img-save--temp":       {"mode": "write", "json": False, "timeout": 120, "cmd": ["img-save", "--project", "@project", "--id", "@id", "--temp", "@file"],
                             "optional": [("--source", "@source")]},
    "img-embed":            {"mode": "write", "json": True,  "timeout": 120, "cmd": ["img-embed", "--project", "@project", "--json"]},
    "tpl-design--specimen": {"mode": "write", "json": True,  "timeout": 300, "cmd": ["tpl-design", "--specimen", "@name"],
                             "optional": [("--fill", "@fill")]},
    "tech-layout--preview": {"mode": "write", "json": False, "timeout": 300, "cmd": ["tech-layout", "--preview"],
                             "optional": [("--project", "@project"), ("--enterprise", "@enterprise")]},
    "m9-verify":            {"mode": "write", "json": False, "timeout": 300, "cmd": ["m9-verify", "--project", "@project"]},
    "m9-evidence":          {"mode": "write", "json": False, "timeout": 300, "cmd": ["m9-evidence", "--project", "@project"]},
    "tender-report":        {"mode": "write", "json": False, "timeout": 300, "cmd": ["tender-report", "--project", "@project"]},
    "tender-rule":          {"mode": "write", "json": False, "timeout": 300, "cmd": ["tender-rule", "--project", "@project"]},
    "tender-agent-parse":   {"mode": "write", "json": False, "timeout": 900, "cmd": ["tender-agent-parse", "--project", "@project"]},
}

# 高风险命令清单（说明性 + capabilities 展示）：应用/覆盖/删除/状态推进类——
# 永不通过执行桥暴露，只走 CLI + 人工确认闸门（如 --confirm / --apply / upload / trash / rm）
EXEC_DENY_COMMANDS = frozenset((
    "tpl-design--apply", "tpl-part--scan", "tech-layout--apply", "tech-export", "tech-outline",
    "tech-report", "tech-parse", "tech-rewrite", "tech-ctx", "tender-parse", "tender-diff",
    "tender-annex", "tender-gap", "tender-extract", "tender-fmt", "tender-check",
    "tender-show", "fill-tpl", "remedy-gen", "remedy-done", "remedy-archive", "assets-archive",
    "asset-upload", "asset-propose", "asset-apply", "asset-trash", "asset-rm-project",
    "asset-cleanup-trash", "asset-reconcile", "docx-read", "docx-audit",
))
EXEC_OUTPUT_LIMIT = 20000   # stdout/stderr 截断，防大输出拖垮 UI
EXEC_MAX_BODY = 65536       # POST body 上限

# 命令 key → 描述（capabilities 展示用）
EXEC_DESCRIPTIONS = {
    "tpl-design--list": "模板清单（模板设计器）", "tpl-design--show": "模板详情（含暗标派生）",
    "tpl-design--validate": "模板校验问题清单", "tpl-design--specimen": "出模板样张 docx",
    "tpl-part--list": "部件库清单", "tpl-part--show": "部件内容",
    "tech-layout--list": "排版预设清单（十五组×10套）", "tech-layout--preview": "排版样张 docx 预览",
    "tech-status": "技术标写作状态表", "m9-verify": "项目自检体检（红绿灯）",
    "m9-evidence": "投标留痕包（取证链）", "tender-report": "投标要点 HTML 报告",
    "tender-rule": "通道A 文档解析（规则引擎落盘，write 需确认）",
    "tender-agent-parse": "通道B 语义解析（agent 桥·CodeBuddy CLI，耗时长，write 需确认）",
    "img-plan": "AI 配图：生成/合并配图清单（write 需确认）",
    "img-gen-agent": "AI 配图：CodeBuddy ImageGen 生图→临时区（write 需确认，耗时长）",
    "img-save--temp": "AI 配图：临时区图片校验归档回填（write 需确认）",
    "img-embed": "AI 配图：技术标正文嵌入（write 需确认；saved 项按 section 匹配章节树插入引用，幂等）",
    "img-status": "AI 配图：配图清单状态（只读）",
    "img-audit": "AI 配图：技术标暗标合规审计（只读：文件存在/AIGC 残留/红线词/source；无 OCR 披露人工核验）",
    "mat-status": "素材清单状态（配图通道视角，只读：类别聚合+对照+图片类标注）",
}


def _simple_value(value, maxlen=200):
    """执行桥参数值基础校验：拒绝路径穿越/盘符/绝对路径/控制字符/超长。"""
    if not isinstance(value, str) or not value:
        return False
    if len(value) > maxlen:
        return False
    if ".." in value:
        return False
    if value.startswith(("/", "\\")):
        return False
    if len(value) >= 2 and value[1] == ":":
        return False
    if any(ord(ch) < 32 for ch in value):
        return False
    return True


def _resolve_enterprise_root(root, enterprise):
    """企业根 = <软件根>/<企业>（与 CLI 同一实现：core.Library.resolve；
    单企业时 enterprise 可为 None，自动解析唯一企业）。"""
    from _shared.core.lib import Library
    return Library(Path(root)).resolve(enterprise)


def _project_dir(root, enterprise, value):
    """项目名校验：必须是 <企业根>/项目级/<项目名> 下真实存在的目录；返回绝对路径或 None。"""
    if not _simple_value(value):
        return None
    try:
        base = Path(_resolve_enterprise_root(root, enterprise)).resolve()
        proj = (base / "项目级" / value).resolve()
    except Exception:  # noqa: BLE001 —— 企业缺失/多企业未指定等统一视为校验失败
        return None
    if proj != base and str(proj).startswith(str(base)):
        return str(proj) if proj.is_dir() else None
    return None


def _validate_exec_args(entry, args, root, enterprise):
    """校验并装配执行命令参数。cmd 模板中 @key 原位替换为校验值；
    optional 追加到尾部（可省略）。返回 (argv, error|None)。
    @project 必须过目录边界；@name/@fill 过简单值校验。"""
    argv, errors = [], []
    for tok in entry["cmd"]:
        if not tok.startswith("@"):
            argv.append(tok)
            continue
        key = tok[1:]
        val = (args or {}).get(key)
        if key == "project":
            # 安全校验：目录真实存在且在企业根/项目级 边界内（用解析结果验证）；
            # CLI 契约：--project 传「项目名」而非绝对路径（validate_project_name 校验的是名字）
            resolved = _project_dir(root, enterprise, val) if val else None
            if resolved is None:
                errors.append("project 参数非法或不存在（须为 <企业根>/项目级/ 下的真实项目目录）")
                argv.append("__INVALID__")
            else:
                argv.append(val)
        else:
            if not _simple_value(val):
                errors.append("%s 参数非法（拒绝路径穿越/盘符/绝对路径/控制字符）" % key)
                argv.append("__INVALID__")
            else:
                argv.append(val)
    for flag, tok in entry.get("optional", ()):
        val = (args or {}).get(tok[1:])
        if not val:
            continue
        if tok[1:] == "project":
            resolved = _project_dir(root, enterprise, val)
            if resolved is None:
                errors.append("project 参数非法或不存在")
                argv += [flag, "__INVALID__"]
            else:
                argv += [flag, val]
        else:
            if not _simple_value(val):
                errors.append("%s 参数非法" % tok[1:])
                argv += [flag, "__INVALID__"]
            else:
                argv += [flag, val]
    return argv, ("；".join(errors) if errors else None)

# 命令前缀 → 模块归属（能力清单的 moduleEntries 推导依据；随项目扩展在此增行即可，UI 入口自动长出来）
MODULE_PREFIX = (
    ("env", "M0 环境体检"), ("asset", "M1 素材库"), ("tpl", "M2 模板库"),
    ("tender", "M4 招标解析"), ("fill", "M5 商务标"), ("proj", "M5 商务标"),
    ("tech", "M6 技术标"), ("check", "M7 标书检查"), ("eval", "M8 模拟评标"),
    ("remedy", "M10 失分补救"), ("docx", "共享 docx 工具"),
    ("img", "AI 配图"),
)
ENDPOINTS = (
    "/api/health", "/api/layout/groups", "/api/layout/presets",
    "/api/layout/validate", "/api/layout/packs", "/api/capabilities",
    "/api/template/list", "/api/template/show", "/api/template/validate",
    "/api/template/parts", "/api/template/specimen", "/api/exec",
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
                                 "readonly": False, "execBridge": True,
                                 "execCommands": sorted(EXEC_COMMANDS),
                                 "denyCommands": sorted(EXEC_DENY_COMMANDS)})
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
            elif path == "/api/template/list":
                self._send(200, self._template_list())
            elif path == "/api/template/show":
                self._send(200, self._template_show(query))
            elif path == "/api/template/validate":
                self._send(200, self._template_validate(query))
            elif path == "/api/template/parts":
                self._send(200, self._template_parts())
            elif path == "/api/template/specimen":
                self._send(200, self._template_specimen(query))
            else:
                self._send(404, {"ok": False, "error": "未知接口：%s（可用：/api/health /api/layout/groups "
                                                        "/api/layout/presets /api/layout/validate /api/layout/packs "
                                                        "/api/capabilities /api/template/list /api/template/show "
                                                        "/api/template/validate /api/template/parts "
                                                        "/api/template/specimen）" % path})
        except Exception as e:  # noqa: BLE001 —— 兜底，保证响应始终是 JSON
            self._send(500, {"ok": False, "error": "%s: %s" % (type(e).__name__, e)})

    def do_POST(self):
        split = urlsplit(self.path)
        if split.path != "/api/exec":
            self._send(405, {"ok": False, "error": "该接口只读，不支持写操作", "hint": WRITE_HINT})
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0 or length > EXEC_MAX_BODY:
                self._send(400, {"ok": False, "error": "请求体缺失或超过 %d 字节上限" % EXEC_MAX_BODY})
                return
            body = self.rfile.read(length)
            try:
                payload = json.loads(body.decode("utf-8"))
            except (UnicodeDecodeError, ValueError):
                self._send(400, {"ok": False, "error": "请求体不是合法 JSON"})
                return
            self._send(200, self._exec(payload))
        except Exception as e:  # noqa: BLE001 —— 兜底，保证响应始终是 JSON
            self._send(500, {"ok": False, "error": "%s: %s" % (type(e).__name__, e)})

    def do_PUT(self):
        self._send(405, {"ok": False, "error": "仅支持 GET（只读接口）与 POST /api/exec（执行桥）"})

    def do_DELETE(self):
        self._send(405, {"ok": False, "error": "仅支持 GET（只读接口）与 POST /api/exec（执行桥）"})

    def do_PATCH(self):
        self._send(405, {"ok": False, "error": "仅支持 GET（只读接口）与 POST /api/exec（执行桥）"})

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

    # ---- P3 模板设计器（/api/template/*）---------------------------------
    def _cli_json(self, args_list):
        """subprocess 调 bidcraft CLI（--json），返回 (payload, error)。单一事实源=CLI。"""
        import subprocess
        cli = str(Path(__file__).resolve().parent / "bidcraft.py")
        cmd = [sys.executable, "-X", "utf8", cli, "--root", str(self.server.root or ""),
               "--enterprise", (self.server.enterprise or "")] + args_list + ["--json"]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                               timeout=120, cwd=str(Path(__file__).resolve().parent))
        except subprocess.TimeoutExpired:
            return None, "CLI 超时（120s）"
        out = (r.stdout or "").strip()
        try:
            payload = json.loads(out)
        except ValueError:
            return None, "CLI 输出非 JSON：%s" % (out[:200] or r.stderr[:200])
        if r.returncode != 0 and payload.get("ok") is not True:
            payload["cliExit"] = r.returncode
        return payload, None

    def _template_list(self):
        payload, err = self._cli_json(["tpl-design", "--list"])
        if err:
            return {"ok": False, "error": err}
        return payload

    def _template_show(self, query):
        name = (query.get("name") or [""])[0].strip()
        if not name:
            return {"ok": False, "error": "缺少 name 参数（模板名或文件名，tpl-design --list 查看）"}
        payload, err = self._cli_json(["tpl-design", "--show", name])
        if err:
            return {"ok": False, "error": err}
        return payload

    def _template_validate(self, query):
        name = (query.get("name") or [""])[0].strip()
        if not name:
            return {"ok": False, "error": "缺少 name 参数（模板名或文件名）"}
        payload, err = self._cli_json(["tpl-design", "--validate", name])
        if err:
            return {"ok": False, "error": err}
        return payload

    def _template_parts(self):
        payload, err = self._cli_json(["tpl-part", "--list"])
        if err:
            return {"ok": False, "error": err}
        return payload

    def _template_specimen(self, query):
        """出样张：走 CLI fixture 分支，样张落临时目录并返回绝对路径（只读派生，不写项目/模板库）。"""
        name = (query.get("name") or [""])[0].strip()
        if not name:
            return {"ok": False, "error": "缺少 name 参数（模板名或文件名）"}
        fill = (query.get("fill") or [""])[0].strip() or ""
        import tempfile
        cwd = tempfile.mkdtemp(prefix="bid_tpl_spec_")
        import subprocess
        cli = str(Path(__file__).resolve().parent / "bidcraft.py")
        cmd = [sys.executable, "-X", "utf8", cli, "--root", str(self.server.root or ""),
               "--enterprise", (self.server.enterprise or ""),
               "tpl-design", "--specimen", name, "--json"]
        if fill:
            cmd += ["--fill", fill]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                               timeout=180, cwd=cwd)
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "出样张超时（180s）"}
        out = (r.stdout or "").strip()
        try:
            payload = json.loads(out)
        except ValueError:
            return {"ok": False, "error": "CLI 输出非 JSON：%s" % (out[:300] or r.stderr[:200])}
        payload["ok"] = (r.returncode == 0 and payload.get("ok") is True)
        if not payload["ok"]:
            payload["cliExit"] = r.returncode
        return payload

    # ---- 执行桥（POST /api/exec）----------------------------------------
    def _exec(self, payload):
        """白名单命令执行：read 直接跑；write 必须 confirm:true；白名单外 403。"""
        command = (payload or {}).get("command")
        if not command or not isinstance(command, str):
            return {"ok": False, "error": "缺少 command（白名单 key，见 /api/capabilities execCommands）"}
        entry = EXEC_COMMANDS.get(command)
        if entry is None:
            if command in EXEC_DENY_COMMANDS:
                return {"ok": False, "error": "命令 %s 属高风险操作，执行桥不暴露——请走 CLI 并保留人工确认闸门（--confirm/--apply）" % command,
                        "hint": WRITE_HINT}
            return {"ok": False, "error": "命令 %s 不在执行桥白名单（可用：%s）" %
                    (command, "、".join(sorted(EXEC_COMMANDS)))}
        args = payload.get("args") or {}
        if not isinstance(args, dict):
            return {"ok": False, "error": "args 必须是对象（{name/project/fill...}）"}
        if entry["mode"] == "write" and payload.get("confirm") is not True:
            return {"ok": False, "error": "命令 %s 属写操作（会落盘产物），必须显式确认：confirm:true（由 UI 人工确认产生）" % command}
        argv, err = _validate_exec_args(entry, args, self.server.root, self.server.enterprise)
        if err:
            return {"ok": False, "error": "参数校验失败：%s" % err, "command": command}
        import subprocess
        cli = str(Path(__file__).resolve().parent / "bidcraft.py")
        cmd = [sys.executable, "-X", "utf8", cli,
               "--root", str(self.server.root or ""),
               "--enterprise", str(self.server.enterprise or "")] + argv
        if entry.get("json"):
            cmd.append("--json")
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                               timeout=entry["timeout"],
                               cwd=str(Path(__file__).resolve().parent))
        except subprocess.TimeoutExpired:
            return {"ok": False, "command": command, "error": "CLI 超时（%ss）" % entry["timeout"]}
        stdout = (r.stdout or "")[:EXEC_OUTPUT_LIMIT]
        stderr = (r.stderr or "")[:EXEC_OUTPUT_LIMIT]
        resp = {"ok": (r.returncode == 0), "command": command,
                "mode": entry["mode"], "exit": r.returncode,
                "output": {"stdout": stdout, "stderr": stderr}}
        if entry.get("json"):
            try:
                resp["payload"] = json.loads(stdout.strip())
            except ValueError:
                resp["payload"] = None
                if r.returncode != 0:
                    resp["error"] = "CLI 失败：%s" % (stderr[:500] or stdout[:500])
        elif r.returncode != 0:
            resp["error"] = "CLI 失败：%s" % (stderr[:500] or stdout[:500])
        print("[exec] %s exit=%s" % (command, r.returncode), flush=True)
        return resp

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
            "execBridgeVersion": EXEC_BRIDGE_VERSION,
            "presetsVersion": (doc or {}).get("version", ""),
            "layoutGroups": [{"key": k, "label": v} for k, v in m6layout.GROUPS],
            "commands": commands,
            "moduleEntries": module_entries,
            "endpoints": list(ENDPOINTS),
            "execCommands": [{"key": k, "mode": v["mode"], "description": EXEC_DESCRIPTIONS.get(k, ""),
                              "confirmRequired": v["mode"] == "write"}
                             for k, v in sorted(EXEC_COMMANDS.items())],
            "denyCommands": sorted(EXEC_DENY_COMMANDS),
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
    print("bidcraft-server v%s（只读接口 + 执行桥）已启动：%s" % (SERVER_VERSION, url))
    print("只读接口：/api/health /api/layout/groups /api/layout/presets /api/layout/validate "
          "/api/layout/packs /api/capabilities /api/template/list /api/template/show "
          "/api/template/validate /api/template/parts /api/template/specimen")
    print("执行桥：POST /api/exec（白名单 %d 个命令；write 命令须 confirm:true；白名单外 403）"
          % len(EXEC_COMMANDS))
    print("高风险命令（应用/覆盖/删除/状态推进）一律走 CLI + 人工确认闸门，执行桥不暴露。Ctrl+C 停止。")
    if args.host not in ("0.0.0.0", "::"):
        print("监听 %s —— 仅本机可访问；如需内网访问请显式 --host 0.0.0.0 并自行加鉴权。" % args.host)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
        server.server_close()


if __name__ == "__main__":
    main()
