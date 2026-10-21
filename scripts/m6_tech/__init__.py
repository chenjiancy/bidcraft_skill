# -*- coding: utf-8 -*-
"""
bidcraft · M6 技术标制作 —— 包入口

分层：
  rules_base / rules_chapters / rules_check / rules   F1–F11 纯逻辑（无 I/O）
  store                                              存储层（原子写 / 状态机 / 闸门）
  sources                                            M4 数据源读取与设置推导
  ctxpack                                            上下文包组装（m6.ctx/v1）
  layout                                             排版预设读取与 tech-layout（T13）
  writer / report                                    正文落盘（tech-parse）/ 通道A 检查与闸门②报告
  cli                                                CLI 命令（由 bidcraft.py 注册）
"""
from .cli import register_parser  # noqa: F401
