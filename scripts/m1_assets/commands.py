# -*- coding: utf-8 -*-
"""
bidcraft · M1 素材库 —— 模块子包（命令实现 + 子命令注册）

用法总览（示例）
----------------
  # 0) 建企业（首次调用 skill 必做；软件目录三层结构由 init-enterprise 生成）
  python bidcraft.py init-enterprise --name "示例XX工程监理有限公司"

  # 1) 打开收件箱 → 逐张上传 → 关闭收件箱
  python bidcraft.py open-inbox
  python bidcraft.py upload --file "D:/下载/营业执照.jpg"
  python bidcraft.py upload --file "D:/下载/张三身份证正面.jpg"
  python bidcraft.py close-inbox

  # 2) 生成归档建议（半自动：人来确认/修改）
  python bidcraft.py propose --out 归档提案.json

  # 3) 按提案执行归档
  python bidcraft.py apply --proposal 归档提案.json

  # 4) 巡检（非常规上传 + 命名规范 + 归属）
  python bidcraft.py inspect

  # 5) 检索 / 概览 / 回收站
  python bidcraft.py query --category 人员 --keyword 监理工程师
  python bidcraft.py overview
  python bidcraft.py cleanup-trash --days 30

素材库根目录（软件根）优先级：--root 参数 > 环境变量 BIDCRAFT_LIB_ROOT > 当前目录下的「素材库/」。
"""

import argparse
import json
import os
import sys
from pathlib import Path

from _shared import core          # noqa: E402
from _shared import naming as nm  # noqa: E402

try:  # Windows 控制台中文输出
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


# --------------------------------------------------------------------------
# 公共（CLI 辅助）
# --------------------------------------------------------------------------
def lib_root(args):
    root = args.root or os.environ.get("BIDCRAFT_LIB_ROOT") or os.path.join(os.getcwd(), "素材库")
    return Path(root)


def get_lib(args):
    return core.Library(lib_root(args))


def get_ent(args, required=True):
    lib = get_lib(args)
    if not required and not lib.enterprises():
        return None
    return lib.resolve(getattr(args, "enterprise", None))


def dump(obj, args, human=""):
    if getattr(args, "json", False):
        print(json.dumps(obj, ensure_ascii=False, indent=2))
    else:
        print(human if human else json.dumps(obj, ensure_ascii=False, indent=2))


def table(rows, headers):
    """极简等宽表（中文按 2 列宽估算）。"""
    def w(s):
        s = str(s)
        return sum(2 if ord(c) > 127 else 1 for c in s)

    widths = [w(h) for h in headers]
    for r in rows:
        for i, c in enumerate(r):
            widths[i] = max(widths[i], w(c))
    line = "  ".join(h + " " * (widths[i] - w(h)) for i, h in enumerate(headers))
    out = [line, "-" * w(line)]
    for r in rows:
        out.append("  ".join(str(c) + " " * (widths[i] - w(str(c))) for i, c in enumerate(r)))
    return "\n".join(out)


# --------------------------------------------------------------------------
# 命令实现
# --------------------------------------------------------------------------
def cmd_init_enterprise(args):
    lib = get_lib(args)
    ent, existed = lib.init_enterprise(args.name, credit_code=args.credit_code, owner=args.owner)
    core.cleanup_trash(ent, days=args.trash_days)  # 顺带做一次回收站清理
    obj = {"ok": True, "enterprise": ent.name, "path": str(core.lib_root(ent)), "already_existed": existed}
    dump(obj, args, human=(
        ("企业已存在，已复用：%s" if existed else "已创建企业：%s") % ent.name
        + "\n公司回收站：%s（删除的项目/素材先进此处，30 天后清理）" % (ent / "回收站")
        + "\n素材库路径：%s" % core.lib_root(ent)
        + "\n已初始化子目录：%s" % "、".join(core.ENTERPRISE_SUBDIRS)
        + "\n台账：%s（JSON 权威，CSV 按需导出）" % core.LEDGER_JSON
    ))


