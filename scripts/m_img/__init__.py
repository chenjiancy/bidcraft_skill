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
def _arch_ext_for(src, ext):
    """按真实图片格式决定归档扩展名：PIL 识别（png→png，jpeg/jpg→jpg）；
    PIL 不可用或识别失败 → 回退源扩展名映射（.jpeg→jpg）。"""
    try:
        from PIL import Image
        with Image.open(src) as im:
            fmt = (im.format or "").lower()
        if fmt == "png":
            return "png"
        if fmt in ("jpeg", "jpg"):
            return "jpg"
    except Exception:
        pass
    return IMG_EXTS.get(ext, "png")


def _clean_copy(src, dst, arch_ext):
    """PIL 重编码清洗落盘：丢弃平台产物内嵌的 AIGC/EXIF 等元数据段，
    产出 python-docx / Word 可直接识别的标准 PNG/JPEG。失败 → 拒绝不落盘。"""
    try:
        from PIL import Image
        with Image.open(src) as im:
            im.load()
            if arch_ext == "png":
                im.save(str(dst), format="PNG")
            else:
                im.save(str(dst), format="JPEG", quality=95)
    except Exception as e:
        if dst.exists():
            dst.unlink()
        raise core.LibraryError("图片清洗落盘失败（平台产物可能损坏/格式异常），已拒绝：%s" % e)


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

    # 真实格式判定（防"扩展名 .png 实为 JPEG"的错配落盘）：PIL 识别优先，
    # 不可用/不可读时回退源扩展名映射。归档扩展名与真实格式一致。
    arch_ext = _arch_ext_for(src, ext)
    d = img_dir(ent, project)
    d.mkdir(parents=True, exist_ok=True)
    # 防重复：同 id 已有不同扩展名的落盘 → 拒绝
    for existing in d.glob(args.id + ".*"):
        raise core.LibraryError("配图项 %s 已有落盘文件：%s（先清理再保存）" % (args.id, existing.name))

    dst = d / ("%s.%s" % (args.id, arch_ext))
    # 清洗落盘：平台产物常内嵌 AIGC/EXIF 元数据段（如 APP11 'AIGC{...}'），
    # python-docx 无法解析会 UnrecognizedImageError → 统一 PIL 重编码为干净标准文件。
    _clean_copy(src, dst, arch_ext)
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
# img-embed：技术标 AI 配图嵌入（非商务标引擎消费 img-save 产物，写操作）
# --------------------------------------------------------------------------
def _tech_match(section, title):
    """section ↔ 章节 title 双向包含匹配（任一方向命中即中）。"""
    s = (section or "").strip()
    t = (title or "").strip()
    return bool(s and t and (s in t or t in s))


def cmd_img_embed(args):
    """AI 配图 → 技术标正文嵌入（写操作，执行桥须 confirm：true）。

    读 配图/配图清单_<项目>.json 的 saved 项 → 按 section 匹配技术标章节树
    （章节 title 双向包含）→ 在章节正文标题后插入 `![图题](图片绝对路径)`
    （m6 export 渲染语法；Path.is_file 校验）→ 幂等（已含该图片引用则跳过）。
    未匹配章节 / 未 saved 项 → 披露不嵌入。暗标提示：export 暗标自动切图。
    """
    ent = get_ent(args)
    project = args.project
    plan = _load_plan(ent, project, must=True)
    saved = [it for it in plan.get("items", [])
             if it.get("status") == "saved" and it.get("file")]
    from m6_tech import store as tech_store          # noqa: E402
    tech = tech_store.tech_path(ent, project)
    tree = tech_store.read_tree(tech)
    chapters = tech_store.list_chapters(tree)
    proj_dir = Path(ent) / PROJECT_SUBDIR / project
    embedded, skipped, unmatched = [], [], []
    for it in saved:
        img_abs = (proj_dir / str(it.get("file"))).resolve()
        if not img_abs.is_file():
            unmatched.append({"id": it.get("id"), "section": it.get("section"),
                              "reason": "图片文件不存在（配图清单 saved 但本体缺失）：%s" % it.get("file")})
            continue
        ch = next((c for c in chapters if _tech_match(it.get("section"), c.get("title"))), None)
        if ch is None:
            unmatched.append({"id": it.get("id"), "section": it.get("section"),
                              "reason": "技术标章节树无匹配章节（section 与章节 title 双向包含未命中）"})
            continue
        body_path = tech_store.chapter_body_path(tech, ch)
        if not body_path.is_file():
            unmatched.append({"id": it.get("id"), "section": it.get("section"),
                              "reason": "章节正文不存在：%s（先 tech-parse 落盘）" % body_path})
            continue
        text = body_path.read_text(encoding="utf-8")
        if str(img_abs) in text:
            skipped.append({"id": it.get("id"), "section": it.get("section"),
                            "chapter": ch.get("id"), "reason": "已嵌入（幂等跳过）"})
            continue
        cap = it.get("subject") or it.get("section") or it.get("id")
        ref = "![%s](%s)" % (cap, img_abs)
        lines = text.splitlines()
        # 在首个标题行后插入图片引用；无标题则文件开头
        idx = next((i for i, ln in enumerate(lines) if ln.strip().startswith("#")), None)
        if idx is None:
            new_text = ref + "\n\n" + text
        else:
            lines.insert(idx + 1, "")
            lines.insert(idx + 2, ref)
            new_text = "\n".join(lines)
        body_path.write_text(new_text, encoding="utf-8")
        # 回读校验
        back = body_path.read_text(encoding="utf-8")
        if str(img_abs) not in back:
            raise core.LibraryError("img-embed 回读校验失败（引用未写入）：%s" % body_path)
        embedded.append({"id": it.get("id"), "section": it.get("section"),
                         "chapter": ch.get("id"), "file": str(img_abs)})
    obj = {"project": project, "saved": len(saved),
           "embedded": len(embedded), "skipped": len(skipped), "unmatched": len(unmatched),
           "details": {"embedded": embedded, "skipped": skipped, "unmatched": unmatched}}
    if getattr(args, "json", False):
        print(json.dumps(obj, ensure_ascii=False, indent=2))
        return 0
    print("img-embed：技术标 AI 配图嵌入（写操作）\n")
    print("配图清单 saved %d 项｜嵌入 %d｜幂等跳过 %d｜未匹配/未嵌 %d"
          % (len(saved), len(embedded), len(skipped), len(unmatched)))
    for r in embedded:
        print("  [嵌] %s → 章节 %s（%s）" % (r["id"], r["chapter"], r["section"]))
    for r in skipped:
        print("  [跳] %s → %s（%s）" % (r["id"], r["chapter"], r["reason"]))
    for r in unmatched:
        print("  [未] %s → %s" % (r["id"], r["reason"]))
    return 0


