# -*- coding: utf-8 -*-
"""
bidcraft · 产物反馈机制 —— 存储/编排层（确定性文件操作）

职责边界
--------
- 只做确定性的数据读写与比对：产物基线登记/刷新、变更检测（未变/已改/缺失）、
  文本级差异提取、评估报告骨架生成。
- 「改了什么、建议如何完善系统功能」的语义判断由 agent 完成，
  agent 在评估报告骨架的基础上补充完善点建议，最终由用户确认后才受控应用。

数据落位（企业级）：<软件根>/<企业>/产物基线.json + <软件根>/<企业>/产物反馈/
依赖：Python 标准库。
"""

import csv
import difflib
import json
import re
import uuid
from datetime import datetime
from pathlib import Path

from _shared import core

BASELINE_JSON = "产物基线.json"
FEEDBACK_DIR = "产物反馈"
REPORT_PREFIX = "评估报告_"
CHANGELOG_MD = "变更日志.md"

BASELINE_COLUMNS = [
    "id", "层级", "项目", "产物类型", "相对路径",
    "sha256", "版本", "生成器", "登记时间", "文本指纹",
]

# 系统自身文件（不算人工改动；audit 排除 + baseline 不登记）
EXCLUDE_NAMES = {
    BASELINE_JSON, "模板台账.json", "模板台账.csv", "素材台账.json", "素材台账.csv",
    "_素材库信息.json", "_batch.json", "_回收站清单.json", "_归档提案.json",
    CHANGELOG_MD,
}


class FeedbackError(RuntimeError):
    pass


def feedback_root(ent):
    """<软件根>/<企业>/产物反馈（不创建）。"""
    return Path(ent) / FEEDBACK_DIR


def baseline_path(ent):
    return Path(ent) / BASELINE_JSON


def _load_raw(ent):
    p = baseline_path(ent)
    if p.exists():
        data = core.read_json(p, None)
        if isinstance(data, list):
            return data
    return []


def load_baseline(ent):
    return _load_raw(ent)


def save_baseline(ent, rows):
    baseline_path(ent).write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def baseline_index(ent):
    return {core.norm_rel(r.get("相对路径", "")): r for r in load_baseline(ent)
            if r.get("相对路径")}


def _text_fingerprint(path):
    """docx 提取段落文本；txt/md/json/csv 原文；其他返回 ''。"""
    p = Path(path)
    if p.suffix.lower() == ".docx":
        try:
            import zipfile
            with zipfile.ZipFile(p) as z:
                if "word/document.xml" not in z.namelist():
                    return ""
                xml = z.read("word/document.xml").decode("utf-8", errors="replace")
            out = []
            for m in re.finditer(r"<w:p[ >].*?</w:p>|<w:p/>", xml, flags=re.S):
                parts = re.findall(r"<w:t[^>]*>(.*?)</w:t>", m.group(0), flags=re.S)
                if parts:
                    out.append("".join(parts).replace("&lt;", "<").replace("&gt;", ">")
                               .replace("&quot;", '"').replace("&apos;", "'").replace("&amp;", "&"))
            return "\n".join(out)
        except Exception:
            return ""
    if p.suffix.lower() in (".txt", ".md", ".json", ".csv"):
        try:
            return p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return ""
    return ""


def register(ent, rel_path, level="项目级", project="", ptype="", generator="",
             version=None, note=""):
    """
    登记/刷新单个产物基线。
    - 未登记过 → 新增条目（版本默认 v1）。
    - 已登记 → 刷新：sha256/文本指纹更新，版本 bump（除非 version 显式给出）。
    """
    ent = Path(ent)
    rel = core.norm_rel(rel_path)
    abs_path = ent / rel
    if not abs_path.is_file():
        raise FeedbackError("产物不存在：%s" % rel)
    if abs_path.name in EXCLUDE_NAMES or abs_path.name.startswith("~$"):
        raise FeedbackError("系统文件不登记基线：%s" % rel)

    rows = load_baseline(ent)
    # 重要：索引必须基于同一份 rows 构建（baseline_index 会重新读盘，
    # 得到不同对象，改了 idx[rel] 也影响不到 rows，导致保存失效——⑥ 踩坑）
    idx = {core.norm_rel(r.get("相对路径", "")): r for r in rows if r.get("相对路径")}
    sha = core.sha256_of(abs_path)
    fp = _text_fingerprint(abs_path)
    now = core.now_iso()
    if rel in idx:
        row = idx[rel]
        row["sha256"] = sha
        row["文本指纹"] = fp
        row["登记时间"] = now
        if version is not None:
            row["版本"] = str(version)
        else:
            try:
                row["版本"] = "v%d" % (int(str(row.get("版本", "v1")).lstrip("v")) + 1)
            except ValueError:
                row["版本"] = "v1"
        if level:
            row["层级"] = level
        if project:
            row["项目"] = project
        if ptype:
            row["产物类型"] = ptype
        if generator:
            row["生成器"] = generator
        if note:
            row.setdefault("备注", note)
        save_baseline(ent, rows)
        return row
    row = {c: "" for c in BASELINE_COLUMNS}
    row.update({
        "id": uuid.uuid4().hex[:8],
        "层级": level, "项目": project, "产物类型": ptype, "相对路径": rel,
        "sha256": sha, "版本": version or "v1", "生成器": generator,
        "登记时间": now, "文本指纹": fp,
    })
    if note:
        row["备注"] = note
    rows.append(row)
    save_baseline(ent, rows)
    return row


