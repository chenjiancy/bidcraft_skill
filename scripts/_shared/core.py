# -*- coding: utf-8 -*-
"""
bidcraft · M1 素材库 —— 存储层（企业目录 / 台账 / 收件箱批次 / 回收站 / 巡检 / 检索）

职责边界
--------
- 只做确定性的文件系统操作与数据读写，不做「看懂内容」的判断。
- 「图片/PDF 正文里写的是哪家企业」「这几页是不是同一份证书」这类语义判断，
  由 agent（多模态）完成，然后把结论作为参数传进来执行。
"""

import csv
from collections import defaultdict
import hashlib
import json
import os
import re
import shutil
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

from . import naming as nm

# --------------------------------------------------------------------------
# 常量
# --------------------------------------------------------------------------
LEDGER_CSV = "素材台账.csv"
LEDGER_JSON = "素材台账.json"
META_JSON = "_素材库信息.json"
BATCH_JSON = "_batch.json"
TRASH_JSON = "_回收站清单.json"

# 软件目录结构（三层）：软件根/<企业>/企业级/业绩库(素材库) · 企业级/模板库 · 项目级
LIB_SUBPATH = ("企业级", "业绩库")      # 企业目录下素材库（业绩库）的相对路径
ENTERPRISE_SUBDIRS = ["资质", "人员", "业绩", "荣誉", "财务", "企业介绍", "收件箱", "回收站"]
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
    """企业素材库根：<企业目录>/企业级/业绩库（素材/台账/收件箱/回收站均落于此）。"""
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


# --------------------------------------------------------------------------
# 库（多企业容器）
# --------------------------------------------------------------------------
class Library:
    def __init__(self, root):
        self.root = Path(root)

    # -- 企业 -------------------------------------------------------------
    def ensure_root(self):
        self.root.mkdir(parents=True, exist_ok=True)

    def enterprises(self):
        if not self.root.exists():
            return []
        out = []
        for d in sorted(self.root.iterdir()):
            if not d.is_dir() or d.name.startswith("."):
                continue
            lib = lib_root(d)
            if (lib / LEDGER_JSON).exists() or (lib / LEDGER_CSV).exists() or \
               any((lib / s).is_dir() for s in CLASSIFY_DIRS):
                out.append(d.name)
        return out

    def resolve(self, name=None):
        ents = self.enterprises()
        if name:
            target = self.root / name
            if not target.is_dir():
                raise LibraryError(
                    "企业不存在：%s（现有：%s）" % (name, "、".join(ents) or "无")
                )
            return target
        if len(ents) == 1:
            return self.root / ents[0]
        if not ents:
            raise LibraryError("尚未创建任何企业，请先执行 init-enterprise 创建企业")
        raise LibraryError("存在多个企业，请用 --enterprise 指定：%s" % "、".join(ents))

    def init_enterprise(self, name, credit_code=None, owner=None):
        """
        初始化企业（三层结构）：
          软件根/<企业>/
            ├── 企业级/
            │   ├── 业绩库/        ← 素材库：资质/人员/业绩/荣誉/财务/收件箱/回收站 + 台账
            │   └── 模板库/
            └── 项目级/
        """
        self.ensure_root()
        dirname = ("%s_%s" % (name, credit_code)) if credit_code else name
        ent = self.root / dirname
        existed = ent.is_dir()
        ent.mkdir(parents=True, exist_ok=True)
        (ent / "项目级").mkdir(exist_ok=True)
        (ent / "企业级" / "模板库").mkdir(parents=True, exist_ok=True)
        lib = lib_root(ent)                      # 企业级/业绩库（素材库）
        lib.mkdir(parents=True, exist_ok=True)
        for sub in ENTERPRISE_SUBDIRS:
            (lib / sub).mkdir(exist_ok=True)
        meta_path = lib / META_JSON
        if not meta_path.exists():
            write_json(meta_path, {
                "name": name,
                "credit_code": credit_code,
                "dir": dirname,
                "owner": owner or name,
                "schema": 1,
                "created_at": now_iso(),
            })
        if not (lib / LEDGER_JSON).exists() and not (lib / LEDGER_CSV).exists():
            save_ledger(ent, [])
        return ent, existed

    def remove_empty_enterprise(self, ent):
        """仅当企业目录为空骨架时删除（用于误创建回滚）。"""
        pass  # 保守起见不提供删除，避免误删素材


# --------------------------------------------------------------------------
# 台账
# --------------------------------------------------------------------------
def load_ledger(ent):
    ent = Path(ent)
    lib = lib_root(ent)
    p = lib / LEDGER_JSON
    if p.exists():
        data = read_json(p, None)
        if isinstance(data, list):
            return data
    csvp = lib / LEDGER_CSV
    if csvp.exists():
        with open(csvp, encoding="utf-8-sig", newline="") as f:
            return [dict(r) for r in csv.DictReader(f)]
    return []


