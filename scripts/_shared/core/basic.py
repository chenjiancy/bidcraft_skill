# -*- coding: utf-8 -*-
"""⑦ core 拆包 · 基础：常量 / LibraryError / 小工具 / Library 类。"""
import errno
import hashlib
import json
import os
import re
import shutil
import time
from datetime import date, datetime
from pathlib import Path

__all__ = [
    "LEDGER_CSV", "LEDGER_JSON", "META_JSON", "BATCH_JSON", "TRASH_JSON",
    "LIB_SUBPATH", "ENTERPRISE_SUBDIRS", "CLASSIFY_DIRS", "PERSON_SUBDIRS",
    "LEDGER_COLUMNS", "TRASH_RETENTION_DAYS", "LibraryError",
    "now_iso", "today_str", "sha256_of", "norm_rel", "rel_to_path", "lib_root",
    "write_json", "read_json", "read_json_strict", "atomic_write_text", "_name_tokens",
]

# 写盘安全四件套（C2）：Windows 文件锁五档退避
_LOCK_RETRY_DELAYS = (0.02, 0.04, 0.08, 0.16, 0.32)
_LOCK_ERRNOS = {errno.EPERM, errno.EACCES, errno.EBUSY}


def _is_lock_error(e):
    return getattr(e, "errno", None) in _LOCK_ERRNOS


def _is_intermediate(name):
    """C2：中间/临时文件后缀（.bak/.tmp/.lock/.corrupt-*）——目录扫描不得当作业务文件。"""
    n = str(name).lower()
    if n.endswith((".bak", ".tmp", ".lock")):
        return True
    if ".corrupt-" in n:
        return True
    return False

# --------------------------------------------------------------------------
# 常量
# --------------------------------------------------------------------------
LEDGER_CSV = "素材台账.csv"
LEDGER_JSON = "素材台账.json"
META_JSON = "_素材库信息.json"
BATCH_JSON = "_batch.json"
TRASH_JSON = "_回收站清单.json"

# 软件目录结构（三层）：软件根/<企业>/回收站（公司级统一回收站）· 企业级/素材库 · 企业级/模板库 · 项目级
LIB_SUBPATH = ("企业级", "素材库")      # 企业目录下素材库的相对路径
ENTERPRISE_SUBDIRS = ["资质", "人员", "业绩", "荣誉", "财务", "企业介绍", "收件箱"]
CLASSIFY_DIRS = ["资质", "人员", "业绩", "荣誉", "财务", "企业介绍"]
PERSON_SUBDIRS = [
    "注册证书", "岗位证书", "职称证书", "身份证", "毕业证",
    "个人荣誉", "退休证", "返聘协议", "简历",
]

LEDGER_COLUMNS = [
    "id", "category", "subtype", "rel_path", "keywords", "dates", "date_type",
    "owner", "upload_date", "original_filename", "source", "group_id",
    "page_index", "ext", "added_at", "note",
]

TRASH_RETENTION_DAYS = 30


class LibraryError(RuntimeError):
    """素材库操作失败（路径非法 / 状态不符 / 企业不存在等）。"""


# --------------------------------------------------------------------------
# 小工具
# --------------------------------------------------------------------------
def now_iso():
    return datetime.now().isoformat(timespec="seconds")


def today_str():
    return date.today().strftime("%Y%m%d")


def sha256_of(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def norm_rel(rel):
    """统一相对路径写法：正斜杠、无首尾斜杠。"""
    return str(rel).replace("\\", "/").strip("/")


def rel_to_path(base, rel):
    return Path(base, *norm_rel(rel).split("/"))


def lib_root(ent):
    """企业素材库根：<企业目录>/企业级/素材库（素材/台账/收件箱/回收站均落于此）。"""
    p = Path(ent)
    for seg in LIB_SUBPATH:
        p = p / seg
    return p


def write_json(path, obj):
    """原子写 JSON（链企引入 C2 写盘安全四件套）：tmp→replace 原子替换 + Windows 文件锁五档退避 + .bak 留底 + 回读校验。

    写前把上一版存 `<name>.bak`；遇 EPERM/EACCES/EBUSY 按 [20,40,80,160,320]ms 退避 5 次后抛 LibraryError；
    写后回读逐字比对，不一致即抛错（绝不静默）。
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(obj, ensure_ascii=False, indent=2) + "\n"
    atomic_write_text(path, text)


def atomic_write_text(path, text):
    """统一原子写文本：tmp→replace + 五档退避 + 旧版 .bak + 回读校验（C2 四件套）。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        try:
            shutil.copy2(str(path), str(path.with_name(path.name + ".bak")))
        except OSError:
            pass  # .bak 尽力而为，不阻塞主写
    tmp = path.with_name(path.name + ".tmp")
    last = None
    for i in range(len(_LOCK_RETRY_DELAYS) + 1):
        try:
            tmp.write_text(text, encoding="utf-8")
            os.replace(str(tmp), str(path))
            break
        except OSError as e:
            if not _is_lock_error(e):
                raise LibraryError("落盘失败：%s（%s）" % (path, e))
            last = e
            if i < len(_LOCK_RETRY_DELAYS):
                time.sleep(_LOCK_RETRY_DELAYS[i])
    else:
        raise LibraryError("落盘失败（文件被占用，重试 %d 次）：%s（%s）"
                           % (len(_LOCK_RETRY_DELAYS) + 1, path, last))
    back = path.read_text(encoding="utf-8")
    if back != text:
        raise LibraryError("回读不一致：%s（写 %d 字符 / 读 %d 字符）"
                           % (path, len(text), len(back)))
    return path


def read_json(path, default=None):
    """读 JSON；坏 JSON 不静默丢现场：原文件改存 `<name>.corrupt-<ts>` 后返回 default。"""
    path = Path(path)
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        _quarantine_corrupt(path)
        return default


def read_json_strict(path, label="JSON", default=None):
    """读 JSON 且坏文件显式报错（SIDECAR_CORRUPT）：备份 .corrupt-{ts} 后抛 LibraryError。

    适用于关键共享资源（layout-presets.json / template.json / 台账），
    静默返回 default 会导致用空内容覆盖真实数据的风险。
    """
    path = Path(path)
    if not path.exists():
        if default is not None:
            return default
        raise LibraryError("%s不存在：%s" % (label, path))
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        _quarantine_corrupt(path)
        raise LibraryError("%s损坏（SIDECAR_CORRUPT，原文件已备份 .corrupt）：%s（%s）" % (label, path, e))


def _quarantine_corrupt(path):
    """坏 JSON 备份：`<name>.corrupt-<ts>`，绝不拿空内容覆盖真实文件。"""
    try:
        dst = path.with_name(path.name + ".corrupt-%s" % datetime.now().strftime("%Y%m%d-%H%M%S"))
        if not dst.exists():
            shutil.copy2(str(path), str(dst))
    except OSError:
        pass


def _name_tokens(name):
    """把企业名拆成用于归属识别的特征串。"""
    if not name:
        return set()
    s = re.sub(r"(有限责任公司|股份有限公司|有限公司|公司|集团|分公司|项目部)$", "", name.strip())
    toks = {t for t in {name.strip(), s} if len(t) >= 2}
    return toks