# --------------------------------------------------------------------------
# img-audit：技术标 AI 配图暗标合规审计（只读）
# --------------------------------------------------------------------------
# 暗标红线违规词表（清单 subject/style 文本命中即不合规；可增行）
AUDIT_WORDS = ["公司", "有限", "集团", "股份", "LOGO", "logo", "水印", "AI 生成", "AI生成",
               "WORKBUD", "WorkBuddy", "企业名称", "人名", "签名"]

# OCR 探测（图内文字核验：有 OCR 引擎则真扫；无则披露需人工核验）
def _ocr_engine():
    """返回 (python_exe, engine_name) 或 None。

    探测链：① BIDCRAFT_OCR_PY 环境变量（OCR venv 的 python.exe 绝对路径）
            ② 仓库根 .ocr_venv（E:\\bidcraft_skill\\.ocr_venv\\Scripts\\python.exe 同型布局）
            ③ 当前解释器自身（主环境已装 paddleocr 时）。
    引擎识别按 paddleocr > easyocr > pytesseract > tesseract 顺序。"""
    candidates = []
    env_py = os.environ.get("BIDCRAFT_OCR_PY")
    if env_py:
        candidates.append((env_py, "paddleocr"))
    root = Path(__file__).resolve().parents[2]
    venv_py = root / ".ocr_venv" / "Scripts" / "python.exe"
    if venv_py.is_file():
        candidates.append((str(venv_py), "paddleocr"))
    candidates.append((sys.executable, "current"))
    for py, tag in candidates:
        if not py or not os.path.isfile(py):
            continue
        try:
            if tag == "paddleocr":
                return (py, "paddleocr")
            for mod in ("paddleocr", "easyocr", "pytesseract"):
                __import__(mod)
                return (py, mod)
            import shutil
            if shutil.which("tesseract"):
                return (py, "tesseract")
        except Exception:
            continue
    return None


_OCR_TIMEOUT = 180


def _ocr_texts(abs_path):
    """调 OCR 引擎对单张图做真扫，返回 [text,...]；引擎缺失/失败返回 None（由调用方披露）。"""
    engine = _ocr_engine()
    if engine is None:
        return None
    py, name = engine
    if name == "paddleocr":
        worker = Path(__file__).resolve().parent / "_ocr_worker.py"
        try:
            r = subprocess.run([py, "-X", "utf8", str(worker), str(abs_path)],
                               capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=_OCR_TIMEOUT)
            doc = json.loads((r.stdout or "").strip().splitlines()[-1])
        except Exception:
            return None
        if doc.get("error"):
            return None
        return [str(t) for t in doc.get("texts", [])]
    # easyocr/pytesseract/tesseract：走标准库探测路径（当前实现仅披露引擎可用，不做真扫）
    return None


