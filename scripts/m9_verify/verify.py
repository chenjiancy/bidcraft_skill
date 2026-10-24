# -*- coding: utf-8 -*-
"""
bidcraft · M9 取证/自检 —— 纯逻辑（无 I/O；CLI 见 m9_verify/__init__.py）

run_checks(proj_dir)：确定性断言体检（每项 id/模块/检查/状态/依据；fail=产物缺失或契约破坏，
warn=可整改提示，pass=满足）→ 红绿灯汇总。
collect_evidence(proj_dir)：投标留痕包（M4→M6→M7→M8→M10 全过程产物索引 + 关键状态提取）。
"""
import datetime as _dt
from pathlib import Path


def _now():
    return _dt.datetime.now().strftime("%Y-%m-%d %H:%M")


def _exists(*parts):
    return Path(*parts)


def _js(path):
    import json
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _tech_settings(proj_dir, project):
    p = proj_dir / "技术标" / "设置.json"
    if not p.is_file():
        return None, None
    return _js(p), p


def _task_doc(proj_dir, project):
    p = proj_dir / "模拟评标" / ("失分补救任务单_%s.json" % project)
    return (_js(p) if p.is_file() else None), p


def _recheck_doc(proj_dir, project):
    p = proj_dir / "模拟评标" / ("补救后重检报告_%s.json" % project)
    return (_js(p) if p.is_file() else None), p


def run_checks(proj_dir, project):
    """确定性断言体检：产物齐不齐 / 契约对不对 / 闭环通不通。返回 (checks, overall)。"""
    checks = []
    pdir = Path(proj_dir)

    def add(cid, module, check, status, evidence):
        checks.append({"id": cid, "模块": module, "检查": check, "状态": status, "依据": evidence})

    # —— M4 招标解析 ——
    points = _exists(pdir, "招标解析", "投标要点_%s.json" % project)
    mat = _exists(pdir, "招标解析", "素材清单_%s.json" % project)
    add("m4_points", "M4", "投标要点解析产物存在", "pass" if points.is_file() else "fail",
        "存在" if points.is_file() else "缺失：招标解析/投标要点_%s.json（先 tech-init/招标解析）" % project)
    add("m4_mat", "M4", "素材清单存在", "pass" if mat.is_file() else "fail",
        "存在" if mat.is_file() else "缺失：招标解析/素材清单_%s.json（先素材归档/招标解析）" % project)

    # —— M6 技术标 ——
    tdocx = _exists(pdir, "技术标", "产出", "技术标_%s.docx" % project)
    add("m6_docx", "M6", "技术标成稿 docx 存在且非空", "pass" if tdocx.is_file() and tdocx.stat().st_size > 0 else "fail",
        "存在（%.0f KB）" % (tdocx.stat().st_size / 1024) if tdocx.is_file() else "缺失：技术标/产出/技术标_%s.docx" % project)
    settings, sp = _tech_settings(pdir, project)
    if settings:
        bid_mode = settings.get("bidMode") or "未知"
        add("m6_settings", "M6", "技术标设置.json 可读（bidMode）", "pass", "bidMode=%s" % bid_mode)
    else:
        add("m6_settings", "M6", "技术标设置.json 可读（bidMode）", "warn" if tdocx.is_file() else "fail",
            "缺失：技术标/设置.json（tech-init 未产出设置；docx 已存在时降级为可整改项）")

    # —— M7 机器检查 ——
    cjson = _exists(pdir, "标书检查", "机器检查_%s_技术标.json" % project)
    check_doc = _js(cjson) if cjson.is_file() else None
    if check_doc:
        items = check_doc.get("检查") or []
        n_ok = sum(1 for c in items if c.get("ok"))
        n_total = len(items)
        failed = [c.get("id") for c in items if not c.get("ok") and (c.get("issues") or [])]
        if n_total == 0:
            add("m7_check", "M7", "技术标机器检查已执行（6 项）", "fail", "检查列表为空，检查未实际执行")
        else:
            status = "pass" if n_ok == n_total else "warn"
            add("m7_check", "M7", "技术标机器检查已执行（%d 项）" % n_total, status,
                "%d/%d 通过%s" % (n_ok, n_total, ("；未通过：" + "、".join(failed)) if failed else ""))
    else:
        add("m7_check", "M7", "技术标机器检查已执行", "fail",
            "缺失：标书检查/机器检查_%s_技术标.json（先 check-rule --kind tech）" % project)

    # —— M8 模拟评标 ——
    ep = _exists(pdir, "模拟评标", "模拟评标_%s.json" % project)
    eval_doc = _js(ep) if ep.is_file() else None
    if eval_doc:
        issues = ((eval_doc.get("summary") or {}).get("issues") or [])
        gap = sum((i.get("gap") or 0) for i in issues)
        add("m8_eval", "M8", "模拟评标已执行（失分诊断）", "pass" if gap == 0 else "warn",
            "失分合计 %.1f 分（%d 项）" % (gap, len(issues)) if gap else "无失分（全部满分）")
    else:
        add("m8_eval", "M8", "模拟评标已执行", "fail",
            "缺失：模拟评标/模拟评标_%s.json（先 eval-run/eval-report）" % project)

    # —— M10 补救闭环 ——
    task_doc, tp = _task_doc(pdir, project)
    recheck_doc, rp = _recheck_doc(pdir, project)
    if task_doc:
        tasks = task_doc.get("tasks") or []
        done = sum(1 for t in tasks if t.get("完成状态") == "已完成")
        if tasks:
            if done == len(tasks):
                add("m10_tasks", "M10", "补救任务单全部勾选完成", "pass", "%d/%d 已勾选" % (done, len(tasks)))
            else:
                add("m10_tasks", "M10", "补救任务单全部勾选完成", "warn",
                    "%d/%d 已勾选（剩余：%s）" % (done, len(tasks), "、".join(
                        t.get("id", "?") for t in tasks if t.get("完成状态") != "已完成")))
        else:
            add("m10_tasks", "M10", "补救任务单含任务", "warn", "任务单存在但任务为空（remedy-gen 未产出整改任务）")
    else:
        add("m10_tasks", "M10", "补救任务单存在", "warn" if eval_doc else "pass",
            "任务单缺失（M8 失分未补救；无失分或未执行 remedy-gen）")

    if recheck_doc:
        s = recheck_doc.get("summary") or {}
        n_pass = s.get("验证通过") or 0
        n_done = s.get("已勾选任务") or 0
        if n_done > 0 and n_pass == n_done:
            add("m10_recheck", "M10", "补救后重检全部通过", "pass", "%d/%d 通过" % (n_pass, n_done))
        else:
            add("m10_recheck", "M10", "补救后重检全部通过", "warn",
                "%d/%d 通过（未通过/需人工复核见 补救后重检报告_%s.html）" % (n_pass, n_done, project))
    else:
        done_count = 0
        if task_doc:
            done_count = sum(1 for t in (task_doc.get("tasks") or []) if t.get("完成状态") == "已完成")
        if done_count:
            add("m10_recheck", "M10", "补救后重检已执行", "warn",
                "有 %d 个任务已勾选完成但未见 补救后重检报告_%s.json（先 remedy-recheck）" % (done_count, project))
        else:
            add("m10_recheck", "M10", "补救后重检已执行", "pass",
                "无已勾选任务，重检非必须（remedy-done 勾选后 remedy-recheck 复核）")

    fails = [c for c in checks if c["状态"] == "fail"]
    warns = [c for c in checks if c["状态"] == "warn"]
    if fails:
        overall = "红灯"
        conclusion = "体检发现 %d 项必做未做（%s）；补齐后重跑 m9-verify" % (
            len(fails), "、".join(c["id"] for c in fails))
    elif warns:
        overall = "黄灯"
        conclusion = "产物齐备，但有 %d 项可整改提示（%s）；整改后重跑 m9-verify 复核" % (
            len(warns), "、".join(c["id"] for c in warns))
    else:
        overall = "绿灯"
        conclusion = "全过程产物齐备、检查通过、补救闭环完成；可进入投标决策（人工确认闸门：以评标委员会评审为准）"
    return checks, overall, conclusion, _now()


