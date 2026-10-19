# -*- coding: utf-8 -*-
"""docx_tools.audit_cli：docx-audit 子命令：包检查编排 + 基线差异 + 报告。

模式：
* 无 --source：独立审计目标 docx。
* 有 --source：对源与目标各跑同一组探测器；抑制未变化的非致命源发现；基线自身的
  致命包问题仍上报（带 source: 前缀），使比较不可信时明确暴露。

报告：JSON + 人读 MD 双份（--out-dir 写入），stdout 同步输出完整 JSON
（BEGIN/END AUDIT REPORT JSON 标记）。退出码 0=通过 / 1=有错误 / 2=输入无效。
能力逻辑借鉴豆包 word 技能 audit.py（平台无关重写，非整文件复制）。
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any
from zipfile import BadZipFile, ZipFile

from lxml import etree

from .common import (
    NS,
    STORY_PART_RE,
    FIXED_STORY_RE,
    canonical_xml_hash,
    parse_xml,
    resolve_alternate_content,
    sha256_bytes,
    sha256_file,
    wqn,
    wtag,
)
from .audit import (
    REPAIR_HINTS,
    enrich_findings,
    extract_styles,
    issue,
)
from .audit_extract import (
    drawing_id_findings,
    extract_drawings,
    extract_paragraphs,
    extract_sections_for_audit,
    extract_tables,
    ooxml_property_order_findings,
    structural_hash,
)

FATAL_PACKAGE_CODES = {
    "E_DOCX_OPEN",
    "E_ZIP_CRC",
    "E_ZIP_MEMBER_DUPLICATE",
    "E_PART_MISSING",
    "E_XML_INVALID",
    "E_DOCUMENT_ROOT_INVALID",
}
REPORT_TOKEN_BUDGET = 60_000


class AuditError(ValueError):
    pass


# ---------------------------------------------------------------------------
# inspect_docx：包级检查 + 清单提取
# ---------------------------------------------------------------------------
def inspect_docx(path: Path) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    if not path.exists():
        raise AuditError("DOCX does not exist: %s" % path)
    try:
        with ZipFile(path) as archive:
            bad_member = archive.testzip()
            if bad_member:
                return {
                    "file": {
                        "path": str(path.resolve()),
                        "size": path.stat().st_size,
                        "sha256": sha256_file(path),
                    },
                    "findings": [
                        issue(
                            "error",
                            "E_ZIP_CRC",
                            bad_member,
                            "ZIP CRC check failed",
                        )
                    ],
                }
            names = [item.filename for item in archive.infolist() if not item.is_dir()]
            duplicate_members = sorted(
                name for name, count in Counter(names).items() if count > 1
            )
            for name in duplicate_members:
                findings.append(
                    issue(
                        "error",
                        "E_ZIP_MEMBER_DUPLICATE",
                        name,
                        "OOXML package contains duplicate ZIP members",
                        actual=Counter(names)[name],
                    )
                )
            name_set = set(names)
            required = {"[Content_Types].xml", "_rels/.rels", "word/document.xml"}
            for missing in sorted(required - name_set):
                findings.append(
                    issue(
                        "error", "E_PART_MISSING", missing, "required OOXML part is missing"
                    )
                )
            xml_roots: dict[str, etree._Element] = {}
            parts: dict[str, dict[str, Any]] = {}
            for name in sorted(names):
                data = archive.read(name)
                entry: dict[str, Any] = {"size": len(data), "sha256": sha256_bytes(data)}
                if name.endswith((".xml", ".rels")):
                    try:
                        root = parse_xml(data, name)
                        xml_roots[name] = root
                        entry["canonical_sha256"] = canonical_xml_hash(root)
                        entry["structure_sha256"] = structural_hash(
                            root, clear_text=True
                        )
                    except ValueError as exc:
                        findings.append(issue("error", "E_XML_INVALID", name, str(exc)))
                parts[name] = entry
            semantic_roots = {
                name: (
                    resolve_alternate_content(root)
                    if not name.endswith(".rels") and name != "[Content_Types].xml"
                    else root
                )
                for name, root in xml_roots.items()
            }
            document = semantic_roots.get("word/document.xml")
            if document is not None and document.tag != wtag("document"):
                findings.append(
                    issue(
                        "error",
                        "E_DOCUMENT_ROOT_INVALID",
                        "word/document.xml",
                        "main document part is not a WordprocessingML w:document",
                        actual=etree.QName(document).localname,
                        expected="w:document",
                    )
                )
            elif document is not None and len(document.findall(wtag("body"), namespaces=NS)) != 1:
                findings.append(
                    issue(
                        "error",
                        "E_DOCUMENT_ROOT_INVALID",
                        "word/document.xml",
                        "main document must contain exactly one direct w:body",
                        expected=1,
                        actual=len(document.findall(wtag("body"), namespaces=NS)),
                    )
                )
            sections = extract_sections_for_audit(document)
            styles = extract_styles(semantic_roots)
            for part, root in sorted(semantic_roots.items()):
                findings.extend(ooxml_property_order_findings(part, root))
            paragraphs: list[dict[str, Any]] = []
            tables: list[dict[str, Any]] = []
            drawings: list[dict[str, Any]] = []
            for part in sorted(semantic_roots):
                if not STORY_PART_RE.match(part):
                    continue
                root = semantic_roots[part]
                paragraphs.extend(extract_paragraphs(part, root))
                tables.extend(extract_tables(part, root))
                drawings.extend(extract_drawings(part, root))
            findings.extend(drawing_id_findings(drawings))
            manifest: dict[str, Any] = {
                "file": {
                    "path": str(path.resolve()),
                    "size": path.stat().st_size,
                    "sha256": sha256_file(path),
                },
                "parts": parts,
                "sections": sections,
                "styles": styles,
                "paragraphs": paragraphs,
                "tables": tables,
                "drawings": drawings,
                "summary": {
                    "part_count": len(parts),
                    "section_count": len(sections),
                    "paragraph_count": len(paragraphs),
                    "table_count": len(tables),
                    "drawing_count": len(drawings),
                    "character_count": sum(
                        len(str(paragraph.get("text") or ""))
                        for paragraph in paragraphs
                    ),
                },
            }
            manifest["findings"] = findings
            return manifest
    except (BadZipFile, OSError, NotImplementedError, RuntimeError, EOFError) as exc:
        return {
            "file": {"path": str(path.resolve())},
            "findings": [issue("error", "E_DOCX_OPEN", str(path), str(exc))],
        }


# ---------------------------------------------------------------------------
# 基线差异过滤
# ---------------------------------------------------------------------------
def _finding_identity(finding: dict[str, Any]) -> tuple[Any, ...]:
    return (
        finding.get("code"),
        finding.get("location"),
        finding.get("message"),
        json.dumps(finding.get("expected"), sort_keys=True, ensure_ascii=False),
        json.dumps(finding.get("actual"), sort_keys=True, ensure_ascii=False),
    )


def filter_unchanged_baseline_findings(
    source_findings: list[dict[str, Any]],
    target_findings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """抑制在源中发现过且未变化的非致命发现（multiset 比较）。

    致命包发现（FATAL_PACKAGE_CODES）不抑制：它们会让源/目标比较不可信。
    """
    source_multiset = Counter(
        _finding_identity(item)
        for item in source_findings
        if item.get("code") not in FATAL_PACKAGE_CODES
    )
    retained: list[dict[str, Any]] = []
    for item in target_findings:
        identity = _finding_identity(item)
        if item.get("code") not in FATAL_PACKAGE_CODES and source_multiset[identity] > 0:
            source_multiset[identity] -= 1
            continue
        retained.append(item)
    return retained


# ---------------------------------------------------------------------------
# 报告聚合
# ---------------------------------------------------------------------------
def summarize_by_code(findings: list[dict[str, Any]]) -> dict[str, Any]:
    by_code = Counter(item.get("code") for item in findings)
    return {
        "by_code": dict(sorted(by_code.items())),
        "total": len(findings),
    }


def aggregate_findings(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for finding in findings:
        groups.setdefault(finding.get("code", "E_UNKNOWN"), []).append(finding)
    result: list[dict[str, Any]] = []
    for code, group in sorted(groups.items()):
        first = group[0]
        result.append(
            {
                "code": code,
                "severity": first.get("severity", "error"),
                "count": len(group),
                "message": first.get("message"),
                "repair_hint": first.get("repair_hint")
                or REPAIR_HINTS.get(code, ""),
                "locations": [
                    str(item.get("location")) for item in group[:10]
                ],
                "examples": [
                    {key: value for key, value in item.items() if key in ("expected", "actual", "blocking")}
                    for item in group[:3]
                ],
            }
        )
    return result


# ---------------------------------------------------------------------------
# command_audit
# ---------------------------------------------------------------------------
def _resolve_docx(source: Path, tmpdir: Path) -> Path:
    if source.suffix.lower() != ".doc":
        return source
    from .. import com_util

    if not getattr(com_util, "HAVE_COM", False):
        raise AuditError(
            "当前环境无 Windows Word COM，无法把 .doc 转换为 .docx；请改用 .docx 输入"
        )
    docx_path = tmpdir / (source.stem + ".docx")
    with com_util.WordCOM(visible=False) as word:
        word.convert_to_docx(str(source), str(docx_path))
    return docx_path


def command_audit(args: argparse.Namespace) -> int:
    if args.source is not None and args.source.resolve() == args.file.resolve():
        raise AuditError("--source must be a different DOCX from the target")
    if not args.file.is_file():
        raise AuditError("DOCX does not exist: %s" % args.file)
    with tempfile.TemporaryDirectory() as tmp_name:
        target_path = _resolve_docx(args.file, Path(tmp_name))
        target_manifest = inspect_docx(target_path)
        target_fatal = [
            item
            for item in target_manifest.get("findings", [])
            if item.get("code") in FATAL_PACKAGE_CODES
        ]
        findings = list(target_manifest.get("findings", []))
        mode = "source_compare" if args.source is not None else "standalone"
        source_manifest: dict[str, Any] | None = None
        source_fatal: list[dict[str, Any]] = []
        source_comparison_performed = False
        if args.source is not None:
            source_path = _resolve_docx(args.source, Path(tmp_name))
            source_manifest = inspect_docx(source_path)
            source_fatal = [
                item
                for item in source_manifest.get("findings", [])
                if item.get("code") in FATAL_PACKAGE_CODES
            ]
            for source_error in source_fatal:
                copied = dict(source_error)
                copied["location"] = "source:%s" % source_error.get("location", "")
                copied["message"] = "source DOCX is not usable for comparison: %s" % str(
                    source_error.get("message") or "invalid source"
                )
                findings.append(copied)
            if not source_fatal and not target_fatal:
                findings = filter_unchanged_baseline_findings(
                    list(source_manifest.get("findings", [])), findings
                )
                source_comparison_performed = True
    active = enrich_findings(findings)
    raw_errors = [item for item in active if item.get("severity") == "error"]
    input_invalid = bool(target_fatal or source_fatal)
    if input_invalid:
        automated_status = "invalid"
    elif raw_errors:
        automated_status = "failed"
    else:
        automated_status = "passed"
    error_summary = summarize_by_code(raw_errors)
    error_groups = aggregate_findings(raw_errors)
    checks = {
        "package_validity": {
            "performed": True,
            "passed": not target_fatal and not source_fatal,
        },
        "ooxml_property_order": {
            "performed": not input_invalid,
            "passed": not input_invalid and "E_OOXML_TBLPR_ORDER" not in error_summary["by_code"] and "E_OOXML_TCPR_ORDER" not in error_summary["by_code"],
        },
        "drawing_identity": {
            "performed": not input_invalid,
            "passed": not input_invalid and "E_OOXML_DOCPR_ID_INVALID" not in error_summary["by_code"] and "E_DRAWING_EXTENT_INVALID" not in error_summary["by_code"],
        },
        "source_comparison": {"performed": source_comparison_performed},
    }
    report: dict[str, Any] = {
        "schema_version": 1,
        "reporting_policy": "errors_only",
        "mode": mode,
        "target": target_manifest.get("file", {}),
        "source": source_manifest.get("file", {}) if source_manifest else None,
        "automated_status": automated_status,
        "automated_checks_passed": automated_status == "passed",
        "error_count": len(raw_errors),
        "error_summary": error_summary,
        "errors": error_groups,
        "checks": checks,
        "input_valid": not input_invalid,
        "execution_completed": True,
    }
    if _estimate_tokens(report) > REPORT_TOKEN_BUDGET:
        report["errors"] = []
        report["report_budget"] = {
            "trim_level": 3,
            "detail": "errors[] omitted to satisfy the token budget; see error_summary.by_code",
        }
    _emit(args, report, automated_status, mode, len(raw_errors))
    if input_invalid:
        return 2
    return 0 if not raw_errors else 1


def _estimate_tokens(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False))


def _emit(args, report: dict[str, Any], status: str, mode: str, error_count: int) -> None:
    """stdout 输出状态行 + 完整 JSON（BEGIN/END 标记）；--out-dir 写 JSON+MD 双份。"""
    header = "[%s] mode=%s errors=%d" % (status.upper(), mode, error_count)
    json_text = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2)
    _stdout(header)
    _stdout("----- BEGIN AUDIT REPORT JSON (complete; do not read any file) -----")
    _stdout(json_text)
    _stdout("----- END AUDIT REPORT JSON -----")
    if args.out_dir:
        out_dir = Path(args.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        stem = Path(args.file).stem
        (out_dir / ("%s.docx-audit.json" % stem)).write_text(
            json_text, encoding="utf-8"
        )
        (out_dir / ("%s.docx-audit.md" % stem)).write_text(
            _report_markdown(report), encoding="utf-8"
        )


def _report_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# docx-audit 报告",
        "",
        "- 模式：%s" % report.get("mode"),
        "- 状态：%s" % report.get("automated_status"),
        "- 输入有效：%s" % report.get("input_valid"),
        "- 错误数：%d" % report.get("error_count", 0),
        "- 目标：%s" % (report.get("target") or {}).get("path", ""),
    ]
    if report.get("source"):
        lines.append("- 基线：%s" % report["source"].get("path", ""))
    lines.append("")
    summary = report.get("error_summary", {})
    by_code = summary.get("by_code", {})
    if by_code:
        lines.append("## 按错误码汇总")
        lines.append("")
        lines.append("| 错误码 | 数量 |")
        lines.append("|---|---|")
        for code, count in sorted(by_code.items()):
            lines.append("| %s | %d |" % (code, count))
    else:
        lines.append("无错误发现。")
    lines.append("")
    groups = report.get("errors", [])
    if groups:
        lines.append("## 错误明细（按码分组，最多各取 10 处位置）")
        lines.append("")
        for group in groups:
            lines.append("### %s × %d" % (group["code"], group["count"]))
            lines.append("")
            lines.append("%s" % group.get("message", ""))
            if group.get("repair_hint"):
                lines.append("")
                lines.append("> 修复建议：%s" % group["repair_hint"])
            for location in group.get("locations", []):
                lines.append("- `%s`" % location)
            lines.append("")
    return "\n".join(lines) + "\n"


def _stdout(text: str) -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    print(text)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def register_parser(subparsers) -> None:
    parser = subparsers.add_parser(
        "docx-audit",
        help="docx 格式/结构审计（包有效性/样式/表格/段落/属性顺序/基线差异）",
    )
    parser.add_argument("--file", required=True, type=Path, help="目标 docx 文件路径")
    parser.add_argument(
        "--source", type=Path,
        help="可选：基线 docx（企业模板/项目模板），用于格式结构差异过滤",
    )
    parser.add_argument(
        "--out-dir",
        help="可选：审计报告输出目录（写入 JSON + MD 双份，UTF-8）",
    )
    parser.set_defaults(func=command_audit)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="docx-audit CLI")
    register_parser(parser)
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except AuditError as exc:
        _stdout("[INPUT ERROR] %s" % exc)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