def save_ledger(ent, rows):
    ent = Path(ent)
    lib = lib_root(ent)
    rows = list(rows)
    (lib / LEDGER_JSON).write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    with open(lib / LEDGER_CSV, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=LEDGER_COLUMNS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in LEDGER_COLUMNS})


def ledger_index(ent):
    """rel_path(规范化) -> row"""
    return {norm_rel(r.get("rel_path", "")): r for r in load_ledger(ent) if r.get("rel_path")}


def new_ledger_row(**kw):
    row = {c: "" for c in LEDGER_COLUMNS}
    row["id"] = uuid.uuid4().hex[:8]
    row["added_at"] = now_iso()
    row["upload_date"] = kw.get("upload_date") or today_str()
    row.update({k: v for k, v in kw.items() if k in LEDGER_COLUMNS})
    return row


# --------------------------------------------------------------------------
# 收件箱（上传批次）
# --------------------------------------------------------------------------
class Inbox:
    def __init__(self, ent):
        self.ent = Path(ent)
        self.dir = lib_root(self.ent) / "收件箱"
        self.batch_path = self.dir / BATCH_JSON

    # -- 批次 -------------------------------------------------------------
    def open(self, note=None, force=False):
        self.dir.mkdir(parents=True, exist_ok=True)
        b = read_json(self.batch_path, None)
        if b and not b.get("closed_at") and not force:
            b["resumed"] = True
            return b
        b = {
            "batch_id": uuid.uuid4().hex[:8],
            "created_at": now_iso(),
            "closed_at": None,
            "note": note or "",
            "items": [],
        }
        # 接管「上一批次未归档、仍躺在收件箱里」的文件，避免丢跟踪
        carried = self._register_folder_files(b)
        b["carried_over"] = len(carried)
        write_json(self.batch_path, b)
        return b

    def load(self):
        return read_json(self.batch_path, None)

    def require_open(self):
        b = self.load()
        if not b:
            raise LibraryError("收件箱未打开，请先执行 open-inbox")
        if b.get("closed_at"):
            raise LibraryError("本批次已关闭（closed_at=%s），如需继续请重新 open-inbox" % b["closed_at"])
        return b

    def add(self, src_path, original_name=None):
        """逐张上传：单次调用只接收一个文件。"""
        src = Path(src_path)
        if not src.exists():
            raise LibraryError("文件不存在：%s" % src)
        if src.is_dir():
            raise LibraryError("一次只能上传一个文件（不支持目录/批量）：%s" % src)

        b = self.require_open()
        seq = (max([i.get("seq", 0) for i in b["items"]]) + 1) if b["items"] else 1

        orig = original_name or src.name
        target = self.dir / orig
        if target.exists():
            stem, ext = nm.split_ext(orig)
            n = 2
            while True:
                cand = self.dir / ("%s_dup%d%s" % (stem, n, ext))
                if not cand.exists():
                    target = cand
                    break
                n += 1

        shutil.copy2(src, target)
        os.utime(target, None)  # 刷新 mtime，便于顺序兜底

        item = {
            "seq": seq,
            "file": target.name,
            "original_name": orig,
            "via": "upload",
            "size": target.stat().st_size,
            "sha256": sha256_of(target),
            "written_at": datetime.fromtimestamp(target.stat().st_mtime).isoformat(timespec="seconds"),
            "uploaded_at": now_iso(),
        }
        b["items"].append(item)
        write_json(self.batch_path, b)
        return item

    def _register_folder_files(self, b):
        """把「直接拷进收件箱文件夹」的文件补登记进批次 b（就地修改，不落盘）。"""
        known = {i.get("file") for i in b.get("items", [])}
        reserved = {BATCH_JSON, "_归档提案.json"}
        found = []
        for p in sorted(self.dir.iterdir()):
            if not p.is_file() or p.name in reserved or p.name.startswith("."):
                continue
            if p.name not in known:
                found.append(p)
        found.sort(key=lambda p: (p.stat().st_mtime, p.name))

        seq = (max([i.get("seq", 0) for i in b.get("items", [])]) + 1) if b.get("items") else 1
        added = []
        for p in found:
            it = {
                "seq": seq,
                "file": p.name,
                "original_name": p.name,
                "via": "folder",
                "size": p.stat().st_size,
                "sha256": sha256_of(p),
                "written_at": datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds"),
                "uploaded_at": now_iso(),
            }
            b.setdefault("items", []).append(it)
            added.append(it)
            seq += 1
        return added

    def sync(self):
        """
        把「直接拷进收件箱文件夹」的文件补登记进当前批次（上传方式不限）。
        这类文件顺序只能靠写入时间推断，故标记 via=folder 并在撞车时提示人工确认。
        """
        b = self.require_open()
        added = self._register_folder_files(b)
        if added:
            write_json(self.batch_path, b)
        return added

    def items(self, order="seq"):
        b = self.load() or {"items": []}
        items = list(b.get("items", []))
        if order == "seq":
            items.sort(key=lambda i: i.get("seq", 0))
        elif order == "time":
            items.sort(key=lambda i: i.get("written_at", ""))
        return items

    def has_time_collision(self):
        """
        顺序风险检测。
        - 全部条目经 upload 逐张登记 → 序号即权威顺序，无风险。
        - 存在「直接丢进文件夹」的条目 → 顺序只能靠写入时间推断，同秒即视为撞车。
        """
        items = self.items()
        if not items:
            return False
        folder_items = [i for i in items if i.get("via") != "upload"]
        if not folder_items:
            return False
        times = [i.get("written_at", "") for i in folder_items]
        return len(times) != len(set(times))

    def close(self):
        b = self.load()
        if not b:
            raise LibraryError("收件箱未打开")
        b["closed_at"] = now_iso()
        write_json(self.batch_path, b)
        return b

    def remove_items(self, filenames):
        """从批次中移除已归档条目（文件已在归档时移走）。"""
        b = self.load()
        if not b:
            return
        drop = set(filenames)
        b["items"] = [i for i in b["items"] if i.get("file") not in drop]
        if not b["items"]:
            self.batch_path.unlink(missing_ok=True)
        else:
            write_json(self.batch_path, b)

    def path_of(self, filename):
        return self.dir / filename


