# -*- coding: utf-8 -*-
"""⑦ core 拆包 · 基础：常量 / LibraryError / 小工具 / Library 类。"""
import hashlib
import json
import re
from datetime import date, datetime
from pathlib import Path

__all__ = [
    "LEDGER_CSV", "LEDGER_JSON", "META_JSON", "BATCH_JSON", "TRASH_JSON",
    "LIB_SUBPATH", "ENTERPRISE_SUBDIRS", "CLASSIFY_DIRS", "PERSON_SUBDIRS",
    "LEDGER_COLUMNS", "TRASH_RETENTION_DAYS", "LibraryError",
    "now_iso", "today_str", "sha256_of", "norm_rel", "rel_to_path", "lib_root",
    "write_json", "read_json", "_name_tokens",
]

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
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def read_json(path, default=None):
    path = Path(path)
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _name_tokens(name):
    """把企业名拆成用于归属识别的特征串。"""
    if not name:
        return set()
    s = re.sub(r"(有限责任公司|股份有限公司|有限公司|公司|集团|分公司|项目部)$", "", name.strip())
    toks = {t for t in {name.strip(), s} if len(t) >= 2}
    return toks
