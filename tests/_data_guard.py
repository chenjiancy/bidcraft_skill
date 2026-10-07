# -*- coding: utf-8 -*-
"""真实数据用例前置依赖清单化（改进清单④ / golden-经验总结 第 4 条）。

背景：真实数据依赖用例的 skip 条件不应只看"企业根目录存在"，而必须列出
用例实际依赖的全部数据文件（格式契约/素材清单/项目模板/简历图等），
任一缺失 → SkipTest 而非运行后报错。

用法：
    from _data_guard import require_data, skip_unless_data, env_ent_root, env_proj_root

    # 1) 显式检查：返回 (是否就绪, 缺失清单)
    ok, missing = require_data([...依赖路径...])

    # 2) 装饰器（类或方法）：任一缺失 → SkipTest（reason 自动带缺失清单）
    @skip_unless_data([...依赖路径...])
    class TestReal(unittest.TestCase): ...

    # 3) 环境变量注入真实路径（与既有约定一致）：
    #    BIDCRAFT_TEST_ENT=E:\\监理标书制作\\和县建设工程监理有限公司
    #    BIDCRAFT_TEST_PROJ=马鞍山和县化工园尾水水质提升工程（EPC总承包）监理
"""

import os
import unittest
from pathlib import Path

DEFAULT_ENT = r"E:\监理标书制作\示例建设工程监理有限公司"
DEFAULT_PROJ = "示例化工园尾水水质提升工程（EPC总承包）监理"


def env_ent_root():
    """企业根目录：环境变量 BIDCRAFT_TEST_ENT 或示例名（公网安全默认）。"""
    return Path(os.environ.get("BIDCRAFT_TEST_ENT", DEFAULT_ENT))


def env_proj_root(ent=None):
    """项目根目录：<企业根>/项目级/<BIDCRAFT_TEST_PROJ 或示例名>。"""
    ent = Path(ent) if ent else env_ent_root()
    return ent / "项目级" / os.environ.get("BIDCRAFT_TEST_PROJ", DEFAULT_PROJ)


def require_data(paths, base=None):
    """检查依赖数据文件/目录全部存在（只读，不创建）。

    paths: 相对 base 的路径清单（正/反斜杠均可；目录/文件皆可）。
    base:  根目录；缺省为企业根（BIDCRAFT_TEST_ENT 或示例名）。
    返回 (是否全部就绪, 缺失路径清单)。
    """
    base = Path(base) if base else env_ent_root()
    missing = []
    for p in paths:
        if not (base / p).exists():
            missing.append(str(p).replace("\\", "/"))
    return (not missing), missing


def skip_unless_data(paths, base=None, reason=None):
    """unittest.skipUnless 风格的类/方法装饰器：任一依赖数据缺失 → SkipTest。

    reason 缺省时自动列出缺失清单（便于 CI 日志定位）。
    """
    ok, missing = require_data(paths, base=base)
    if ok:
        return lambda obj: obj
    msg = reason or ("真实数据前置缺失，跳过：%s" % "、".join(missing))
    return unittest.skip(msg)
