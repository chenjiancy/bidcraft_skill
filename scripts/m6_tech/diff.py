# -*- coding: utf-8 -*-
"""
bidcraft · M6 技术标制作 —— T12 `tech-diff`（双通道差异比对，契约 §6.3 / V12）

 1. 通道A 机器结论（tech-check → 检查/覆盖矩阵_<项目>.json）
    vs 通道B agent 自述（章节/.meta/ch-*.selfcheck.json，M6-COVERAGE）
    → F10 compare_dual 四类差异：覆盖结论冲突 / 篇幅偏差>20% / 仅通道B / 仅通道A
 2. 差异清单落盘 `检查/双通道差异_<项目>.json/.md`（只读产物，供审计）
 3. 裁决纪律（V12 不静默）：`--verdict <json>` 逐项裁决（idx 全覆盖、verdict 合法）
    + `--confirm` 写入 confirmLog（gate=diff，items 条数须与差异一致）；
    无未裁决项方可 tech-export（export 侧 V12 检查）。
"""
import json
from pathlib import Path

from _shared import core
from . import rules, sources, store

DIFF_BASE = "双通道差异_%s"
VERDICTS = ("accept", "reject", "note")


def _load_machine(tech, project):
    p = tech / ("检查/覆盖矩阵_%s.json" % project)
    if not p.is_file():
        raise core.LibraryError("覆盖矩阵缺失：%s（请先 tech-check）" % p)
    try:
        return json.loads(p.read_text(encoding="utf-8")), p
    except ValueError as e:
        raise core.LibraryError("覆盖矩阵 JSON 损坏：%s（%s）" % (p, e))


def _collect_selfchecks(tech):
    """收集全部 .meta/ch-*.selfcheck.json（M6-COVERAGE 自述）→ {ch_id: payload}。"""
    meta = tech / "章节" / ".meta"
    out = {}
    if not meta.is_dir():
        return out
    for p in sorted(meta.glob("ch-*.selfcheck.json")):
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
        except ValueError as e:
            raise core.LibraryError("自述块 JSON 损坏：%s（%s）" % (p, e))
        cid = doc.get("chapter") or p.name
        if doc.get("block") == "M6-COVERAGE":
            out[cid] = doc
    return out


def _load_verdicts(args, proj):
    """读取逐项裁决 JSON（须位于本项目目录内）。"""
    p = sources.ensure_inside("裁决文件", args.verdict, proj)
    try:
        doc = json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise core.LibraryError("裁决文件无法解析：%s（%s）" % (p, e))
    items = doc.get("diffs") if isinstance(doc, dict) else None
    if not isinstance(items, list):
        raise core.LibraryError("裁决文件须为 {\"diffs\": [{\"idx\": 0, \"verdict\": \"accept|reject|note\"}]}")
    return items


def _validate_verdicts(items, diffs):
    """裁决与差异必须一一对应（V12：差异条数与裁决记录条数一致）。"""
    seen = set()
    for it in items:
        if not isinstance(it, dict):
            raise core.LibraryError("裁决项非法（须含 idx/verdict）")
        idx = it.get("idx")
        if not isinstance(idx, int) or idx < 0 or idx >= len(diffs):
            raise core.LibraryError("裁决 idx 越界：%r（差异共 %d 条）" % (idx, len(diffs)))
        if idx in seen:
            raise core.LibraryError("裁决 idx 重复：%d（每条差异只能裁决一次）" % idx)
        seen.add(idx)
        verdict = it.get("verdict")
        if verdict not in VERDICTS:
            raise core.LibraryError("裁决 verdict 非法：%r（允许 %s）" % (verdict, "/".join(VERDICTS)))
    if len(seen) != len(diffs):
        raise core.LibraryError("裁决条数 %d ≠ 差异条数 %d（不得静默跳过，V12）"
                                % (len(seen), len(diffs)))
    return [{"idx": i, "verdict": next(
        it["verdict"] for it in items if it["idx"] == i),
        "note": (next(it for it in items if it["idx"] == i).get("note") or "")[:120]}
        for i in range(len(diffs))]


def cmd_tech_diff(args):
    ent = sources.get_ent(args)
    proj = sources.proj_dir(ent, args.project)
    tech = sources.tech_dir(ent, args.project)
    machine, _ = _load_machine(tech, args.project)
    selfchecks = _collect_selfchecks(tech)
    diffs = rules.compare_dual(machine, selfchecks)

    doc = {"schema": "m6.diff/v1", "project": args.project,
           "note": "双通道差异（通道A tech-check 机器结论 vs 通道B agent 自述）",
           "diffs": diffs, "generated": core.now_iso()}
    base = DIFF_BASE % args.project
    json_path = tech / ("检查/%s.json" % base)
    md_path = tech / ("检查/%s.md" % base)
    md_lines = ["# 双通道差异 · %s" % args.project, "",
                "- 通道A：tech-check（机器，六项检查）｜通道B：agent 自述（M6-COVERAGE）",
                "- 差异类型：覆盖结论冲突 / 篇幅偏差 / 仅通道B / 仅通道A",
                "- 裁决：`tech-diff --verdict <json> --confirm`，条数须与差异一致（V12 不静默）", ""]
    if not diffs:
        md_lines.append("（两通道无实质差异）")
    for i, d in enumerate(diffs, 1):
        md_lines.append("%d. [%s] 章 %s｜%s" % (i, d["type"], d["chapter"] or "全局", d["item"]))
        md_lines.append("   %s" % d["detail"])
    json_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text("\n".join(md_lines), encoding="utf-8")
    core.readback.verify_json(json_path, required_fields=("project", "diffs"),
                              label="双通道差异 json")
    core.readback.verify_file(md_path, label="双通道差异 md")

    # 裁决（V12：不得静默判定）
    resolved = None
    if args.verdict:
        items = _load_verdicts(args, proj)
        resolved = _validate_verdicts(items, diffs)
        if not args.confirm:
            print("裁决校验通过（%d 条），需 --confirm 写入 confirmLog" % len(resolved))
    elif args.confirm:
        raise core.LibraryError("--confirm 须配合 --verdict <json> 逐项裁决（V12：不得静默判定）")

    if resolved and args.confirm:
        note = json.dumps({"items": resolved, "total": len(diffs)}, ensure_ascii=False)
        store.confirm_gate(tech, "diff", note=note)

    if args.json:
        out = {"project": args.project, "diffs": diffs,
               "resolved": resolved or [], "path": str(json_path)}
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0
    print("双通道差异：%d 条（%s）" % (len(diffs), "无差异" if not diffs else "须逐项裁决"))
    for i, d in enumerate(diffs, 1):
        print("  %d. [%s] 章 %s｜%s" % (i, d["type"], d["chapter"] or "全局", d["item"]))
        print("     %s" % d["detail"][:120])
    if resolved and args.confirm:
        print("裁决已落盘：confirmLog gate=diff，%d 条全部裁决" % len(resolved))
    print("落盘：%s / %s" % (json_path, md_path))
    if diffs and not (resolved and args.confirm):
        print("提示：tech-export 前须 tech-diff --verdict <json> --confirm 完成裁决（V12）")
    return 0