# --------------------------------------------------------------------------
# 回收站
# --------------------------------------------------------------------------
def trash_dir(ent):
    d = lib_root(ent) / "回收站"
    d.mkdir(parents=True, exist_ok=True)
    return d


def trash_manifest(ent):
    return read_json(trash_dir(ent) / TRASH_JSON, []) or []


def save_trash_manifest(ent, rows):
    write_json(trash_dir(ent) / TRASH_JSON, rows)


def move_to_trash(ent, rel_path, reason=""):
    """把企业内某文件移入回收站并登记删除时间/到期时间。"""
    ent = Path(ent)
    src = rel_to_path(lib_root(ent), rel_path)
    if not src.exists():
        raise LibraryError("待删除文件不存在：%s" % rel_path)

    name = src.name
    dest = trash_dir(ent) / name
    if dest.exists():
        stem, ext = nm.split_ext(name)
        dest = trash_dir(ent) / ("%s_%s%s" % (stem, datetime.now().strftime("%Y%m%d%H%M%S"), ext))

    shutil.move(str(src), str(dest))
    rows = trash_manifest(ent)
    rows.append({
        "file": dest.name,
        "original_rel": norm_rel(rel_path),
        "reason": reason,
        "deleted_at": now_iso(),
        "expire_at": (datetime.now() + timedelta(days=TRASH_RETENTION_DAYS)).isoformat(timespec="seconds"),
    })
    save_trash_manifest(ent, rows)
    return dest


def cleanup_trash(ent, days=TRASH_RETENTION_DAYS):
    """清理超期回收站文件；返回被删列表。"""
    ent = Path(ent)
    rows = trash_manifest(ent)
    kept, removed = [], []
    cutoff = datetime.now() - timedelta(days=days)
    tdir = trash_dir(ent)
    for r in rows:
        try:
            deleted_at = datetime.fromisoformat(r.get("deleted_at", ""))
        except Exception:
            deleted_at = None
        f = tdir / r.get("file", "")
        if deleted_at and deleted_at < cutoff and f.exists():
            f.unlink(missing_ok=True)
            removed.append(r.get("file"))
        elif f.exists():
            kept.append(r)
    # 兜底：清掉清单外的孤儿文件（按 mtime）
    known = {r.get("file") for r in kept}
    for f in tdir.iterdir():
        if f.name in (TRASH_JSON,) or f.is_dir() or f.name in known:
            continue
        try:
            mtime = datetime.fromtimestamp(f.stat().st_mtime)
        except OSError:
            continue
        if mtime < cutoff:
            f.unlink(missing_ok=True)
            removed.append(f.name)
    save_trash_manifest(ent, kept)
    return removed


# --------------------------------------------------------------------------
# 企业归属校验（文件名层）
# --------------------------------------------------------------------------
def ownership_check(ent, filename, extra_text=None):
    """
    依据文件名（及 agent 传入的正文/OCR 文本）判断素材是否疑似属于别的企业。
    返回 {"status": match|conflict|unknown, ...}
    """
    ent = Path(ent)
    meta = read_json(lib_root(ent) / META_JSON, {}) or {}
    my_name = meta.get("name") or ent.name
    my_tokens = _name_tokens(my_name)

    text = "%s %s" % (filename or "", extra_text or "")
    lib = Library(ent.parent)
    for other in lib.enterprises():
        if other == ent.name:
            continue
        other_meta = read_json(lib_root(ent.parent / other) / META_JSON, {}) or {}
        for t in _name_tokens(other_meta.get("name") or other):
            if t and t in text and t not in my_tokens:
                return {"status": "conflict", "other": other, "token": t}
    for t in my_tokens:
        if t and t in text:
            return {"status": "match", "token": t}
    return {"status": "unknown"}


