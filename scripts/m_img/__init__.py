# -*- coding: utf-8 -*-
"""
bidcraft · m_img AI 配图管道 —— CLI（命令实现 + 子命令注册）

定位：跨 M4/M5 的「素材生产管道」——从投标要点（M4 产物）确定配图需求，
双通道（豆包 agent / CodeBuddy ImageGen）生图 → img-save 落盘回填 → 供 fill-tpl（M5）嵌入。

命令：
  img-plan   从投标要点生成/合并「配图清单」（确定性骨架，agent 可改写）
  img-save   收图落盘（校验图片 → 复制到 配图/<id>.<ext> → 回填清单状态）
  img-status 查看清单状态（pending/saved 计数 + 明细）

数据落位（项目级）：<软件根>/<企业>/项目级/<项目名>/配图/
  配图清单_<项目>.json     # 机读清单（生图执行器与嵌入引擎的唯一事实源）
  <img_id>.<png|jpg>       # 图片本体

交接协议（图片必须落盘才算完成）：
  豆包对话框：agent 调平台生图 → 用户/agent 确认后调 `img-save --id <img_id> --file <图>` 落盘；
  UI/CodeBuddy：执行桥 img-save（confirm:true）或 CLI 直调，图片来自 CodeBuddy ImageGen 产物路径。
"""

import argparse
import datetime as _dt
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from _shared import core            # noqa: E402
from m4_tender import rules as m4_rules   # noqa: E402
from m4_tender import tender as m4_tender  # noqa: E402

try:  # Windows 控制台中文输出
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

PROJECT_SUBDIR = "项目级"
IMG_SUBDIR = "配图"
IMG_TEMP_SUBDIR = "临时"   # CodeBuddy 等外部通道的暂存区（img-gen-agent 落点；img-save --temp 只认这里）
PLAN_BASE = "配图清单_%s"

# CodeBuddy CLI（headless 生图；缺省路径可被环境变量 BIDCRAFT_CODEBUDDY_BIN 覆盖）
CODEBUDDY_BIN = "C:/Users/hxjlcj/AppData/Local/codebuddy/bin/codebuddy.exe"

# 图片收口白名单（扩展名 → 归档扩展名）
IMG_EXTS = {".png": "png", ".jpg": "jpg", ".jpeg": "jpg"}
IMG_MAX_BYTES = 10 * 1024 * 1024  # 10MB
# --temp 文件名白名单（仅文件名，禁路径分隔符/穿越）
TEMP_NAME_RE = r"^[\w.\-]+$"

# 生成规则表：投标要点 module.id（业务语义）→ 配图需求（确定性骨架；subject/style 可被 agent 改写）
# 注：module.type 是结构类型（fields/items/mixed），业务类型在 id（staff/project_overview/...）
PLAN_RULES = [
    {"id": "staff", "kind": "框图", "ratio": "16:9",
     "subject": "项目监理机构人员配置框图（总监理工程师-专业监理工程师-监理员层级与分工）",
     "style": "商务正式、扁平化、蓝色系"},
    {"id": "project_overview", "kind": "示意图", "ratio": "16:9",
     "subject": "项目概况与监理工作内容示意（覆盖本项目主要监理对象）",
     "style": "商务正式、扁平化、蓝色系"},
    {"id": "qualification", "kind": "框图", "ratio": "16:9",
     "subject": "企业组织机构与资质框架图",
     "style": "商务正式、扁平化、蓝色系"},
    {"id": "scoring", "kind": "对照图", "ratio": "16:9",
     "subject": "评分办法与评分点对照示意（可选配图）",
     "style": "商务正式、扁平化、蓝色系"},
]


# --------------------------------------------------------------------------
# 公共（CLI 辅助，与 m4_tender 同构）
# --------------------------------------------------------------------------
def lib_root(args):
    root = args.root or os.environ.get("BIDCRAFT_LIB_ROOT") or os.path.join(os.getcwd(), "素材库")
    return Path(root)


def get_ent(args):
    lib = core.Library(lib_root(args))
    return lib.resolve(getattr(args, "enterprise", None))


