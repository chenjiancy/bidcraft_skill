# -*- coding: utf-8 -*-
"""
bidcraft · M0 环境基线 —— env-check 一键体检（Word COM / gen_py / 字体 / OCR 引擎）。

触发场景：
  · 换机 / 重装后首次使用前：python bidcraft.py env-check
  · 出现 Word 原生崩溃（gen_py 缓存过期）、OCR 识别失败、字体排版异常时排查
  · CI 前确认本机运行环境基线

设计：只读检查，不修改任何系统状态；每项返回 {name, status, detail}，
status ∈ ok / warn（可用但隐患）/ fail（缺失阻断），由 agent 决定后续动作。
"""

import json
import platform
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from _shared.core.basic import now_iso

__all__ = ["run_env_checks", "cmd_env_check", "register_parser"]

# 标书常用字体（注册表 Fonts 键中的名称前缀，Windows 11 为罗马化命名）
FONT_CHECKS = [
    ("SimSun", "宋体"),
    ("SimHei", "黑体"),
    ("KaiTi", "楷体"),
    ("FangSong", "仿宋"),
    ("FangSong_GB2312", "仿宋_GB2312"),
    ("Microsoft YaHei", "微软雅黑"),
    ("Times New Roman", "Times New Roman"),
    ("Arial", "Arial"),
]


def _importable(mod):
    try:
        __import__(mod)
        return True
    except Exception:
        return False


def _check_python():
    v = platform.python_version()
    bits = 64 if sys.maxsize > 2 ** 32 else 32
    return {"name": "Python 环境", "status": "ok",
            "detail": "%s（%d 位）%s" % (v, bits, platform.platform())}


def _check_deps():
    out = []
    deps = [
        ("python-docx", "docx"),
        ("PyMuPDF", "pymupdf"),
        ("pywin32(win32com)", "win32com.client"),
        ("pywin32(pythoncom)", "pythoncom"),
        ("rapidocr_onnxruntime", "rapidocr_onnxruntime"),
        ("pytesseract", "pytesseract"),
    ]
    for label, mod in deps:
        if _importable(mod):
            out.append({"name": "依赖·%s" % label, "status": "ok", "detail": "可导入"})
        else:
            out.append({"name": "依赖·%s" % label, "status": "warn",
                        "detail": "未安装（对应功能将降级/不可用）"})
    return out


def _check_word_com():
    from _shared import com_util
    if not com_util.HAVE_COM:
        return {"name": "Word COM", "status": "warn",
                "detail": "pywin32 不可用（Word 页数统计/格式检查功能降级）"}
    # 实弹冒烟：临时空 docx → 打开 → 统计页数 → 干净退出
    import tempfile as _tf
    from docx import Document
    tmpdir = _tf.TemporaryDirectory()
    try:
        probe = Path(tmpdir.name) / "_env_probe.docx"
        d = Document()
        d.add_paragraph("env-check 冒烟测试")
        d.save(str(probe))
        with com_util.WordCOM() as w:
            pages = w.pages_of(probe)
        return {"name": "Word COM", "status": "ok",
                "detail": "DispatchEx 打开/统计页数冒烟通过（页数=%d）" % pages}
    except Exception as e:
        return {"name": "Word COM", "status": "warn",
                "detail": "COM 冒烟失败：%s（若为原生崩溃，先清 gen_py 缓存后重试）" % e}
    finally:
        try:
            tmpdir.cleanup()
        except Exception:
            pass


def _check_gen_py():
    """gen_py 类型库缓存：存在即可能累积过期（pywin32 已知坑），提示按需重建。"""
    gen = Path(tempfile.gettempdir()) / "gen_py"
    if not gen.exists():
        return {"name": "gen_py 缓存", "status": "ok",
                "detail": "无缓存目录（%s），pywin32 将按需生成" % gen}
    try:
        pyver = "cp%d%d-win_amd64" % (sys.version_info[0], sys.version_info[1])
        cache = gen / pyver
        if cache.exists():
            files = sum(1 for _ in cache.rglob("*") if _.is_file())
            age_days = (datetime.now().timestamp() - cache.stat().st_mtime) / 86400
            if age_days > 30:
                return {"name": "gen_py 缓存", "status": "warn",
                        "detail": "%s 存在 %d 个文件，最近写入已 %.0f 天（建议清理重建，规避原生崩溃）"
                                  % (cache, files, age_days)}
            return {"name": "gen_py 缓存", "status": "ok",
                    "detail": "%s 存在 %d 个文件，最近写入 %.0f 天内（正常）"
                              % (cache, files, max(1, age_days))}
        return {"name": "gen_py 缓存", "status": "ok",
                "detail": "存在根目录 %s（尚未生成当前版本缓存）" % gen}
    except Exception as e:
        return {"name": "gen_py 缓存", "status": "warn", "detail": "检查失败：%s" % e}