# --------------------------------------------------------------------------
# 归档建议（propose）
# --------------------------------------------------------------------------
def _suggest_fields(filename, category, subtype, today=None):
    """从文件名里尽力抽出关键字与日期（供归档建议；人工/agent 可再修正）。"""
    today = today or today_str()
    stem, ext = nm.split_ext(filename)
    base, page = nm.split_page(stem)
    dates = nm.extract_dates(base)

    # 去掉日期与水印式分隔，切成候选 token
    rest = base
    for d in dates:
        rest = rest.replace(d, "_")
    rest = re.sub(r"[_\-]{2,}", "_", rest).strip("_-")
    tokens = [t for t in re.split(r"[_\-]", rest) if t]

    # 规则里的常量段（如「营业执照」「身份证」「简历」）不应留在关键字里
    try:
        segs = nm.get_rule(category, subtype)["segs"] if (category and subtype) else []
    except nm.NamingError:
        segs = []
    consts = [s[1] for s in segs if s[0] == nm.CONST]

    def strip_consts(ts):
        out = []
        for t in ts:
            v = t
            for c in consts:
                v = v.replace(c, "")
            if v.strip():
                out.append(v.strip())
        return out

    def side_of(text):
        if "国徽" in text or "背面" in text:
            return "国徽面"
        if "人像" in text or "正面" in text:
            return "人像面"
        return None

    keywords = []
    if category == "人员" and subtype == "身份证":
        side = side_of(base)
        keywords = [side] if side else []
        tokens = [t for t in strip_consts(tokens) if not any(k in t for k in ("正面", "背面"))]
    elif category == "人员" and subtype == "简历":
        dates = dates or [today]          # 简历按上传日期
        keywords = []
        tokens = strip_consts(tokens)
    elif subtype == "营业执照":
        keywords = [t for t in tokens if ("正本" in t or "副本" in t)]
        tokens = []
    elif subtype == "退休证":
        keywords = strip_consts(tokens)
        dates = dates or [nm.LONG_TERM]   # 退休证默认长期
        tokens = []
    elif subtype == "返聘协议":
        keywords = strip_consts(tokens)
        tokens = []
    else:
        toks = strip_consts(tokens)
        keywords = [toks[0]] if toks else []
        tokens = toks

    return {
        "keywords": keywords,
        "dates": dates,
        "page": page,
        "ext": ext,
        "stem": base,
        "leftover_tokens": tokens[1:] if (tokens and subtype not in ("营业执照", "退休证", "返聘协议")) else [],
    }


def _group_hint(items):
    """按主体名相似度给出多页归组提示（弱启发，最终由用户圈选）。"""
    buckets = {}
    for it in items:
        stem, _ = nm.split_ext(it.get("original_name", ""))
        base, page = nm.split_page(stem)
        key = re.sub(r"\d+$", "", base).strip("_-（）() ")
        buckets.setdefault(key, []).append(it.get("seq"))
    return {k: v for k, v in buckets.items() if len(v) > 1}


