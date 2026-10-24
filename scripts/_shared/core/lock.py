# -*- coding: utf-8 -*-
"""⑧ core 拆包 · 跨进程文件锁（链企引入 C2 写盘安全四件套之一）。

进程内 key 锁挡不住两个进程同时写同一文件（执行桥 + CLI 双开场景），
本模块提供跨进程 lockfile：PID + 时间戳 + 心跳，stale 30s 可抢占。

用法（contextmanager）：
    with file_lock(path, timeout=10.0, stale=30.0):
        ...  # 独占写盘
    拿不到锁（timeout 耗尽且锁未 stale）→ 抛 LibraryError(LOCK_BUSY)。
"""
import os
import time
from contextlib import contextmanager
from pathlib import Path

from .basic import LibraryError

LOCK_SUFFIX = ".lock"
STALE_SECONDS = 30.0
HEARTBEAT_INTERVAL = 5.0
_ACQUIRE_POLL = 0.05


class _FileLock:
    """进程内持有的锁对象：进入时写 lockfile，退出时删除；持有期间心跳刷新。"""

    def __init__(self, lock_path, stale):
        self.lock_path = Path(lock_path)
        self.stale = stale
        self.pid = os.getpid()
        self._last_beat = 0.0

    def _write(self):
        self.lock_path.write_text(json_payload(self.pid, time.time()), encoding="utf-8")
        self._last_beat = time.time()

    def _alive(self):
        """当前 lockfile 是否属于存活进程（PID 存活）——抢占判断依据。"""
        try:
            meta = self.lock_path.read_text(encoding="utf-8").strip().split()
            pid = int(meta[0]) if meta else -1
            ts = float(meta[1]) if len(meta) > 1 else 0.0
        except (OSError, ValueError):
            return False
        if pid == self.pid:
            return True
        if _pid_alive(pid):
            return time.time() - ts < self.stale  # 存活但心跳过期 → 视为可抢占
        return False  # 进程已死 → 可抢占

    def heartbeat(self):
        now = time.time()
        if now - self._last_beat >= HEARTBEAT_INTERVAL:
            try:
                self._write()
            except OSError:
                pass

    def release(self):
        try:
            self.lock_path.unlink(missing_ok=True)
        except OSError:
            pass


def json_payload(pid, ts):
    return "%d %.3f\n" % (pid, ts)


def _pid_alive(pid):
    """跨平台 PID 存活探测（Windows 用 OpenProcess，POSIX 用 kill 0）。"""
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        try:
            exit_code = ctypes.c_ulong()
            ok = ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
            if not ok:
                return True
            return exit_code.value == 259  # STILL_ACTIVE
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    import signal

    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


@contextmanager
def file_lock(path, timeout=10.0, stale=STALE_SECONDS):
    """跨进程文件锁：拿不到且超时 → LibraryError；支持 stale 抢占（进程死/心跳过期）。"""
    lock_path = Path(str(path) + LOCK_SUFFIX)
    deadline = time.time() + timeout
    while True:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(json_payload(os.getpid(), time.time()))
            lock = _FileLock(lock_path, stale)
            break
        except FileExistsError:
            lock = _FileLock(lock_path, stale)
            if not lock._alive():
                # 进程死 / 心跳过期 → 抢占删除
                try:
                    lock_path.unlink(missing_ok=True)
                except OSError:
                    pass
                continue
            if time.time() >= deadline:
                raise LibraryError("获取文件锁超时（LOCK_BUSY）：%s" % lock_path)
            time.sleep(_ACQUIRE_POLL)
    try:
        yield
    finally:
        lock.release()
