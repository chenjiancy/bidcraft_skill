# -*- coding: utf-8 -*-
"""Word COM 统一封装（P2-6）：单实例复用 + 干净退出 + 页数统计。

背景（开发日志 2026-10-05）：
  - checker.py 旧实现每文件 DispatchEx + doc.Close(False)，在
    pywin32 + Python 3.14 下触发原生 access violation（gen_py 缓存过期）；
  - 本机 Word Quit() 后进程不自动退出（pywin32 312 引用计数问题），
    文件锁会残留 → 退出时记录本次启动的 PID 并精确 taskkill
    （不误杀用户手动打开的 Word 文档）。
  - 若仍遇原生崩溃，先清 %TEMP%\\gen_py\\<pyver>\\ 重建类型库缓存。
"""
import gc
import subprocess
import time

try:
    import pythoncom
    import win32com.client
    HAVE_COM = True
except Exception:                                  # pragma: no cover - 环境缺依赖
    HAVE_COM = False

# Word 内置常量（与版本无关的稳定值）
WD_STATISTICS_PAGES = 2                            # wdStatisticPages


class WordCOM:

    def __init__(self, visible=False):
        self._word = None
        self._visible = visible
        self._docs = []
        self._pid = None

    def __enter__(self):
        if HAVE_COM:
            pythoncom.CoInitialize()
        return self

    def _ensure(self):
        if self._word is None:
            before = set(_word_procs())
            self._word = win32com.client.DispatchEx("Word.Application")
            self._word.Visible = self._visible
            try:
                self._word.DisplayAlerts = 0
            except Exception:
                pass
            # 记录本次启动的 Word PID（before/after 差集，精确清理不误杀）
            new = set(_word_procs()) - before
            if new:
                self._pid = int(new.pop())
        return self._word

    def open_readonly(self, path):
        """只读打开 docx/doc，返回 Document（文档引用登记在 _docs）。"""
        word = self._ensure()
        doc = word.Documents.Open(str(path), ReadOnly=True)
        self._docs.append(doc)
        return doc

    def pages_of(self, path):
        """打开→强制重排→统计页数→释放文档引用。返回页数。"""
        doc = self.open_readonly(path)
        try:
            try:
                doc.Repaginate()
            except Exception:
                pass
            return int(doc.ComputeStatistics(WD_STATISTICS_PAGES))
        finally:
            self._docs.remove(doc)
            try:
                del doc
            except Exception:
                pass

    def __exit__(self, exc_type, exc, tb):
        # 1) 释放全部文档引用（让 Word 端文档状态可关闭）
        self._docs.clear()
        # 2) Quit（优雅退出；异常吞掉，兜底靠精确 kill）
        try:
            if self._word is not None:
                self._word.Quit()
        except Exception:
            pass
        try:
            del self._word
        except Exception:
            pass
        self._word = None
        gc.collect()
        # 3) 轮询等待本次进程退出（最多 ~2s）；仍残留 → 精确 taskkill
        for _ in range(4):
            time.sleep(0.5)
            if self._pid is not None and str(self._pid) not in _word_procs():
                break
        if self._pid is not None:
            _kill_pid(self._pid)
            self._pid = None
            time.sleep(0.6)        # 等待 Word 进程句柄释放（否则紧随删除会 WinError 32）
        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass
        return False


def _kill_pid(pid):
    try:
        subprocess.run(["taskkill", "/PID", str(pid), "/F"],
                       capture_output=True, timeout=10)
    except Exception:
        pass


def _word_procs():
    if not HAVE_COM:
        return []
    ps = "Get-Process WINWORD -ErrorAction SilentlyContinue | ForEach-Object { $_.Id }"
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                           capture_output=True, text=True, timeout=10)
        return (r.stdout or "").split()
    except Exception:
        return []