def propose(ent, require_closed=True):
    """为收件箱当前批次生成归档建议（供用户确认/修改）。"""
    ent = Path(ent)
    inbox = Inbox(ent)
    batch = inbox.load()
    if not batch:
        raise LibraryError("收件箱为空，无可归档内容（请先 open-inbox → upload → close-inbox）")
    if require_closed and not batch.get("closed_at"):
        raise LibraryError("收件箱尚未关闭（请先执行 close-inbox，再生成归档建议）")

    meta = read_json(lib_root(ent) / META_JSON, {}) or {}
    owner = meta.get("owner") or meta.get("name") or ent.name

    # 已有台账：同类别 → 关键字集合 + 主体（人员类按 rel_path 提取姓名）索引，用于归档时同名判定
    cat_index = defaultdict(list)
    for r in load_ledger(ent):
        c = r.get("category") or ""
        s = r.get("subtype") or ""
        kws = {k.strip() for k in str(r.get("keywords") or "").split("、") if k.strip()}
        rel = r.get("rel_path") or ""
        parts = rel.split("/")
        person = parts[1] if len(parts) > 1 and parts[0] == "人员" else ""
        cat_index[(c, s)].append({"rel_path": rel, "kw": kws, "person": person})

    items_out = []
    for it in inbox.items(order="seq"):
        orig = it.get("original_name", "")
        cat, sub, hit = nm.classify(orig)
        sug = _suggest_fields(orig, cat, sub)
        ownership = ownership_check(ent, orig)

        item = {
            "seq": it.get("seq"),
            "inbox_file": it.get("file"),
            "original_name": orig,
            "written_at": it.get("written_at"),
            "sha256": it.get("sha256"),
            "decision": "archive" if cat else "pending",
            "category": cat or "",
            "subtype": sub or "",
            "classify_hit": hit or "",
            "person": "",
            "project_folder": "",
            "keywords": sug["keywords"],
            "dates": sug["dates"],
            "date_type": nm.CATEGORY_META.get(cat, {}).get("date_label", ""),
            "page": sug["page"],
            "group_id": "",
            "final_name": "",
            "on_conflict": "",
            "ownership": ownership.get("status", "unknown"),
            "ownership_detail": ownership,
            "needs_input": [],
            "note": "",
            "is_name_conflict": False,
            "conflict_with": [],
            "conflict_in_batch": False,
        }
        # 同名检测：同大类 + 同子类；人员类须同人（person 未定时 apply 兜底重算），
        # 关键字排除等级/类型固定词后交集；固定词子类（简历/退休证等）同人即同名；
        # 同一素材的多页分页（同基名仅页码不同）不算冲突。
        if cat and sub:
            my_person = (item.get("person") or "").strip()
            conflict_existing = []
            for e in cat_index.get((cat, sub), []):
                e_item = {"category": cat, "subtype": sub, "person": my_person,
                          "keywords": item.get("keywords"),
                          "rel_path": e["rel_path"]}
                if _name_conflict_hit(e_item, {"category": cat, "subtype": sub,
                                               "keywords": "、".join(sorted(e["kw"])),
                                               "rel_path": e["rel_path"]}):
                    conflict_existing.append(e["rel_path"])
            conflict_in_batch = False
            for other in items_out:
                if other.get("seq") == item["seq"]:
                    continue
                if (other.get("category"), other.get("subtype")) != (cat, sub):
                    continue
                try:
                    my_base = nm.build_name(cat, sub, keywords=item.get("keywords"),
                                            dates=item.get("dates"), page=None)
                    o_base = nm.build_name(cat, sub, keywords=other.get("keywords"),
                                           dates=other.get("dates"), page=None)
                except Exception:
                    my_base = o_base = None
                if my_base and o_base and my_base == o_base:
                    continue   # 同基名不同页码（多页分页）
                if _name_conflict_hit(item, other):
                    conflict_in_batch = True
                    break
            if conflict_existing or conflict_in_batch:
                item["is_name_conflict"] = True
                item["on_conflict"] = ""  # 同名必须由用户确认处理方式（keep_both / skip / trash_old）
                item["conflict_with"] = conflict_existing
                item["conflict_in_batch"] = conflict_in_batch
        if not cat:
            item["needs_input"].append("请指定大类/子类（无法自动识别）")
        if cat == "人员" and sub != "简历":
            item["needs_input"].append("请提供人员姓名（作为人员子目录）")
        if cat == "业绩":
            item["needs_input"].append("请提供项目文件夹名（项目全名关键字_签订日期_总监）")
        if cat and sub:
            try:
                nm.build_name(cat, sub, keywords=item["keywords"], dates=item["dates"], page=item["page"])
            except nm.NamingError as e:
                item["needs_input"].append("字段不足：%s" % e)
        items_out.append(item)

    return {
        "enterprise": ent.name,
        "owner": owner,
        "batch_id": batch.get("batch_id"),
        "created_at": now_iso(),
        "time_collision": inbox.has_time_collision(),
        "group_hint": _group_hint(inbox.items()),
        "items": items_out,
    }


# --------------------------------------------------------------------------
# 归档执行（apply）
# --------------------------------------------------------------------------
def _target_rel(ent, item):
    """计算归档目标相对路径。"""
    cat = item.get("category")
    sub = item.get("subtype")
    if not cat:
        raise LibraryError("条目 %s 缺少大类" % item.get("inbox_file"))

    if item.get("final_name"):
        fname = item["final_name"]
        # final_name 不带扩展名时自动补源文件扩展名（避免归档后丢后缀）
        _, cur_ext = nm.split_ext(fname)
        if not cur_ext:
            ext = item.get("ext") or nm.split_ext(item.get("original_name", ""))[1]
            if ext:
                fname += ext
    else:
        fname = nm.build_name(
            cat, sub,
            keywords=item.get("keywords"),
            dates=item.get("dates"),
            page=item.get("page") if item.get("page") is not None else None,
            ext=None,
        )
        ext = item.get("ext") or nm.split_ext(item.get("original_name", ""))[1]
        if ext:
            fname += ext

    if cat == "人员":
        person = (item.get("person") or "").strip()
        if not person:
            raise LibraryError("人员素材必须提供 person（%s）" % item.get("inbox_file"))
        sub_dir = sub or "其他"
        if sub_dir not in PERSON_SUBDIRS:
            # 动态扩展：允许新子类，但记录
            pass
        return norm_rel("/".join([cat, nm.sanitize_keyword(person), sub_dir, fname]))

    if cat == "业绩":
        pf = (item.get("project_folder") or "").strip()
        if not pf:
            raise LibraryError("业绩素材必须提供 project_folder（%s）" % item.get("inbox_file"))
        return norm_rel("/".join([cat, pf, fname]))

    if cat == "财务":
        # 财务大类按子类建子目录（如 财务/中小企业声明函/…）
        sub_dir = sub or "财务证照"
        return norm_rel("/".join([cat, sub_dir, fname]))

    return norm_rel("/".join([cat, fname]))