def cmd_list_enterprises(args):
    lib = get_lib(args)
    ents = lib.enterprises()
    if args.json:
        print(json.dumps({"root": str(lib.root), "enterprises": ents}, ensure_ascii=False, indent=2))
    else:
        print("软件根目录：%s" % lib.root)
        print("企业（%d）：%s" % (len(ents), "、".join(ents) if ents else "（无，请先 init-enterprise）"))


def cmd_overview(args):
    ent = get_ent(args, required=False)
    if ent is None:
        print("尚未创建任何企业，请先执行 init-enterprise --name \"企业全名\"")
        return
    ov = core.enterprise_overview(ent)
    human = (
        "企业：%s\n素材库路径：%s\n台账条目：%d\n"
        "分类分布：%s\n磁盘文件数：%s\n收件箱：%s\n回收站：%d 个文件"
        % (
            ov["enterprise"], ov["path"], ov["ledger_total"],
            "、".join("%s=%d" % kv for kv in ov["by_category"].items()) or "（空）",
            "、".join("%s=%d" % kv for kv in ov["disk_files"].items()),
            ("打开中 batch=%s，待归档 %d 个" % (ov["inbox"]["batch_id"], ov["inbox"]["items"]))
            if ov["inbox"]["open"] else "未打开",
            ov["trash"],
        )
    )
    dump(ov, args, human=human)


def cmd_open_inbox(args):
    ent = get_ent(args)
    core.cleanup_trash(ent, days=args.trash_days)
    b = core.Inbox(ent).open(note=args.note, force=args.force)
    n = len(b.get("items", []))
    if b.get("resumed"):
        head = "收件箱批次已恢复（batch=%s，已有 %d 个文件）" % (b["batch_id"], n)
    else:
        head = "收件箱已打开（batch=%s）" % b["batch_id"]
    dump(b, args, human=(
        head
        + "\n上传方式（任选其一）："
        + "\n  · 逐张登记：python bidcraft.py upload --file \"<文件路径>\""
        + "\n  · 或直接把文件拷进收件箱文件夹，然后执行：python bidcraft.py sync-inbox"
        + "\n上传完毕后：python bidcraft.py close-inbox"
    ))


def cmd_sync_inbox(args):
    ent = get_ent(args)
    inbox = core.Inbox(ent)
    added = inbox.sync()
    if not added:
        print("收件箱内没有新增未登记文件。")
        return
    dup = {}
    for it in inbox.items():
        dup.setdefault(it.get("sha256"), []).append(it.get("file"))
    dup = {k: v for k, v in dup.items() if len(v) > 1}
    human = "已补登记 %d 个文件（按写入时间排序）：\n" % len(added)
    human += "\n".join("  %d. %s  (%s)" % (a["seq"], a["file"], a["written_at"]) for a in added)
    if inbox.has_time_collision():
        human += "\n⚠️ 存在同秒写入（顺序无法自动判定），归档前请人工确认先后。"
    if dup:
        human += "\n⚠️ 检测到内容重复（sha256 相同）：" + "；".join(
            "同一文件：%s" % "、".join(v) for v in dup.values())
    dump({"added": added, "duplicates": dup}, args, human=human)


def cmd_upload(args):
    ent = get_ent(args)
    item = core.Inbox(ent).add(args.file, original_name=args.name)
    dump(item, args, human=(
        "已登记第 %d 个文件：%s → 收件箱/%s（%d 字节）"
        % (item["seq"], item["original_name"], item["file"], item["size"])
    ))


def cmd_close_inbox(args):
    ent = get_ent(args)
    inbox = core.Inbox(ent)
    b = inbox.close()
    n = len(b.get("items", []))
    warn = ""
    if inbox.has_time_collision():
        warn = "\n⚠️ 检测到写入时间撞车（同秒多文件），P0/P1 顺序请人工确认。"
    dump({"closed_at": b["closed_at"], "items": n}, args, human=(
        "收件箱已关闭（batch=%s，共 %d 个文件待归档）。%s\n下一步：python bidcraft.py propose --out 归档提案.json"
        % (b["batch_id"], n, warn)
    ))