def unregister(ent, rel_path):
    """从基线移除（产物被删除/移出时）。返回是否移除。"""
    rel = core.norm_rel(rel_path)
    rows = load_baseline(ent)
    out = [r for r in rows if core.norm_rel(r.get("相对路径", "")) != rel]
    removed = len(out) != len(rows)
    if removed:
        save_baseline(ent, out)
    return removed


def audit(ent, full=False, path=None):
    """
    变更检测（四态）：
      unchanged  未变（哈希一致）
      modified   已改（哈希不一致）——人工修改的主要信号
      missing    缺失（基线有、磁盘无）
    full=True 时对 modified 做文本级差异（difflib 行级），输出差异摘要。
    返回 {"checked": n, "unchanged": [...], "modified": [...], "missing": [...], "diffs": {...}}
    """
    ent = Path(ent)
    rows = load_baseline(ent)
    idx = baseline_index(ent)
    unchanged, modified, missing = [], [], []
    diffs = {}
    if path:
        rel = core.norm_rel(path)
        targets = [r for r in rows if core.norm_rel(r.get("相对路径", "")) == rel]
    else:
        targets = rows
    for r in targets:
        rel = core.norm_rel(r.get("相对路径", ""))
        abs_path = ent / rel
        if not abs_path.is_file():
            missing.append(r)
            continue
        sha = core.sha256_of(abs_path)
        if sha == r.get("sha256"):
            unchanged.append(r)
            continue
        modified.append(r)
        if full:
            old_fp = r.get("文本指纹", "")
            new_fp = _text_fingerprint(abs_path)
            if old_fp and new_fp and old_fp != new_fp:
                diff = list(difflib.unified_diff(
                    old_fp.splitlines(), new_fp.splitlines(),
                    fromfile="基线 v%s" % r.get("版本"), tofile="当前",
                    lineterm="", n=1))
                diffs[rel] = diff[:200]   # 截断，防爆
            else:
                diffs[rel] = ["（文本指纹不可比：旧=%s 新=%s）" % (bool(old_fp), bool(new_fp))]
    return {
        "checked": len(targets), "unchanged": unchanged, "modified": modified,
        "missing": missing, "diffs": diffs,
    }


def report(ent, audit_result=None, out=None, draft=True):
    """
    生成《系统功能更新评估报告》md（骨架）：
    变更概览 + 差异摘要 + 完善点建议（agent 补充） + 影响面/风险 + 确认栏。
    返回报告路径。
    """
    ent = Path(ent)
    if audit_result is None:
        audit_result = audit(ent, full=True)
    fdir = feedback_root(ent)
    fdir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = out or (fdir / ("%s%s.md" % (REPORT_PREFIX, ts)))

    lines = ["# 系统功能更新评估报告", ""]
    lines.append("- 报告编号：FR-%s ｜ 生成时间：%s ｜ 触发：自动检测/手动 audit" % (ts, core.now_iso()))
    lines.append("- 审计范围：基线 %d 条；未变 %d / 已改 %d / 缺失 %d"
                 % (audit_result["checked"], len(audit_result["unchanged"]),
                    len(audit_result["modified"]), len(audit_result["missing"])))
    lines.append("")
    lines.append("## 1. 变更概览")
    lines.append("| 文件 | 状态 | 原版本 | 类型 |")
    lines.append("|---|---|---|---|")
    for r in audit_result["modified"]:
        lines.append("| %s | 已改 | %s | %s |" % (r.get("相对路径", ""), r.get("版本", ""), r.get("产物类型", "")))
    for r in audit_result["missing"]:
        lines.append("| %s | 缺失 | %s | %s |" % (r.get("相对路径", ""), r.get("版本", ""), r.get("产物类型", "")))
    lines.append("")
    lines.append("## 2. 差异摘要")
    if audit_result["diffs"]:
        for rel, d in audit_result["diffs"].items():
            lines.append("### %s" % rel)
            lines.append("```diff")
            lines.extend(d)
            lines.append("```")
    else:
        lines.append("（无文本级差异——仅哈希变化或指纹不可比，需人工查看）")
    lines.append("")
    lines.append("## 3. 完善点建议（agent 补充，待人工确认）")
    lines.append("- [ ] 数据层：")
    lines.append("- [ ] 代码层：")
    lines.append("")
    lines.append("## 4. 影响面与风险")
    lines.append("- 涉及模块/产物/流程：")
    lines.append("- 代码层是否需回归：")
    lines.append("- 回滚方案：")
    lines.append("")
    lines.append("## 5. 建议动作")
    lines.append("- 采纳项：")
    lines.append("- 驳回项：")
    lines.append("")
    lines.append("## 6. 确认栏（待人工确认）")
    lines.append("- [ ] 全部采纳　[ ] 部分采纳（注明编号）　[ ] 驳回")
    lines.append("")
    Path(report_path).write_text("\n".join(lines), encoding="utf-8")
    return str(report_path)


def append_changelog(ent, entry):
    """受控应用后记录变更日志（追加）。"""
    fdir = feedback_root(ent)
    fdir.mkdir(parents=True, exist_ok=True)
    p = fdir / CHANGELOG_MD
    block = "\n- **%s** %s\n" % (core.now_iso(), entry)
    with open(p, "a", encoding="utf-8") as f:
        f.write(block)


def status(ent):
    rows = load_baseline(ent)
    by_type = {}
    for r in rows:
        t = r.get("产物类型", "未分类")
        by_type[t] = by_type.get(t, 0) + 1
    return {
        "enterprise": Path(ent).name,
        "baseline_total": len(rows),
        "by_type": by_type,
        "baseline_path": str(baseline_path(ent)),
        "feedback_dir": str(feedback_root(ent)),
    }