# 人员类同名判定语义（见 _name_conflict_hit）：
# · 职称证书：实质标识 = 完整职称名（等级+专业，如 高级工程师_建筑电气）→ 基名相同才同名
# · 其余人员类子类（注册证书/岗位证书/身份证/简历/退休证/返聘协议/个人荣誉等）：
#   无独立身份标识 → 同人同子类即同名（新素材更新旧素材）
# · 同一素材多页分页（同基名不同页码 _P0/_P1）不构成同名


def _strip_page_suffix(fname):
    """去除文件名扩展名与多页分页后缀（_P0/_P1/…），得到素材基名。"""
    import re
    noext = str(fname).rsplit(".", 1)[0] if "." in str(fname) else str(fname)
    return re.sub(r"_P\d*$", "", noext)


def _ledger_person(rel_path):
    """从台账 rel_path 提取人员类主体姓名（rel_path 形如 人员/<姓名>/…）。"""
    parts = (rel_path or "").split("/")
    return parts[1] if len(parts) > 1 and parts[0] == "人员" else ""


def _name_conflict_hit(item, r):
    """判断提案条目与台账记录是否构成同名。

    同大类 + 同子类；人员类必须同人，且关键字（排除等级/类型固定词后）有交集；
    无实质关键字的固定词子类（如简历/退休证）同人即同名。非人员类按关键字交集。
    同一素材的多页分页（基名相同仅页码不同）不构成同名。
    """
    try:
        base_f = nm.build_name(
            item.get("category"), item.get("subtype") or nm.DEFAULT_SUBTYPE.get(item.get("category")),
            keywords=item.get("keywords"), dates=item.get("dates"), page=None)
    except Exception:
        base_f = None
    r_base = (r.get("rel_path") or "").rsplit("/", 1)[-1]
    if base_f and r_base.startswith(base_f + "_P"):
        return False
    my_kw = {k.strip() for k in (item.get("keywords") or []) if str(k).strip()}
    r_kw = {k.strip() for k in str(r.get("keywords") or "").split("、") if k.strip()}
    if (item.get("category") or "") == "人员":
        my_person = (item.get("person") or "").strip()
        r_person = _ledger_person(r.get("rel_path", ""))
        if not (my_person and r_person and my_person == r_person):
            return False
        sub = item.get("subtype") or ""
        if sub == "职称证书":
            # 职称证书的实质标识 = 完整职称名（等级+专业，如 高级工程师_建筑电气）
            try:
                my_base = nm.build_name("人员", sub, keywords=item.get("keywords"),
                                        dates=item.get("dates"), page=None)
            except Exception:
                my_base = None
            r_base = (r.get("rel_path") or "").rsplit("/", 1)[-1]
            r_clean = _strip_page_suffix(r_base)
            return bool(my_base and r_clean == my_base)
        # 其余人员类子类（注册证书/岗位证书/身份证/简历/退休证/返聘协议/个人荣誉等）：
        # 无独立身份标识，同人同子类即视为同名（新素材更新旧素材）
        return True
    return bool(my_kw & r_kw)


def _recalc_conflict(ent, item, rows):
    """以最终提案字段实时重算同名冲突。

    propose 生成提案时 person/keywords 可能为空（脚本无法从文件名语义认出主体），
    而 agent 会在提案中补齐（如固定词子类简历的 person）。apply 前以最终字段重算：
    同大类+同子类 → 关键字有交集 → 同名；关键字为空（固定词子类）→ 同主体
    （人员类按 rel_path 中的姓名）→ 同名（删除/更新语义）。
    命中且未确认 on_conflict 时置空（apply 将拒绝）；未命中则取消同名标记。
    """
    cat = item.get("category") or ""
    sub = item.get("subtype") or ""
    if not cat or not sub:
        return
    hits = []
    for r in rows:
        if (r.get("category") or "", r.get("subtype") or "") != (cat, sub):
            continue
        if _name_conflict_hit(item, r):
            hits.append(norm_rel(r.get("rel_path", "")))
    if hits:
        item["is_name_conflict"] = True
        item["conflict_with"] = hits
        # on_conflict 保持提案状态：默认 ""（未确认 → apply 拒绝）或用户显式确认值
        # （keep_both 并存 / trash_old 删除更新 / skip 跳过）
    else:
        item["is_name_conflict"] = False
        item["conflict_with"] = []


