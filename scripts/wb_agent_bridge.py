# -*- coding: utf-8 -*-
"""
bidcraft · 执行桥 Agent 桥（通道B：agent 语义解析自动化）

职责：把「提示词模板 + 招标原文」交给本机 CodeBuddy Code CLI（headless 单次模式），
      取回结构化响应（markdown 文本 + 内嵌 JSON 骨架），供 M4 tender-agent-parse 校验落盘。

背景：
- 通道A（tender-rule）是规则引擎，脚本可确定性执行；
- 通道B（语义解析 9 模块）本质是 agent 的活——此前由「人肉 agent / 平台 AI」完成，
  脚本只做编排与存取（解析主体：agent）。
- 本模块让通道B 可编程化：包装官方 CodeBuddy CLI（codebuddy -p --output-format json），
  登录态独立（首次须 /login，见 dev/登录CodeBuddy-CLI.bat），认证后 headless 调用即通。

契约：
- CLI 路径解析顺序：env BIDCRAFT_AGENT_CLI → PATH 中的 codebuddy → 本机官方默认安装路径。
- 调用形态：codebuddy -p <prompt> --output-format json  （headless 非交互单次，rc=0 成功）
- 输出形态：JSON 消息流（数组，元素含 role/content）；assistant 最终文本即解析产物。
- 产物约定：assistant 文本 = 投标要点 markdown 全文，末尾内嵌 ```json {…modules…}``` 骨架。
- 失败分类：未登录（Authentication required…/login）/ 超时 / CLI 缺失 / 输出无 JSON 骨架。

边界（如实声明）：
- 调用真实 AI：有成本、耗时长（长文档可能数分钟），非确定性输出；
- 质量由提示词模板（M4-招标文件解析-提示词.md v1.1）+ 落盘校验（rules.validate_points_json）
  兜底；最终仍须人工核对闸门（tender-report HTML + 双通道 diff 用户裁决）。
"""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

# 本机官方 CLI 默认安装路径（Windows native installer；其他平台由 BIDCRAFT_AGENT_CLI/PATH 提供）
DEFAULT_CLI = r"C:\Users\hxjlcj\AppData\Local\codebuddy\bin\codebuddy.exe"

AUTH_REQUIRED_HINT = "Authentication required"
JSON_FENCE_RE = re.compile(r"```json[ \t]*\r?\n(.*?)\r?\n```", re.S)


def find_cli():
    """解析 CodeBuddy CLI 可执行路径。优先 env → PATH → 默认安装路径。"""
    env = os.environ.get("BIDCRAFT_AGENT_CLI")
    if env and Path(env).exists():
        return str(Path(env))
    found = shutil.which("codebuddy")
    if found:
        return found
    p = Path(DEFAULT_CLI)
    if p.exists():
        return str(p)
    return None


def extract_assistant_text(stdout):
    """
    从 headless JSON 消息流提取 assistant 最终文本（拼接全部 assistant 文本块）。
    容错：stdout 不是合法 JSON 数组时原样返回（供上层报错用）。
    返回 (text, parsed) —— parsed=False 表示未按消息流解析。
    """
    if not stdout or not stdout.strip():
        return "", False
    try:
        msgs = json.loads(stdout)
    except Exception:
        return stdout, False
    if not isinstance(msgs, list):
        return stdout, False
    parts = []
    for m in msgs:
        if not isinstance(m, dict):
            continue
        if m.get("role") != "assistant" and m.get("type") != "message":
            continue
        content = m.get("content")
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            for c in content:
                if isinstance(c, dict) and c.get("type") in ("text", "output_text", "input_text"):
                    parts.append(c.get("text") or "")
    return "\n".join(p for p in parts if p), True


def extract_json_block(text):
    """
    从 assistant 文本提取「投标要点 JSON 骨架」：
    1) 优先 ```json … ``` 围栏块；
    2) 其次扫平衡大括号对象，取含 "modules" 键且可 json.loads 的第一个。
    返回 (json_obj|None, error)。
    """
    if not text:
        return None, "agent 输出为空"
    for m in JSON_FENCE_RE.finditer(text):
        block = m.group(1).strip()
        try:
            obj = json.loads(block)
            if isinstance(obj, dict) and "modules" in obj:
                return obj, None
        except Exception:
            continue
    # 围栏未命中：扫描平衡大括号
    start = -1
    depth = 0
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start >= 0:
                cand = text[start:i + 1]
                try:
                    obj = json.loads(cand)
                except Exception:
                    start = -1
                    continue
                if isinstance(obj, dict) and "modules" in obj:
                    return obj, None
                start = -1
    return None, "输出中未找到含 modules 的 JSON 骨架（请检查提示词模板与 CLI 输出）"