def _check_fonts():
    """注册表 Fonts 键读取系统字体（标书常用中英文字体）。"""
    import winreg
    out = []
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts") as k:
            i = 0
            fonts = []
            while True:
                try:
                    name, _, _ = winreg.EnumValue(k, i)
                    fonts.append(name)
                    i += 1
                except OSError:
                    break
        for family, label in FONT_CHECKS:
            hits = [n for n in fonts if n.startswith(family)]
            if hits:
                out.append({"name": "字体·%s" % label, "status": "ok",
                            "detail": "已安装（%s）" % hits[0]})
            else:
                out.append({"name": "字体·%s" % label, "status": "warn",
                            "detail": "未在注册表 Fonts 中找到（若模板排版异常请检查）"})
        return out
    except Exception as e:
        return [{"name": "字体检查", "status": "warn",
                 "detail": "读取注册表失败：%s" % e}]


def _check_tesseract():
    from m5_project import fill_ocr as ocr
    t = ocr.TESS
    p = Path(t)
    if not p.exists():
        return {"name": "Tesseract OCR", "status": "warn",
                "detail": "未找到 tesseract：%s（rapidocr 可用时 OCR 仍可工作）" % t}
    try:
        r = subprocess.run([str(p), "--version"], capture_output=True, text=True,
                           timeout=10, encoding="utf-8", errors="replace")
        ver = (r.stdout or r.stderr or "").strip().splitlines()[0]
        return {"name": "Tesseract OCR", "status": "ok", "detail": "%s → %s" % (p, ver)}
    except Exception as e:
        return {"name": "Tesseract OCR", "status": "warn",
                "detail": "存在但版本探测失败：%s" % e}


def _check_rapidocr():
    if _importable("rapidocr_onnxruntime"):
        return {"name": "rapidocr", "status": "ok",
                "detail": "rapidocr_onnxruntime 可导入（OCR 主引擎可用）"}
    return {"name": "rapidocr", "status": "warn",
            "detail": "未安装（将走 tesseract 兜底）"}


def run_env_checks():
    """执行全部环境检查（只读）。返回结构化结果。"""
    checks = [_check_python()]
    checks += _check_deps()
    checks += [_check_rapidocr(), _check_tesseract()]
    checks += [_check_word_com(), _check_gen_py()]
    checks += _check_fonts()

    n_fail = sum(1 for c in checks if c["status"] == "fail")
    n_warn = sum(1 for c in checks if c["status"] == "warn")
    return {
        "scanned_at": now_iso(),
        "checks": checks,
        "summary": {"ok": len(checks) - n_fail - n_warn, "warn": n_warn, "fail": n_fail},
        "ok": n_fail == 0,
    }


def cmd_env_check(args):
    res = run_env_checks()
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return
    from m1_assets.commands import table as _table
    rows = [[c["name"], c["status"], c["detail"]] for c in res["checks"]]
    print(_table(rows, ["检查项", "状态", "说明"]))
    s = res["summary"]
    print("\n结果：%d 正常 / %d 警告 / %d 失败%s" % (
        s["ok"], s["warn"], s["fail"],
        "（全部正常）" if res["ok"] else "（有警告/失败项，请按上表处理）"))


def register_parser(sub):
    # 注意：--json 由 bidcraft.py 统一给每个子命令补充（SUPPRESS 语义），此处不再重复定义
    sp = sub.add_parser("env-check", help="M0：运行环境一键体检（Word COM/gen_py/字体/OCR）")
    sp.set_defaults(func=cmd_env_check)