def img_dir(ent, project):
    """<企业根>/项目级/<项目>/配图（不创建）。"""
    return Path(ent) / PROJECT_SUBDIR / project / IMG_SUBDIR


def plan_path(ent, project):
    return img_dir(ent, project) / (PLAN_BASE % project + ".json")


def _load_plan(ent, project, must=True):
    p = plan_path(ent, project)
    if not p.exists():
        if must:
            raise core.LibraryError("配图清单不存在：%s（请先运行 img-plan）" % p)
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        raise core.LibraryError("配图清单解析失败：%s（%s）" % (p, e))


def _write_plan(ent, project, doc):
    d = img_dir(ent, project)
    d.mkdir(parents=True, exist_ok=True)
    (d / (PLAN_BASE % project + ".json")).write_text(
        json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")


def _now():
    return _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# --------------------------------------------------------------------------
# img-plan：投标要点 → 配图清单（确定性骨架，幂等合并）
# --------------------------------------------------------------------------
def cmd_img_plan(args):
    ent = get_ent(args)
    project = args.project
    ok, issue = m4_rules.validate_project_name(project)
    if not ok:
        raise core.LibraryError("项目名不合法：%s" % issue)
    tdir = m4_tender.project_tender_dir(ent, project)
    points_json = tdir / (m4_rules.points_base(project) + ".json")
    if not points_json.exists():
        raise core.LibraryError("投标要点不存在：%s（请先完成 M4 双通道解析）" % points_json)
    try:
        points = json.loads(points_json.read_text(encoding="utf-8"))
    except Exception as e:
        raise core.LibraryError("投标要点解析失败：%s（%s）" % (points_json, e))

    old = _load_plan(ent, project, must=False) or {"project": project, "items": []}
    old_items = {it.get("id"): it for it in old.get("items", [])}
    # 已存在同 subject 的项（无论状态）→ 幂等跳过
    existing_subjects = {it.get("subject") for it in old.get("items", [])}
    next_no = len(old_items) + 1

    added = []
    for mod in points.get("modules", []):
        rule = next((r for r in PLAN_RULES if r["id"] == mod.get("id")), None)
        if rule is None:
            continue
        subject = rule["subject"]
        if subject in existing_subjects:
            continue
        iid = "img_%03d" % next_no
        old_items[iid] = {
            "id": iid,
            "section": mod.get("title") or mod.get("type", ""),
            "kind": rule["kind"],
            "ratio": rule["ratio"],
            "subject": subject,
            "style": rule["style"],
            "status": "pending",
            "source": "",
            "file": "",
            "created_at": _now(),
        }
        existing_subjects.add(subject)
        next_no += 1
        added.append(iid)

    doc = {"project": project, "generated_at": _now(), "items": sorted(old_items.values(), key=lambda x: x["id"])}
    _write_plan(ent, project, doc)
    counts = {"pending": 0, "saved": 0, "skipped": 0}
    for it in doc["items"]:
        counts[it.get("status", "pending")] = counts.get(it.get("status", "pending"), 0) + 1
    print("配图清单已生成/合并：%s（新增 %d 项，清单共 %d 项：待生成 %d / 已落盘 %d / 跳过 %d）"
          % (plan_path(ent, project), len(added), len(doc["items"]),
             counts.get("pending", 0), counts.get("saved", 0), counts.get("skipped", 0)))
    for it in doc["items"]:
        print("  %s [%s] %s | %s" % (it["id"], it["status"], it["subject"], it["section"]))
    return 0


# --------------------------------------------------------------------------
# img-save：图片收口落盘（写操作；执行桥侧须 confirm:true）
# --------------------------------------------------------------------------
def cmd_img_save(args):
    ent = get_ent(args)
    project = args.project
    doc = _load_plan(ent, project, must=True)
    item = next((it for it in doc["items"] if it.get("id") == args.id), None)
    if item is None:
        raise core.LibraryError("清单中不存在配图项：%s（img-status 查看清单）" % args.id)
    if item.get("status") == "saved":
        raise core.LibraryError("配图项 %s 已落盘：%s（无需重复保存）" % (args.id, item.get("file", "")))

    src = None
    if getattr(args, "temp", None):  # 临时区相对名（执行桥安全通道：禁路径分隔符/穿越）
        name = args.temp.strip()
        if not re.match(TEMP_NAME_RE, name):
            raise core.LibraryError("--temp 仅允许纯文件名（禁路径分隔符）：%s" % args.temp)
        src = img_dir(ent, project) / IMG_TEMP_SUBDIR / name
        if not src.exists():
            raise core.LibraryError("临时区图片不存在：%s（请先把图片放到 配图/临时/）" % src)
    elif args.file:
        src = Path(args.file)
        if not src.exists():
            raise core.LibraryError("图片文件不存在：%s" % src)
    else:
        raise core.LibraryError("须提供 --file（绝对路径）或 --temp（临时区文件名）之一")

    ext = src.suffix.lower()
    if ext not in IMG_EXTS:
        raise core.LibraryError("不支持的图片格式：%s（仅支持 png/jpg/jpeg）" % ext)
    size = src.stat().st_size
    if size <= 0 or size > IMG_MAX_BYTES:
        raise core.LibraryError("图片大小不合法：%d 字节（上限 %d 字节）" % (size, IMG_MAX_BYTES))

    d = img_dir(ent, project)
    d.mkdir(parents=True, exist_ok=True)
    # 防重复：同 id 已有不同扩展名的落盘 → 拒绝
    for existing in d.glob(args.id + ".*"):
        raise core.LibraryError("配图项 %s 已有落盘文件：%s（先清理再保存）" % (args.id, existing.name))

    dst = d / ("%s.%s" % (args.id, IMG_EXTS[ext]))
    shutil.copy2(str(src), str(dst))
    item["status"] = "saved"
    item["file"] = "配图/%s" % dst.name
    item["source"] = args.source or "用户提供"
    item["saved_at"] = _now()
    _write_plan(ent, project, doc)
    print("配图已落盘：%s（来源：%s，%d 字节）" % (dst, item["source"], size))
    print("清单已回填：%s" % plan_path(ent, project))
    return 0


# --------------------------------------------------------------------------
# img-gen-agent：CodeBuddy ImageGen 生图 → 临时区（UI/CodeBuddy 通道）
#   headless 须 -y（bypassPermissions，已实测打通）；图片落 配图/临时/<id>.png，
#   再经 img-save --temp 校验归档（双重闸门：CodeBuddy 权限 + 本地校验/确认）。
# --------------------------------------------------------------------------
def _codebuddy_prompt(item, out_path):
    return (
        "请使用 ImageGen 工具生成一张标书配图：\n"
        "- 主题：%s\n- 类型：%s（%s）\n- 风格：%s，画面内禁止出现真实单位名称/LOGO/人名；"
        "不得包含任何水印、AI 生成标识、平台标识、角标\n"
        "- 用途：嵌入 %s 章节\n"
        "- 输出：保存到 %s\n"
        "完成后只回复：IMAGE_DONE_<文件路径>" % (
            item["subject"], item["kind"], item["ratio"], item["style"],
            item["section"], out_path))


def cmd_img_gen_agent(args):
    ent = get_ent(args)
    project = args.project
    doc = _load_plan(ent, project, must=True)
    item = next((it for it in doc["items"] if it.get("id") == args.id), None)
    if item is None:
        raise core.LibraryError("清单中不存在配图项：%s（img-status 查看清单）" % args.id)
    if item.get("status") == "saved":
        raise core.LibraryError("配图项 %s 已落盘，无需重复生成" % args.id)

    cbd = os.environ.get("BIDCRAFT_CODEBUDDY_BIN") or CODEBUDDY_BIN
    if not os.path.exists(cbd):
        raise core.LibraryError("CodeBuddy CLI 不存在：%s（设 BIDCRAFT_CODEBUDDY_BIN 或先安装登录）" % cbd)

    tmp = img_dir(ent, project) / IMG_TEMP_SUBDIR
    tmp.mkdir(parents=True, exist_ok=True)
    out_path = tmp / ("%s.png" % args.id)  # 固定扩展名落点（prompt 按 .png 约定）
    prompt = _codebuddy_prompt(item, str(out_path))
    cmd = [cbd, "-p", "-y", prompt, "--output-format", "json"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           timeout=args.timeout or 600)
    except subprocess.TimeoutExpired:
        raise core.LibraryError("CodeBuddy 生图超时（%ss）：%s" % (args.timeout or 600, out_path))
    if r.returncode != 0:
        raise core.LibraryError("CodeBuddy 生图失败（exit %d）：%s" % (r.returncode, (r.stderr or r.stdout)[-500:]))
    if not out_path.exists() or out_path.stat().st_size <= 0:
        raise core.LibraryError("CodeBuddy 返回成功但图片未落盘：%s（输出：%s）" % (out_path, r.stdout[-300:]))
    print("CodeBuddy 生图完成：%s（%d 字节；用 img-save --temp %s 校验归档）"
          % (out_path, out_path.stat().st_size, out_path.name))
    return 0


# --------------------------------------------------------------------------
# img-status：清单状态
# --------------------------------------------------------------------------
def cmd_img_status(args):
    ent = get_ent(args)
    project = args.project
    doc = _load_plan(ent, project, must=True)
    items = doc.get("items", [])
    counts = {"pending": 0, "saved": 0, "skipped": 0}
    for it in items:
        counts[it.get("status", "pending")] = counts.get(it.get("status", "pending"), 0) + 1
    if getattr(args, "json", False):
        print(json.dumps({"project": project, "counts": counts, "items": items},
                         ensure_ascii=False, indent=2))
        return 0
    print("配图清单：%s（%d 项：待生成 %d / 已落盘 %d / 跳过 %d）"
          % (project, len(items), counts.get("pending", 0), counts.get("saved", 0), counts.get("skipped", 0)))
    for it in items:
        print("  %s [%s] %s | %s | 来源：%s" % (it["id"], it["status"], it["subject"],
                                              it["section"], it.get("source") or "—"))
    return 0


# --------------------------------------------------------------------------
# 注册
# --------------------------------------------------------------------------
def register_parser(sub):
    sp = sub.add_parser("img-plan", help="AI 配图：从投标要点生成/合并配图清单（确定性骨架，agent 可改写）")
    sp.add_argument("--project", required=True)
    sp.set_defaults(func=cmd_img_plan)

    sp = sub.add_parser("img-save", help="AI 配图：图片收口落盘（校验 → 复制到 配图/<id>.<ext> → 回填清单；写操作，执行桥须 confirm）")
    sp.add_argument("--project", required=True)
    sp.add_argument("--id", required=True, help="配图清单项 id（img_001…）")
    g = sp.add_mutually_exclusive_group(required=True)
    g.add_argument("--file", help="图片文件绝对路径（png/jpg/jpeg，≤10MB；豆包/CLI 场景）")
    g.add_argument("--temp", help="临时区文件名（配图/临时/ 下的纯文件名，禁路径分隔符；执行桥安全通道）")
    sp.add_argument("--source", default="", help="来源标注（CodeBuddy/豆包/即梦API/用户提供）")
    sp.set_defaults(func=cmd_img_save)

    sp = sub.add_parser("img-gen-agent", help="AI 配图：CodeBuddy ImageGen 生图 → 配图/临时/（headless 须 -y，已实测；再经 img-save 归档）")
    sp.add_argument("--project", required=True)
    sp.add_argument("--id", required=True, help="配图清单项 id（img_001…）")
    sp.add_argument("--timeout", type=int, default=600, help="CodeBuddy 调用超时秒数（默认 600）")
    sp.set_defaults(func=cmd_img_gen_agent)

    sp = sub.add_parser("img-status", help="AI 配图：查看配图清单状态（待生成/已落盘 计数 + 明细）")
    sp.add_argument("--project", required=True)
    sp.set_defaults(func=cmd_img_status)