def run_agent(prompt, cwd=None, timeout=900, cli=None):
    """
    调 CodeBuddy CLI headless 单次模式执行 prompt。
    返回 {"ok": bool, "text": assistant 文本, "rc": int, "error": str|None,
          "cli": 路径, "elapsed_s": float}。
    """
    import time
    cli = cli or find_cli()
    if not cli:
        return {"ok": False, "text": "", "rc": -1,
                "error": "未找到 CodeBuddy CLI（请设置 BIDCRAFT_AGENT_CLI，或安装官方 CLI 后重试）",
                "cli": None, "elapsed_s": 0.0}
    if isinstance(cli, (list, tuple)):
        argv = list(cli) + ["-p", prompt, "--output-format", "json"]
        cli_disp = " ".join(str(x) for x in cli)
    elif str(cli).lower().endswith(".py"):
        # .py 直跑：用当前解释器启动（测试注入 fake CLI / 轻量包装场景）
        argv = [sys.executable, str(cli), "-p", prompt, "--output-format", "json"]
        cli_disp = str(cli)
    else:
        argv = [cli, "-p", prompt, "--output-format", "json"]
        cli_disp = cli
    t0 = time.time()
    try:
        r = subprocess.run(
            argv, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=timeout, cwd=cwd or os.getcwd())
    except subprocess.TimeoutExpired:
        return {"ok": False, "text": "", "rc": -1,
                "error": "CLI 超时（%ds）：长文档解析可能超时，请加长 --timeout 或拆段重试" % timeout,
                "cli": cli, "elapsed_s": round(time.time() - t0, 1)}
    except OSError as e:
        return {"ok": False, "text": "", "rc": -1,
                "error": "CLI 启动失败：%s（路径：%s）" % (e, cli_disp),
                "cli": cli_disp, "elapsed_s": round(time.time() - t0, 1)}
    elapsed = round(time.time() - t0, 1)
    out = (r.stdout or "") + "\n" + (r.stderr or "")
    if AUTH_REQUIRED_HINT in out:
        return {"ok": False, "text": "", "rc": r.returncode,
                "error": "CLI 未登录：请先运行 codebuddy 进入交互界面执行 /login 完成登录（见 dev/登录CodeBuddy-CLI.bat）",
                "cli": cli_disp, "elapsed_s": elapsed}
    text, parsed = extract_assistant_text(r.stdout or "")
    if r.returncode != 0 and not text:
        return {"ok": False, "text": "", "rc": r.returncode,
                "error": "CLI 执行失败（rc=%d）：%s" % (r.returncode, (r.stderr or r.stdout or "").strip()[:500]),
                "cli": cli_disp, "elapsed_s": elapsed}
    return {"ok": True, "text": text, "rc": r.returncode,
            "error": None, "cli": cli_disp, "elapsed_s": elapsed, "parsed": parsed}


def compose_prompt(template_text, original_text, project, extra=""):
    """
    组装 agent 解析 prompt：提示词模板（全文）+ 招标原文 + 输出硬性契约。
    模板本身即 M4-招标文件解析-提示词.md（通道B 强制使用）；
    末尾追加「只输出 md + json 骨架」的机器可解析契约。
    """
    head = "你正在执行 bidcraft M4 招标文件解析 · 通道B（语义解析 9 模块）。\n"
    head += "项目名：%s\n" % project
    contract = (
        "\n\n【机器可解析输出契约（必须严格遵守）】\n"
        "1. 按上述规范完成全部解析后，只输出两部分、不要输出其它任何内容：\n"
        "   第一部分：投标要点 markdown 全文（人读版，含全部 9 模块/风险提示/完整度声明）。\n"
        "   第二部分：一个 ```json 围栏块，内容为投标要点 JSON 骨架（含 modules 数组与 diffs 数组，"
        "字段缺失用「原文未提供」），与 markdown 内容一致。\n"
        "2. JSON 骨架必须能被 json.loads 解析；禁止在 JSON 块内写注释或截断。\n"
    )
    if extra:
        contract += "\n【补充要求】\n%s\n" % extra
    return (head + "\n" + template_text + "\n\n"
            + "【招标原文】（分段精读执行流程必须执行；原文如下）\n"
            + original_text + "\n\n【开始输出】\n" + contract)


def render_error(err):
    """把 bridge 错误转成终端友好提示（供 CLI 上层 dump）。"""
    return err or "未知错误"