def collect_evidence(proj_dir, project):
    """投标留痕包：全过程产物索引（模块/相对路径/存在/大小/摘要）。"""
    pdir = Path(proj_dir)
    specs = [
        ("M4", "投标要点", "招标解析", "投标要点_%s.json" % project),
        ("M4", "素材清单", "招标解析", "素材清单_%s.json" % project),
        ("M6", "技术标成稿", "技术标/产出", "技术标_%s.docx" % project),
        ("M6", "技术标设置", "技术标", "设置.json"),
        ("M7", "技术标机器检查", "标书检查", "机器检查_%s_技术标.json" % project),
        ("M8", "模拟评标", "模拟评标", "模拟评标_%s.json" % project),
        ("M8", "主观评审", "模拟评标", "主观评审_%s.json" % project),
        ("M10", "失分补救任务单", "模拟评标", "失分补救任务单_%s.json" % project),
        ("M10", "补救后重检报告", "模拟评标", "补救后重检报告_%s.json" % project),
    ]
    items = []
    for module, name, sub, fname in specs:
        p = pdir / sub / fname
        if p.is_file():
            size = p.stat().st_size
            items.append({"模块": module, "产物": name, "相对路径": str(p.relative_to(pdir)).replace("\\", "/"),
                          "存在": True, "大小": "%.0f KB" % (size / 1024)})
        else:
            items.append({"模块": module, "产物": name, "相对路径": str((pdir / sub / fname).relative_to(pdir)).replace("\\", "/"),
                          "存在": False, "大小": "—"})

    # 关键状态提取
    checks, overall, conclusion, ts = run_checks(pdir, project)
    kpi = {"检查项通过": None, "失分合计": None, "任务完成率": None, "重检通过率": None, "总评": overall}
    cjson = pdir / "标书检查" / ("机器检查_%s_技术标.json" % project)
    cd = _js(cjson) if cjson.is_file() else None
    if cd and (cd.get("检查") or []):
        items_c = cd.get("检查") or []
        kpi["检查项通过"] = "%d/%d" % (sum(1 for c in items_c if c.get("ok")), len(items_c))
    ep = pdir / "模拟评标" / ("模拟评标_%s.json" % project)
    ed = _js(ep) if ep.is_file() else None
    if ed:
        kpi["失分合计"] = round(sum((i.get("gap") or 0) for i in ((ed.get("summary") or {}).get("issues") or [])), 1)
    td, _tp = _task_doc(pdir, project)
    if td and (td.get("tasks") or []):
        tasks = td.get("tasks") or []
        kpi["任务完成率"] = "%d/%d" % (sum(1 for t in tasks if t.get("完成状态") == "已完成"), len(tasks))
    rd, _rp = _recheck_doc(pdir, project)
    if rd:
        s = rd.get("summary") or {}
        n_done = s.get("已勾选任务") or 0
        if n_done:
            kpi["重检通过率"] = "%d/%d" % (s.get("验证通过") or 0, n_done)

    return {"project": project, "生成依据": "M9 取证：投标全过程产物留痕（M4→M6→M7→M8→M10）",
            "生成时间": ts, "总评": overall, "结论": conclusion, "KPI": kpi,
            "检查明细": checks, "产物清单": items}
