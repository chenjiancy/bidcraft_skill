# -*- coding: utf-8 -*-
"""
bidcraft · M2 模板库 —— 存储/编排层（确定性文件操作）

职责边界
--------
- 只做确定性的文件系统操作与数据读写（台账 JSON/CSV 双写、docx 占位符扫描、
  模板导入、按代理机构/采购方式检索、目录对账），不做「看懂内容」的判断。
- 模板归属（哪个代理机构/哪种方式）、占位符含义（登记清单的「说明」列）等
  语义判断由 agent 完成，然后把结论作为参数传进来执行。

数据落位（企业级）：<软件根>/<企业>/企业级/模板库/<招标代理机构>/{投标,采购,询比价}/
依赖：Python 标准库（docx 占位符扫描用 zipfile + 正则提取 <w:t> 文本，无第三方包）。
"""

import csv
import json
import re
import shutil
import uuid
import zipfile
from pathlib import Path

from _shared import core

TEMPLATE_SUBPATH = ("企业级", "模板库")
LEDGER_JSON = "模板台账.json"
LEDGER_CSV = "模板台账.csv"
REGISTRY_MD = "占位符登记清单.md"

MODES = ["投标", "采购", "询比价"]
SCAN_EXTS = (".docx",)          # 标准库可扫描占位符的扩展名（.doc/.pdf 由 agent 提供占位符数）
UNSCANNABLE_HINT = "（.doc/.pdf 等由 agent 读取后经 tpl-import --placeholders 补录）"

TEMPLATE_COLUMNS = [
    "id", "代理机构", "方式", "文件", "相对路径",
    "占位符数", "图片占位符数", "登记清单", "备注", "added_at",
]

# 占位符正则：登记清单与模板正文统一使用 【…】 包裹（D3）；图片占位为 【图片：…】
_PH_RE = re.compile(r"【[^】]*】")
_IMG_PH_RE = re.compile(r"【图片：[^】]*】")

# XML 实体
_ENT = {"&lt;": "<", "&gt;": ">", "&quot;": '"', "&apos;": "'", "&amp;": "&"}


# --------------------------------------------------------------------------
# 路径与台账
# --------------------------------------------------------------------------
def template_root(ent):
    """<软件根>/<企业>/企业级/模板库（不创建）。"""
    return Path(ent).joinpath(*TEMPLATE_SUBPATH)


def _ledger_paths(ent):
    root = template_root(ent)
    return root / LEDGER_JSON, root / LEDGER_CSV


def load_ledger(ent):
    root = template_root(ent)
    p = root / LEDGER_JSON
    if p.exists():
        data = core.read_json(p, None)
        if isinstance(data, list):
            return data
    csvp = root / LEDGER_CSV
    if csvp.exists():
        with open(csvp, encoding="utf-8-sig", newline="") as f:
            return [dict(r) for r in csv.DictReader(f)]
    return []


def save_ledger(ent, rows):
    root = template_root(ent)
    root.mkdir(parents=True, exist_ok=True)
    rows = list(rows)
    (root / LEDGER_JSON).write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    with open(root / LEDGER_CSV, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=TEMPLATE_COLUMNS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in TEMPLATE_COLUMNS})


def init_ledger(ent, force=False):
    """初始化/复用模板台账（幂等；force 时以空台账覆盖，仅迁移场景用）。"""
    root = template_root(ent)
    root.mkdir(parents=True, exist_ok=True)
    existed = (root / LEDGER_JSON).exists() or (root / LEDGER_CSV).exists()
    if existed and not force:
        return True, load_ledger(ent)
    save_ledger(ent, [])
    return existed, []


def ledger_index(ent):
    """相对路径(规范化) -> row。"""
    return {core.norm_rel(r.get("相对路径", "")): r
            for r in load_ledger(ent) if r.get("相对路径")}


def new_row(agency, mode, fname, rel, ph=0, img_ph=0, registry="", note="", **kw):
    row = {c: "" for c in TEMPLATE_COLUMNS}
    row["id"] = uuid.uuid4().hex[:8]
    row["added_at"] = core.now_iso()
    row.update({
        "代理机构": agency, "方式": mode, "文件": fname,
        "相对路径": rel, "占位符数": str(ph), "图片占位符数": str(img_ph),
        "登记清单": registry, "备注": note,
    })
    row.update({k: str(v) for k, v in kw.items() if k in TEMPLATE_COLUMNS})
    return row


