# -*- coding: utf-8 -*-
"""docx_tools：docx 结构深读 + 格式/结构审计共享工具（服务 M2/M5/M7）。

移植自豆包 word 技能能力逻辑（read.py/audit.py），平台无关重写（python-docx 生态
不依赖：本包仅用 lxml + 标准库；.doc 转换复用 com_util.WordCOM）。
CLI 子命令：docx-read（维度 0-7 深读）、docx-audit（包有效性/样式/表格/段落/
属性顺序/基线差异审计）。不占 m* 模块序号（偏离项②，规则对齐清单）。
"""
from __future__ import annotations


def register_parser(subparsers) -> None:
    """挂载 docx-read / docx-audit 子命令到 bidcraft.py 薄壳。"""
    from . import audit_cli, reader_cli

    reader_cli.register_parser(subparsers)
    audit_cli.register_parser(subparsers)