def apply(ent, proposal, require_closed=True):
    """按提案执行归档：改名 → 移动 → 写台账 → 清理收件箱。"""
    ent = Path(ent)
    inbox = Inbox(ent)
    batch = inbox.load()
    if not batch:
        raise LibraryError("收件箱为空，无法归档")
    if require_closed and not batch.get("closed_at"):
        raise LibraryError("收件箱尚未关闭（请先执行 close-inbox）")

    meta = read_json(lib_root(ent) / META_JSON, {}) or {}
    owner = meta.get("owner") or meta.get("name") or ent.name

    rows = load_ledger(ent)
    index = {norm_rel(r.get("rel_path", "")): r for r in rows}

    results = {"archived": [], "skipped": [], "trashed": [], "failed": []}
    handled_files = []

    by_seq = {i.get("seq"): i for i in batch.get("items", [])}

    # 单页去页码：同 target 基名在本次批次内只出现一次且 page==0 → 视为单页，去掉 _P0
    _single_base_counts = defaultdict(int)
    for _item in proposal.get("items", []):
        if _item.get("decision", "archive") in ("skip", "delete"):
            continue
        try:
            _f = nm.build_name(
                _item.get("category"), _item.get("subtype") or nm.DEFAULT_SUBTYPE.get(_item.get("category")),
                keywords=_item.get("keywords"), dates=_item.get("dates"), page=None,
            )
        except (nm.NamingError, Exception):
            continue
        _single_base_counts[(_item.get("category"), _f)] += 1

    for item in proposal.get("items", []):
        seq = item.get("seq")
        it = by_seq.get(seq)
        if not it:
            results["failed"].append({"seq": seq, "error": "批次中无此条目（可能已归档）"})
            continue

        decision = item.get("decision", "archive")
        src = inbox.path_of(it["file"])

        if decision == "skip":
            results["skipped"].append({"seq": seq, "file": it["file"]})
            continue
        if decision == "delete":
            try:
                move_to_trash(ent, norm_rel("收件箱/%s" % it["file"]), reason="归档时用户选择删除")
                results["trashed"].append({"seq": seq, "file": it["file"]})
                handled_files.append(it["file"])
            except LibraryError as e:
                results["failed"].append({"seq": seq, "error": str(e)})
            continue

        # 以最终提案字段实时重算同名（person/keywords 常由 agent 在 propose 后补齐）
        _recalc_conflict(ent, item, rows)

        if item.get("is_name_conflict") and not item.get("on_conflict"):
            results["failed"].append({
                "seq": seq, "file": it["file"],
                "error": "关键字同名素材：请先确认处理方式（keep_both / skip / trash_old）后再 apply",
            })
            continue

        # 同名删除/更新：on_conflict=trash_old 时，conflict_with 中的旧素材入回收站并清理旧台账行
        if item.get("is_name_conflict") and item.get("on_conflict") == "trash_old":
            conflict_failed = None
            for old_rel in item.get("conflict_with") or []:
                try:
                    old_rel = norm_rel(str(old_rel))
                    move_to_trash(ent, old_rel, reason="被新素材更新替代")
                    rows[:] = [r for r in rows if norm_rel(r.get("rel_path", "")) != old_rel]
                    index.pop(old_rel, None)
                except LibraryError as e:
                    conflict_failed = "删除旧素材失败：%s" % str(e)
                    break
            if conflict_failed:
                results["failed"].append({"seq": seq, "file": it["file"], "error": conflict_failed})
                continue

        # 单页去页码：page==0 且该 target 基名在批次内唯一 → 视为单页（page=None，不生成 _P0）
        if item.get("page") == 0:
            try:
                _f = nm.build_name(
                    item.get("category"), item.get("subtype") or nm.DEFAULT_SUBTYPE.get(item.get("category")),
                    keywords=item.get("keywords"), dates=item.get("dates"), page=None,
                )
            except (nm.NamingError, Exception):
                _f = None
            if _f and _single_base_counts.get((item.get("category"), _f)) == 1:
                item["page"] = None

        try:
            rel = _target_rel(ent, item)
        except (LibraryError, nm.NamingError) as e:
            results["failed"].append({"seq": seq, "file": it["file"], "error": str(e)})
            continue

        dest = rel_to_path(lib_root(ent), rel)
        dest.parent.mkdir(parents=True, exist_ok=True)

        if dest.exists():
            mode = item.get("on_conflict", "keep_both")
            if mode == "skip":
                results["skipped"].append({"seq": seq, "file": it["file"], "reason": "目标已存在，跳过"})
                continue
            if mode == "trash_old":
                move_to_trash(ent, rel, reason="被新素材覆盖")
                rows[:] = [r for r in rows if norm_rel(r.get("rel_path", "")) != rel]
                index.pop(rel, None)
            else:  # keep_both
                stem, ext = nm.split_ext(dest.name)
                n = 2
                while True:
                    cand = dest.with_name("%s_%d%s" % (stem, n, ext))
                    if not cand.exists():
                        dest = cand
                        break
                    n += 1
                rel = norm_rel(dest.relative_to(lib_root(ent)).as_posix())

        shutil.move(str(src), str(dest))

        cat = item.get("category")
        sub = item.get("subtype") or nm.DEFAULT_SUBTYPE.get(cat, "")
        row = new_ledger_row(
            category=cat,
            subtype=sub,
            rel_path=rel,
            keywords="、".join(item.get("keywords") or []),
            dates="、".join(item.get("dates") or []),
            date_type=item.get("date_type") or nm.CATEGORY_META.get(cat, {}).get("date_label", ""),
            owner=owner,
            upload_date=today_str(),
            original_filename=it.get("original_name", ""),
            source="收件箱",
            group_id=item.get("group_id", ""),
            page_index="" if item.get("page") is None else item.get("page"),
            ext=nm.split_ext(dest.name)[1],
            note=item.get("note", ""),
        )
        rows.append(row)
        index[rel] = row
        handled_files.append(it["file"])
        results["archived"].append({"seq": seq, "rel_path": rel, "id": row["id"]})

    save_ledger(ent, rows)
    inbox.remove_items(handled_files)

    results["summary"] = {
        "archived": len(results["archived"]),
        "skipped": len(results["skipped"]),
        "trashed": len(results["trashed"]),
        "failed": len(results["failed"]),
        "ledger_total": len(rows),
    }
    return results