def _validate(agency, mode):
    if not agency or not str(agency).strip():
        raise core.LibraryError("代理机构不能为空")
    if mode not in MODES:
        raise core.LibraryError("采购方式必须为：%s" % "、".join(MODES))


def mode_dir(ent, agency, mode):
    """模板库/<代理机构>/<方式>（不创建）。"""
    _validate(agency, mode)
    return template_root(ent) / agency / mode


# --------------------------------------------------------------------------
# docx 占位符扫描（标准库：zipfile + 正则）
# --------------------------------------------------------------------------
def _docx_text(path):
    """提取 DOCX 全部 <w:t> 文本（按段落换行），供占位符统计。"""
    with zipfile.ZipFile(path) as z:
        if "word/document.xml" not in z.namelist():
            raise core.LibraryError("无法解析 DOCX：缺少 word/document.xml（文件可能损坏或非标准 docx）")
        xml = z.read("word/document.xml").decode("utf-8", errors="replace")
    out = []
    for m in re.finditer(r"<w:p[ >].*?</w:p>|<w:p/>", xml, flags=re.S):
        seg = m.group(0)
        parts = re.findall(r"<w:t[^>]*>(.*?)</w:t>", seg, flags=re.S)
        if parts:
            txt = "".join(parts)
            for k, v in _ENT.items():
                txt = txt.replace(k, v)
            out.append(txt)
    return "\n".join(out)


def scan_docx_placeholders(path):
    """统计 docx 模板正文中的占位符。返回 (总占位符数, 图片占位符数)。"""
    text = _docx_text(path)
    return len(_PH_RE.findall(text)), len(_IMG_PH_RE.findall(text))


def scan_placeholders(path):
    """按扩展名分发扫描；不支持的格式返回 None（由 agent 提供占位符数）。"""
    p = Path(path)
    if p.suffix.lower() in SCAN_EXTS:
        return scan_docx_placeholders(p)
    return None


# --------------------------------------------------------------------------
# 导入 / 检索 / 对账 / 概览
# --------------------------------------------------------------------------
def import_template(ent, agency, mode, src_path, note="", placeholders=None,
                    img_placeholders=None, registry=None, in_place=False):
    """
    导入一个模板文件到 模板库/<代理机构>/<方式>/ 并写台账。
    - 目标文件已存在（未用 --in-place）→ 报错（防覆盖，冲突走 agent/用户决策）。
    - in_place=True：登记模板库内已存在的文件（不复制）；要求源文件恰好在目标目录下。
    - 占位符：docx 自动扫描；不支持的格式需由 agent 经 placeholders/img_placeholders 传入。
    """
    _validate(agency, mode)
    src = Path(src_path)
    if not src.is_file():
        raise core.LibraryError("源文件不存在：%s" % src)
    if src.suffix.lower() not in (".docx", ".doc", ".pdf", ".txt", ".md"):
        raise core.LibraryError("不支持的模板格式：%s（支持 docx/doc/pdf/txt/md）" % src.suffix)

    dst_dir = mode_dir(ent, agency, mode)
    dst_dir.mkdir(parents=True, exist_ok=True)
    fname = src.name
    dst = dst_dir / fname

    if in_place:
        if src.parent.resolve() != dst_dir.resolve():
            raise core.LibraryError("--in-place 要求源文件已在目标目录：%s" % dst_dir)
    else:
        if dst.exists():
            raise core.LibraryError("目标文件已存在：%s（如需覆盖/替换，请先人工确认后处理）"
                                    % core.norm_rel(str(dst)))

    rel = core.norm_rel(str(dst.relative_to(Path(ent))))
    if rel in ledger_index(ent):
        raise core.LibraryError("该模板已登记：%s" % rel)

    # 占位符统计
    scanned = scan_placeholders(src)
    if scanned is not None:
        ph, img_ph = scanned
    else:
        if placeholders is None:
            raise core.LibraryError(
                "该格式无法自动扫描占位符，请用 --placeholders/--img-placeholders 提供；%s" % UNSCANNABLE_HINT)
        ph, img_ph = int(placeholders), int(img_placeholders or 0)

    if not in_place:
        shutil.copy2(src, dst)
    reg = registry if registry is not None else (dst_dir / REGISTRY_MD).name
    row = new_row(agency, mode, fname, rel, ph=ph, img_ph=img_ph,
                  registry=reg if reg else "", note=note or "")
    rows = load_ledger(ent)
    rows.append(row)
    save_ledger(ent, rows)
    return row


