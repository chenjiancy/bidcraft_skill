# -*- coding: utf-8 -*-
"""
bidcraft · M6 技术标制作 —— 包入口

分层：
  rules_base / rules_chapters / rules_check / rules   F1–F11 纯逻辑（无 I/O）
  store                                              存储层（原子写 / 状态机 / 闸门）
  sources                                            M4 数据源读取与设置推导
  ctxpack                                            上下文包组装（m6.ctx/v1）
  cli                                                CLI 首批 4 命令（由 bidcraft.py 注册）
"""
from .cli import register_parser  # noqa: F401