def _has_aigc_marker(path):
    """AIGC 元数据残留检测：JPEG APP11 'AIGC{' / PNG 全文件 'AIGC{'（img-save 应已剥离）。"""
    try:
        data = path.read_bytes()
    except OSError:
        return False
    return b"AIGC{" in data


def cmd_img_audit(args):
    """AI 配图暗标合规审计（只读）：对配图清单 saved 项逐图检查——
    a) 图片文件存在（缺失=不合规）；b) AIGC 元数据残留（img-save 清洗失败=不合规）；
    c) 清单 subject/style 含暗标红线词（公司/LOGO/水印/AI 标识等=不合规）；
    d) 来源 source 标注（空=披露）；e) 图内文字：OCR 引擎（默认 paddleocr venv）真扫，
    检出红线词=不合规；引擎不可用则明确披露「图内文字需人工核验」不假装检查。
    输出 pass/fail 三态 + 明细（--json 机读）。"""
    ent = get_ent(args)
    project = args.project
    plan = _load_plan(ent, project, must=True)
    saved = [it for it in plan.get("items", []) if it.get("status") == "saved"]
    proj_dir = Path(ent) / PROJECT_SUBDIR / project
    engine = _ocr_engine()
    ocr_ok = engine is not None
    results = []
    for it in saved:
        p = it.get("file") or ""
        abs_p = (proj_dir / p).resolve() if p else None
        issues = []
        notes = []
        if abs_p is None or not abs_p.is_file():
            issues.append("图片文件缺失：%s" % (p or "(file 为空)"))
        else:
            if _has_aigc_marker(abs_p):
                issues.append("AIGC 元数据段残留（img-save 清洗失败，须重新 img-save）")
            if not it.get("source"):
                issues.append("来源 source 未标注（暗标可追溯性弱，建议补齐）")
            subj = "%s %s" % (it.get("subject") or "", it.get("style") or "")
            hits = [w for w in AUDIT_WORDS if w in subj]
            if hits:
                issues.append("清单 subject/style 含暗标红线词：%s" % "/".join(hits))
            # e) 图内文字真扫（OCR 引擎可用时）；失败/缺失 → 人工核验披露
            if ocr_ok:
                ocr_texts = _ocr_texts(abs_p)
                if ocr_texts is None:
                    notes.append("图内文字 OCR 引擎异常（本次未扫，须人工核验）")
                else:
                    joined = " ".join(ocr_texts)
                    hits2 = [w for w in AUDIT_WORDS if w in joined]
                    if hits2:
                        issues.append("图内文字含暗标红线词（OCR 检出）：%s" % "/".join(hits2))
                    if ocr_texts:
                        notes.append("OCR 文本：%s" % "｜".join(ocr_texts[:12]))
            else:
                notes.append("图内文字需人工核验（本机无 OCR 引擎）")
        status = "fail" if issues else "pass"
        results.append({
            "id": it.get("id"), "section": it.get("section"), "status": status,
            "file": p, "issues": issues, "note": notes,
            "source": it.get("source") or "",
        })
    counts = {"pass": 0, "fail": 0}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    obj = {
        "project": project, "saved": len(saved),
        "pass": counts["pass"], "fail": counts["fail"],
        "ocr": ("available（%s 真扫）" % engine[1]) if ocr_ok else "unavailable（图内文字需人工核验）",
        "items": results,
    }
    if getattr(args, "json", False):
        print(json.dumps(obj, ensure_ascii=False, indent=2))
        return 0
    print("img-audit：AI 配图暗标合规审计（只读）\n")
    print("配图清单 saved %d 项｜通过 %d｜不合规 %d" % (len(saved), counts["pass"], counts["fail"]))
    print("OCR：%s" % obj["ocr"])
    for r in results:
        mark = "PASS" if r["status"] == "pass" else "FAIL"
        print("  [%s] %s %s｜%s" % (mark, r["id"], r["section"], r["file"]))
        for i in r["issues"]:
            print("        - %s" % i)
        for n in r["note"]:
            print("        ~ %s" % n)
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

    sp = sub.add_parser("img-embed", help="AI 配图：技术标正文嵌入（非商务标引擎消费 img-save 产物；写操作，执行桥须 confirm）——saved 项按 section 匹配章节树 → 章节标题后插入 ![图题](绝对路径)，幂等")
    sp.add_argument("--project", required=True)
    sp.set_defaults(func=cmd_img_embed)

    sp = sub.add_parser("img-audit", help="AI 配图：技术标暗标合规审计（只读）——saved 项逐图检查 文件存在/AIGC 残留/subject-style 红线词/来源标注；图内文字无 OCR 环境披露人工核验")
    sp.add_argument("--project", required=True)
    sp.set_defaults(func=cmd_img_audit)