def list_templates(ent, agency=None, mode=None):
    rows = load_ledger(ent)
    out = []
    for r in rows:
        if agency and r.get("代理机构") != agency:
            continue
        if mode and r.get("方式") != mode:
            continue
        out.append(r)
    return out


def query_templates(ent, agency=None, mode=None, keyword=None):
    rows = load_ledger(ent)
    out = []
    for r in rows:
        if agency and r.get("代理机构") != agency:
            continue
        if mode and r.get("方式") != mode:
            continue
        if keyword:
            hay = " ".join([
                r.get("文件", ""), r.get("相对路径", ""),
                r.get("代理机构", ""), r.get("备注", ""),
            ])
            if keyword not in hay:
                continue
        out.append(r)
    return out


def sync_templates(ent):
    """
    目录与台账对账（确定性）：
      missing_rows  台账有记录但文件已不在磁盘（相对路径）
      new_files     磁盘有文件但台账无记录（需登记）
      stale_rows    台账记录的目标文件仍存在但被改名/挪走（按原相对路径判定为 missing）
    返回 {"missing_rows": [...], "new_files": [...]}
    """
    root = template_root(ent)
    rows = load_ledger(ent)
    idx = ledger_index(ent)

    ent = Path(ent)
    missing = []
    for rel, r in idx.items():
        if not (ent / rel).exists():
            missing.append(r)

    new_files = []
    if root.is_dir():
        for d in sorted(root.rglob("*")):
            if not d.is_file():
                continue
            if d.name.startswith("~$") or d.name in (LEDGER_JSON, LEDGER_CSV, REGISTRY_MD):
                continue
            rel = core.norm_rel(str(d.relative_to(Path(ent))))
            if rel not in idx:
                # 提取所属代理机构/方式
                parts = d.relative_to(root).parts
                if len(parts) >= 2 and parts[0] and parts[1] in MODES:
                    new_files.append({
                        "相对路径": rel, "代理机构": parts[0], "方式": parts[1], "文件": d.name,
                    })
                else:
                    new_files.append({"相对路径": rel, "代理机构": "", "方式": "", "文件": d.name})
    return {"missing_rows": missing, "new_files": new_files}


def overview(ent):
    rows = load_ledger(ent)
    by_agency = {}
    for r in rows:
        a = r.get("代理机构", "未分类")
        m = r.get("方式", "未分类")
        by_agency.setdefault(a, {}).setdefault(m, 0)
        by_agency[a][m] += 1
    return {
        "enterprise": Path(ent).name,
        "ledger_total": len(rows),
        "by_agency": by_agency,
    }


def registry_path(ent, agency, mode):
    """登记清单文件路径（模板库/<代理机构>/<方式>/占位符登记清单.md）。"""
    return mode_dir(ent, agency, mode) / REGISTRY_MD


def read_registry(ent, agency, mode, file_filter=None):
    """
    读取某代理机构/方式下的占位符登记清单.md。
    返回 {"exists": bool, "path": str, "content": str}；file_filter 时只保留含该文件名的节。
    """
    p = registry_path(ent, agency, mode)
    if not p.exists():
        return {"exists": False, "path": str(p), "content": ""}
    content = p.read_text(encoding="utf-8")
    if file_filter:
        keep = []
        cur = []
        cur_head = ""
        for line in content.splitlines():
            if line.startswith("## ") or line.startswith("# "):
                if cur_head and file_filter in cur_head:
                    keep.extend(cur)
                cur = [line]
                cur_head = line
            else:
                cur.append(line)
        if cur_head and file_filter in cur_head:
            keep.extend(cur)
        content = "\n".join(keep)
    return {"exists": True, "path": str(p), "content": content}
