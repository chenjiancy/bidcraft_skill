# -*- coding: utf-8 -*-
"""⑦ core 拆包 · 台账（⑩ 单源：JSON 权威，CSV 按需导出）。"""
import csv
import json
import uuid
from pathlib import Path

from .basic import (LEDGER_COLUMNS, LEDGER_CSV, LEDGER_JSON, lib_root,
                    norm_rel, now_iso, read_json, today_str)

__all__ = ["load_ledger", "save_ledger", "export_ledger_csv", "ledger_index",
           "new_ledger_row"]


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
    """⑩ 台账单源化：只写 JSON（权威）；CSV 按需 export_ledger_csv 导出，避免双写漂移。"""
    ent = Path(ent)
    lib = lib_root(ent)
    rows = list(rows)
    (lib / LEDGER_JSON).write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def export_ledger_csv(ent, rows=None):
    """⑩ 按需导出 CSV（UTF-8 BOM，人读友好）；rows 缺省时从当前 JSON 台账读。"""
    ent = Path(ent)
    lib = lib_root(ent)
    if rows is None:
        rows = load_ledger(ent)
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