def cmd_inbox_status(args):
    ent = get_ent(args)
    inbox = core.Inbox(ent)
    b = inbox.load()
    if not b:
        print("收件箱为空（未打开或无待归档内容）。")
        return
    rows = [[str(i.get("seq")), i.get("file"), i.get("written_at"), str(i.get("size"))]
            for i in inbox.items(order="seq")]
    human = table(rows, ["序号", "文件", "写入时间", "大小"]) if rows else "（无文件）"
    human = "batch=%s 打开=%s\n%s" % (b.get("batch_id"), "否" if b.get("closed_at") else "是", human)
    dump(b, args, human=human)


def cmd_propose(args):
    ent = get_ent(args)
    prop = core.propose(ent, require_closed=not args.allow_open)
    default_out = core.lib_root(ent) / "收件箱" / "_归档提案.json"
    out = Path(args.out) if args.out else default_out
    core.write_json(out, prop)
    if args.json:
        print(json.dumps(prop, ensure_ascii=False, indent=2))
    else:
        rows = []
        for it in prop["items"]:
            rows.append([
                str(it["seq"]), it["original_name"],
                ("%s/%s" % (it["category"], it["subtype"])) if it["category"] else "？（待指定）",
                "、".join(it["keywords"]), "、".join(it["dates"]),
                it["ownership"], "; ".join(it["needs_input"]) or "就绪",
            ])
        human = "企业：%s（归属：%s）\n" % (prop["enterprise"], prop["owner"])
        if prop["time_collision"]:
            human += "⚠️ 写入时间存在撞车，多页顺序需人工确认。\n"
        human += table(rows, ["序号", "原文件名", "建议归类", "关键字", "日期", "归属", "待补充"])
        human += "\n\n归档提案已写入：%s\n请人工核对/修改后执行：python bidcraft.py apply --proposal \"%s\"\n" % (out, out)
        print(human)


def cmd_apply(args):
    ent = get_ent(args)
    prop = core.read_json(args.proposal, None)
    if not prop:
        raise SystemExit("提案文件不存在或不是合法 JSON：%s" % args.proposal)
    res = core.apply(ent, prop, require_closed=not args.allow_open)
    s = res["summary"]
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        human = "归档完成：成功 %d、跳过 %d、删除入回收站 %d、失败 %d（台账共 %d 条）\n" % (
            s["archived"], s["skipped"], s["trashed"], s["failed"], s["ledger_total"])
        if res["archived"]:
            human += "\n已归档：\n" + "\n".join("  · %s" % a["rel_path"] for a in res["archived"])
        if res["failed"]:
            human += "\n\n失败（需处理）：\n" + "\n".join(
                "  · seq=%s %s" % (f.get("seq"), f.get("error")) for f in res["failed"])
        print(human)
    if res["failed"]:
        sys.exit(2)


def cmd_validate(args):
    ok, issues = nm.validate(args.category, args.subtype, args.name)
    hint = nm.rule_hint(args.category, args.subtype)
    obj = {"ok": ok, "issues": issues, "expected": hint, "name": args.name,
           "category": args.category, "subtype": args.subtype or nm.DEFAULT_SUBTYPE.get(args.category)}
    dump(obj, args, human=(
        ("✅ 合规：%s" if ok else "❌ 不合规：%s") % args.name
        + "\n期望格式：%s" % hint
        + ("\n问题：\n" + "\n".join("  - %s" % m for m in issues) if issues else "")
    ))


def cmd_inspect(args):
    ent = get_ent(args)
    res = core.inspect(ent)
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        if not res["issues"]:
            print("✅ 巡检通过：企业 %s 未发现非常规上传 / 命名问题。" % res["enterprise"])
            return
        rows = [[i["type"], i["rel_path"], i["detail"]] for i in res["issues"]]
        print("企业：%s　共 %d 项待处理\n" % (res["enterprise"], res["count"]))
        print(table(rows, ["类型", "文件", "说明"]))
        print("\n请逐条决定：【删除重传】入回收站，或【保留归档】按规范改名并补登台账。")