# --------------------------------------------------------------------------
# 巡检（非常规上传 + 命名规范）
# --------------------------------------------------------------------------
def inspect(ent):
    """扫描分类目录：找出未经收件箱的素材（非常规上传）与命名不规范项。"""
    ent = Path(ent)
    index = ledger_index(ent)
    issues = []

    for cat in CLASSIFY_DIRS:
        d = lib_root(ent) / cat
        if not d.is_dir():
            continue
        for p in sorted(d.rglob("*")):
            if not p.is_file() or p.name.startswith("."):
                continue
            rel = norm_rel(p.relative_to(lib_root(ent)).as_posix())
            row = index.get(rel)

            if row:
                ok, msgs = nm.validate(row.get("category") or cat, row.get("subtype") or None, p.name)
                if not ok:
                    issues.append({
                        "type": "命名不规范",
                        "rel_path": rel,
                        "detail": "；".join(msgs),
                        "suggestion": nm.rule_hint(row.get("category") or cat, row.get("subtype") or None),
                    })
            else:
                guess_cat, guess_sub, _ = nm.classify(p.name)
                target_cat = guess_cat or cat
                ok, msgs = nm.validate(target_cat, guess_sub, p.name)
                issues.append({
                    "type": "非常规上传",
                    "rel_path": rel,
                    "detail": "该文件不在台账中（未经收件箱归档）",
                    "suggestion": nm.rule_hint(target_cat, guess_sub) if ok is False else "命名看似合规，仅需补登台账",
                    "guess": {"category": guess_cat, "subtype": guess_sub},
                })
                # 归属校验
                own = ownership_check(ent, p.name)
                if own.get("status") == "conflict":
                    issues.append({
                        "type": "企业归属疑似不符",
                        "rel_path": rel,
                        "detail": "文件名疑似属于其他企业：%s（命中“%s”）" % (own.get("other"), own.get("token")),
                    })

    # 台账有记录、磁盘上却已缺失
    for rel, row in index.items():
        if not rel_to_path(lib_root(ent), rel).exists():
            issues.append({
                "type": "台账悬空",
                "rel_path": rel,
                "detail": "台账有记录但文件已不存在（可能被手工移动/删除）",
            })

    return {
        "enterprise": ent.name,
        "scanned_at": now_iso(),
        "count": len(issues),
        "issues": issues,
    }


# --------------------------------------------------------------------------
# 检索
# --------------------------------------------------------------------------
def query(ent, category=None, keyword=None, subtype=None, expires_before=None,
          expires_after=None, owner=None):
    rows = load_ledger(ent)
    out = []
    for r in rows:
        if category and r.get("category") != category:
            continue
        if subtype and r.get("subtype") != subtype:
            continue
        if owner and owner not in (r.get("owner") or ""):
            continue
        if keyword:
            hay = " ".join([
                r.get("rel_path", ""), r.get("keywords", ""),
                r.get("subtype", ""), r.get("note", ""),
                r.get("original_filename", ""),
            ])
            if keyword not in hay:
                continue
        d = r.get("dates", "")
        first = (d.split("、")[0] if d else "") or ""
        dated = bool(re.match(r"^\d{8}$", first))
        if expires_before or expires_after:
            if not dated:
                continue  # 有日期筛选时，无有效日期的条目不计入
        if expires_before and dated and first >= expires_before:
            continue
        if expires_after and dated and first < expires_after:
            continue
        out.append(r)
    return out


# --------------------------------------------------------------------------
# 概览
# --------------------------------------------------------------------------
def enterprise_overview(ent):
    ent = Path(ent)
    rows = load_ledger(ent)
    by_cat = {}
    for r in rows:
        by_cat.setdefault(r.get("category", "未分类"), 0)
        by_cat[r.get("category", "未分类")] += 1

    disk = {}
    for cat in CLASSIFY_DIRS:
        d = lib_root(ent) / cat
        disk[cat] = sum(1 for p in d.rglob("*") if p.is_file()) if d.is_dir() else 0

    inbox = Inbox(ent)
    b = inbox.load()
    return {
        "enterprise": ent.name,
        "path": str(lib_root(ent)),
        "ledger_total": len(rows),
        "by_category": by_cat,
        "disk_files": disk,
        "inbox": {
            "open": bool(b and not b.get("closed_at")),
            "batch_id": (b or {}).get("batch_id"),
            "items": len((b or {}).get("items", [])),
        },
        "trash": len(trash_manifest(ent)),
    }
