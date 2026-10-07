# -*- coding: utf-8 -*-
"""⑦ core 拆包 · 写后回读验证（写操作落盘后回读校验，失败即报错，绝不假装成功）。

对应成熟模式：read-back verification / durable writes（写入后回读确认，响应状态不可信）；
验证必须比「未抛异常」更严格——文件存在 + 非空 + 内容哈希一致 + 台账/磁盘一致。

接入点（各写操作尾部调用，全部失败即 raise LibraryError，命令非零退出）：
  - M1 apply          → 每个归档目标 verify_sha256（与收件箱登记一致）+ 台账存在 + 整体 verify_consistency
  - M1 move_to_trash  → 回收站目标存在 + 清单登记 + 源已移除
  - M2 tpl-import     → 模板文件存在 + 台账登记
  - M4 tender-*       → 产物 json 可解析 + 关键字段存在；md/html 非空
  - M5 proj-gen/fill  → 生成 docx 非空 + 生成记录 json 可解析

只读验证、不自动修复：失败即报错由用户处置（fail fast，不留半成品状态）。
"""
import hashlib
from pathlib import Path

from .basic import LibraryError, read_json
from .ops import consistency_check

__all__ = ["verify_file", "verify_sha256", "verify_json", "verify_docx_nonempty",
           "verify_consistency", "readback_files"]


def _label(label, path):
    return "%s（%s）" % (label, path) if label else str(path)


def verify_file(path, min_bytes=1, label=""):
    """目标文件必须存在且非空（min_bytes=0 时仅要求存在）。失败 raise LibraryError。"""
    p = Path(path)
    if not p.exists():
        raise LibraryError("写后回读失败：文件不存在 %s" % _label(label, p))
    if p.is_dir():
        raise LibraryError("写后回读失败：期望文件但为目录 %s" % _label(label, p))
    if min_bytes and p.stat().st_size < min_bytes:
        raise LibraryError("写后回读失败：文件为空/过小 %s（%d 字节）"
                           % (_label(label, p), p.stat().st_size))
    return True


def verify_sha256(path, expected_hex, label=""):
    """目标文件 sha256 必须与期望一致（移动不改变内容，哈希是移动正确性的最强校验）。"""
    p = Path(path)
    verify_file(p, label=label)
    if not expected_hex:
        raise LibraryError("写后回读失败：缺少期望 sha256（%s）" % _label(label, p))
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    got = h.hexdigest()
    if got != expected_hex:
        raise LibraryError("写后回读失败：sha256 不一致 %s（期望 %s…，实际 %s…）"
                           % (_label(label, p), expected_hex[:12], got[:12]))
    return True


def verify_json(path, required_fields=(), label=""):
    """JSON 文件必须可解析，且 required_fields 中的键必须存在。失败 raise LibraryError。"""
    p = Path(path)
    verify_file(p, label=label)
    try:
        doc = read_json(p, None)
    except Exception as e:
        raise LibraryError("写后回读失败：JSON 无法解析 %s（%s）" % (_label(label, p), e))
    if doc is None:
        raise LibraryError("写后回读失败：JSON 为空/非法 %s" % _label(label, p))
    missing = [k for k in required_fields if k not in doc]
    if missing:
        raise LibraryError("写后回读失败：JSON 缺少关键字段 %s（%s）" % (missing, _label(label, p)))
    return doc


def verify_docx_nonempty(path, min_paras=1, label=""):
    """docx 必须可打开且段落数 >= min_paras（python-docx）。失败 raise LibraryError。"""
    p = Path(path)
    verify_file(p, label=label)
    try:
        from docx import Document
        doc = Document(str(p))
        n = len(doc.paragraphs)
    except Exception as e:
        raise LibraryError("写后回读失败：docx 无法打开 %s（%s）" % (_label(label, p), e))
    if n < min_paras:
        raise LibraryError("写后回读失败：docx 段落数异常 %s（%d < %d）"
                           % (_label(label, p), n, min_paras))
    return True


def verify_consistency(ent, label="数据一致性"):
    """复用三方对账：台账↔磁盘↔回收站有任一项待处理即 raise。"""
    res = consistency_check(ent)
    if not res.get("ok"):
        issues = ["%s：%s" % (i.get("type"), i.get("detail") or i.get("rel_path") or i.get("file"))
                  for i in res.get("issues", [])]
        raise LibraryError("写后回读失败：%s 对账不通过（%d 项）\n  - %s"
                           % (label, len(issues), "\n  - ".join(issues[:8])))
    return True


def readback_files(paths, label="批量文件"):
    """批量回读：paths 为 [(path, kwargs), ...] 或 path 列表，逐项 verify_file。"""
    for spec in paths:
        if isinstance(spec, (tuple, list)):
            p, kw = spec[0], dict(spec[1]) if len(spec) > 1 else {}
            verify_file(p, label=label, **kw)
        else:
            verify_file(spec, label=label)
    return True