def cmd_query(args):
    ent = get_ent(args)
    if getattr(args, "fuzzy", False):
        # ⑤ 混合检索：n-gram 相似召回 + 字段加权重排（精确命中优先）
        hits = core.query_hybrid(ent, category=args.category, subtype=args.subtype,
                                 keyword=args.keyword,
                                 expires_before=args.expires_before,
                                 expires_after=args.expires_after,
                                 owner=args.owner, top_k=args.top_k)
        rows = [h["row"] for h in hits]
        if args.json:
            print(json.dumps(hits, ensure_ascii=False, indent=2))
        else:
            if not rows:
                print("未命中任何素材。")
                return
            t = [[r.get("id"), r.get("category"), r.get("subtype"), r.get("rel_path"),
                  r.get("dates"), "%.2f" % h["score"]] for r, h in zip(rows, hits)]
            print(table(t, ["ID", "大类", "子类", "路径", "日期", "匹配度"]) +
                  "\n\n共 %d 条（混合检索：精确命中优先，字符相似度兜底）" % len(rows))
        return
    rows = core.query(ent, category=args.category, subtype=args.subtype, keyword=args.keyword,
                      expires_before=args.expires_before, expires_after=args.expires_after,
                      owner=args.owner)
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        if not rows:
            print("未命中任何素材。")
            return
        t = [[r.get("id"), r.get("category"), r.get("subtype"), r.get("rel_path"),
              r.get("dates"), r.get("owner")] for r in rows]
        print(table(t, ["ID", "大类", "子类", "路径", "日期", "归属"]) + "\n\n共 %d 条" % len(rows))


def cmd_trash(args):
    ent = get_ent(args)
    dest = core.move_to_trash(ent, core.lib_rel(args.path), reason=args.reason or "用户删除")
    dump({"moved_to": str(dest)}, args, human="已移入公司回收站：%s（30 天后自动清理）" % dest)


def cmd_rm_project(args):
    ent = get_ent(args)
    proj = args.project.strip("/\\")
    if not proj:
        raise SystemExit("项目名不能为空")
    src = Path(ent) / "项目级" / proj
    if not src.exists():
        projs = "、".join(d.name for d in (Path(ent) / "项目级").iterdir() if d.is_dir()) or "无"
        raise core.LibraryError("项目不存在：%s（项目级下现有：%s）" % (proj, projs))
    dest = core.move_to_trash(ent, "项目级/%s" % proj, reason=args.reason or "删除项目")
    dump({"moved_to": str(dest), "project": proj}, args, human=(
        "项目已移入公司回收站：%s（30 天后自动清理）\n恢复方式：从回收站手动移回 项目级/ 下" % dest))


def cmd_cleanup_trash(args):
    ent = get_ent(args)
    removed = core.cleanup_trash(ent, days=args.days)
    dump({"removed": removed}, args, human=(
        "回收站清理完成，删除 %d 个超期文件%s" % (len(removed), ("：" + "、".join(removed)) if removed else "")
    ))


def cmd_reconcile(args):
    """数据一致性巡检：台账 ↔ 磁盘 ↔ 回收站三方对账。

    --enterprise 指定单企业；未指定时巡检全部企业（只读，不改数据）。
    """
    lib = get_lib(args)
    ents = lib.enterprises()
    if not ents:
        print("尚未创建任何企业，请先执行 init-enterprise --name \"企业全名\"")
        return
    target = getattr(args, "enterprise", None)
    if target:
        ent = lib.resolve(target)
        ents = [ent.name]
    else:
        ents = [e for e in ents]

    results = []
    total_issues = 0
    for name in ents:
        ent = lib.root / name
        try:
            res = core.consistency_check(ent)
        except Exception as e:  # 单企业失败不阻断整体巡检
            res = {"enterprise": name, "scanned_at": core.now_iso(),
                   "summary": {}, "issues": [{"type": "巡检失败", "detail": str(e)}],
                   "ok": False}
        results.append(res)
        total_issues += len(res.get("issues", []))

    payload = {
        "root": str(lib.root),
        "scanned_at": core.now_iso(),
        "enterprises": results,
        "total_issues": total_issues,
        "ok": all(r.get("ok") for r in results),
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    # 人类可读
    for r in results:
        s = r.get("summary", {})
        head = "企业：%s　台账 %d 条 / 磁盘 %d 个 / 回收站清单 %d 条（磁盘 %d 个）" % (
            r["enterprise"], s.get("ledger_rows", 0), s.get("disk_files", 0),
            s.get("trash_manifest", 0), s.get("trash_disk", 0))
        print(head)
        if not r.get("issues"):
            print("  ✅ 数据一致，未发现问题。")
            continue
        rows = [[i.get("type", ""), i.get("rel_path") or i.get("file", ""), i.get("detail", "")]
                for i in r["issues"]]
        print(table(rows, ["类型", "对象", "说明"]))
    print("\n合计：%d 家企业，%d 项待处理%s" % (
        len(results), total_issues,
        "（全部一致）" if not total_issues else "，请逐项人工处理"))


def cmd_rules(args):
    cats = [args.category] if args.category else nm.list_categories()
    obj = {}
    for c in cats:
        obj[c] = {"date_label": nm.CATEGORY_META[c]["date_label"], "subtypes": {}, "default_subtype": nm.DEFAULT_SUBTYPE[c]}
        for s in nm.list_subtypes(c):
            obj[c]["subtypes"][s] = nm.rule_hint(c, s)
    if args.json:
        print(json.dumps(obj, ensure_ascii=False, indent=2))
    else:
        for c, info in obj.items():
            print("【%s】（日期字段：%s，默认子类：%s）" % (c, info["date_label"], info["default_subtype"]))
            for s, hint in info["subtypes"].items():
                print("   - %s：%s" % (s, hint))
        print("\n通用：无到期日记「长期」；日期不可考记「日期不详」；多页末尾加 _P0/_P1；"
              "关键字中的 _ 与 / \\ : * ? \" < > | 一律替换为 -。")


def cmd_build_name(args):
    name = nm.build_name(args.category, args.subtype, keywords=args.keyword,
                         dates=args.date, page=args.page, ext=args.ext)
    ok, issues = nm.validate(args.category, args.subtype, name)
    dump({"name": name, "ok": ok, "issues": issues}, args, human=name)


def cmd_build_project_folder(args):
    name = nm.build_project_folder(args.project, args.date, args.director)
    ok, issues = nm.validate_project_folder(name)
    dump({"folder": name, "ok": ok, "issues": issues}, args, human=name)


def cmd_classify(args):
    cat, sub, hit = nm.classify(args.name)
    sug = core._suggest_fields(args.name, cat, sub)
    obj = {"category": cat, "subtype": sub, "hit": hit, "suggest": sug}
    dump(obj, args, human=(
        "文件名：%s\n建议大类：%s\n建议子类：%s\n命中关键字：%s\n建议关键字：%s\n建议日期：%s\n多页序号：%s"
        % (args.name, cat or "（未识别）", sub or "（未识别）", hit or "-",
           "、".join(sug["keywords"]) or "-", "、".join(sug["dates"]) or "-", sug["page"])
    ))


def cmd_ownership_check(args):
    ent = get_ent(args, required=False)
    if ent is None:
        raise SystemExit("尚未创建企业，无法做归属校验")
    res = core.ownership_check(ent, args.name, extra_text=args.text)
    labels = {"match": "与本企业相符", "conflict": "疑似属于其他企业", "unknown": "无法判定"}
    dump(res, args, human=(
        "当前企业：%s\n素材：%s\n判定：%s%s"
        % (ent.name, args.name, labels.get(res.get("status"), res.get("status")),
           ("（命中：%s，疑似属于 %s）" % (res.get("token"), res.get("other"))) if res.get("status") == "conflict"
           else ("（命中：%s）" % res.get("token") if res.get("token") else ""))
    ))


# --------------------------------------------------------------------------
