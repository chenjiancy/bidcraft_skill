# -*- coding: utf-8 -*-
"""⑦ generator · 格式契约 JSON 生成规则（M5 前置输入①，2026-10-10）。

从招标文件 docx（已转换）自动定位「第X章 投标/响应文件格式」章节，
按契约锚点序列（封面→开标一览表→投标函→附录→法代→授权→监理大纲→
资格证明附表1-10→承诺函→声明函）确定每个契约项 id 的块范围，生成：

    招标解析/格式契约/格式契约.json
    {"项目": <项目名>, "格式章节": <章节标题>, "格式文件": [{"id", "块范围", "标题"}, ...]}

设计要点：
- 锚点匹配对段落文本做「去空白」归一（兼容全角空格/竖排换行），锚点取
  独立标题段（eq=去空白后相等）或正则（re）。
- 块范围 = 上一锚点块 → 当前锚点块-1（左闭右开）；章节尾为最后锚点后。
- 未定位的锚点（如本项目无中小企业声明函）对应契约项块范围留空 → proj-gen
  按「契约中无此项」跳过，不阻断生成。
- 三分工艺：脚本只做确定性定位；边界确认归 agent/用户（proj-contract 输出
  定位结果供核对，可 --edit 后重跑）。
"""
import re
from pathlib import Path

from .gen_common import GenError
from .gen_text import _para_text

__all__ = ["build_contract", "locate_anchors", "CONTRACT_DEFAULT_RELPATH"]

# 默认落盘位置（去掉历史「第五章」硬编码，章节号自适应，2026-10-10）
CONTRACT_DEFAULT_RELPATH = "格式契约/格式契约.json"


def _clean(text):
    r"""去空白归一（\s 含全角空格 \u3000 / 换行 / 制表符）。"""
    return re.sub(r"\s+", "", text or "")


# 锚点序列（按格式章节内文件出现顺序，锚点=该契约文件的起点块）：
#   (契约id, 匹配方式, 模式)  方式 eq=去空白后相等；re=正则（已按去空白归一书写）
# 注意：目录条目（如「第六章响应文件格式42」带页码尾）会被章节正则的
# (?!\d) 负向前瞻排除；「开标一览表」在真实文件中常与上段合并（Word 转换
# 合并段落，如「日期：年月日开标一览表」），故用 re 含匹配。
ANCHOR_SEQ = [
    ("F02", "re", r"开标一览表"),                    # F02 起点；F01 终点=该块-1
    ("F03a", "eq", "一、投标函及投标函附录"),         # F03a 起点（含大标题段）
    ("F03b", "re", r"（二）投标函附录|\(二\)投标函附录"),
    ("F03c", "re", r"（三）投标函|\(三\)投标函"),      # 可缺省
    ("F04a", "re", r"法人代表资格证明|法定代表人资格证明"),
    ("F04b", "re", r"授权委托书"),
    ("F05", "re", r"监理管理文件"),
    ("F06a", "re", r"资格证明及辅助资料表"),
    ("F06b", "re", r"附表\s*1\s*[:：]"),
    ("F06c", "re", r"附表\s*2\s*[:：]"),
    ("F06d", "re", r"附表\s*3\s*[:：]"),
    ("F06e", "re", r"附表\s*4\s*[:：]"),
    ("F06f", "re", r"附表\s*5\s*[:：]"),
    ("F06g", "re", r"附表\s*6\s*[:：]"),
    ("F06h", "re", r"附表\s*7\s*[:：]"),
    ("F06i", "re", r"附表\s*8\s*[:：]"),
    ("F06j", "re", r"附表\s*9\s*[:：]"),
    ("F06k", "re", r"附表\s*10\s*[:：]"),
    ("F06l", "eq", "承诺函"),                         # 项目总监到岗承诺函（附表10后）
    ("F07", "eq", "中小企业声明函"),                   # 可缺省（本项目无）
    ("F09", "re", r"基本账户开户许可证"),              # 可缺省
    ("F13", "eq", "中小企业声明函"),                   # 可缺省
]
# 注：锚点 id 与 gen_common.FILE_MAP 的契约 id 对应；F06l 为 F06 系列后的
# 承诺函边界（真实文件承诺函位于附表10 之后），F07 起点=承诺函锚点。
# 与 FILE_MAP 中 F07 语义一致（承诺函_项目总监到岗.docx）。

# 章节正则：(?!\d) 排除目录条目「第X章…格式42」（页码尾），只命中正文标题
CHAPTER_RE = r"第[一二三四五六七八九十百]+章\s*(投标文件格式|响应文件格式|响应文件的组成)(?!\d)"

# 契约 id → 锚点 id 映射（锚点=该契约文件起点块；"__CHAPTER__" 起点为格式
# 章节标题块，终点=第一个锚点（F02 开标一览表）-1）
ID_ANCHOR = {
    "F01": "__CHAPTER__", "F02": "F02", "F03a": "F03a", "F03b": "F03b",
    "F04a": "F04a", "F04b": "F04b", "F05": "F05", "F06a": "F06a",
    "F06b": "F06b", "F06c": "F06c", "F06d": "F06d", "F06e": "F06e",
    "F06f": "F06f", "F06g": "F06g", "F06h": "F06h", "F06i": "F06i",
    "F06j": "F06j", "F06k": "F06k", "F07": "F06l", "F09": "F09",
    "F13": "F13", "F14": "F13",   # F14 划型标准并入 F13（中小企业声明函）
}


def _match(text_clean, mode, pattern):
    if mode == "eq":
        return text_clean == pattern
    return re.search(pattern, text_clean) is not None


def _find_chapter(texts):
    """返回 (章节起点块索引, 章节标题文本)；None 表示未找到。

    先正向找第一个「开标一览表」块，再向前回溯最近的「第X章…格式」标题；
    无开标一览表时退化正向第一个命中。返回索引供 build_contract 复用。
    """
    import re as _re
    f01_idx = None
    for i, t in enumerate(texts):
        if t and _match(t, "re", r"开标一览表"):
            f01_idx = i
            break
    if f01_idx is not None:
        for i in range(f01_idx, -1, -1):
            m = _re.search(CHAPTER_RE, texts[i])
            if m:
                return i, texts[i]
    for i, t in enumerate(texts):
        m = _re.search(CHAPTER_RE, t)
        if m:
            return i, t
    return None, ""


def locate_anchors(blocks):
    """扫描 blocks（_extract_blocks 输出），返回 (chapter_title, {锚点id: 块索引})。

    定位策略（2026-10-10 针对真实 .doc 转换件校准）：
      1. 正向找第一个「开标一览表」块（F01 锚点，re 含匹配——真实文件中该标题
         常与上段合并，如「日期：年月日开标一览表」）；
      2. 从该块**向前**回溯最近的「第X章…格式」标题作为格式章节起点——可同时
         排除目录条目（带页码尾「…格式42」）与正文章节导航列表（无页码的
         「第六章响应文件格式」段，位于供应商须知内、离锚点远）；
      3. 从章节起点起顺序找各锚点第一次命中。未命中锚点不在返回 dict 中。
    """
    texts = []
    for blk in blocks:
        t = ""
        if blk.get("type") == "para":
            t = _clean(_para_text(blk["node"]))
        texts.append(t)
    chapter_idx, chapter_title = _find_chapter(texts)
    if chapter_idx is None:
        raise GenError("未找到格式章节（第X章 投标/响应文件格式）——请人工确认源文件是否含格式章节")
    anchors = {}
    pos = chapter_idx
    for aid, mode, pattern in ANCHOR_SEQ:
        found = None
        for i in range(pos, len(texts)):
            if texts[i] and _match(texts[i], mode, pattern):
                found = i
                break
        if found is None:
            continue                      # 未命中：该锚点及其后续契约项留空
        anchors[aid] = found
        pos = found
    return chapter_title, anchors


def build_contract(blocks, project, chapter_end_extra=0):
    """生成格式契约 dict：{项目, 格式章节, 格式文件:[{id, 块范围, 标题}]}。

    chapter_end_extra：章节尾额外扩展块数（默认 0；一般无需）。
    """
    import re as _re
    chapter_title, anchors = locate_anchors(blocks)
    # 章节起点复用 _find_chapter（反向回溯），保证 F01 起点=正文格式章节标题
    texts = []
    for blk in blocks:
        t = ""
        if blk.get("type") == "para":
            t = _clean(_para_text(blk["node"]))
        texts.append(t)
    chapter_idx, _ = _find_chapter(texts)
    anchor_ids = list(anchors.keys())
    last_anchor_idx = anchors[anchor_ids[-1]] if anchor_ids else chapter_idx
    # 章节尾：最后一个命中锚点之后的下一个「第X章」标题-1；无后续章节 → 末个非空块
    texts = []
    for blk in blocks:
        t = ""
        if blk.get("type") == "para":
            t = _clean(_para_text(blk["node"]))
        texts.append(t)
    end_idx = last_anchor_idx
    for i in range(last_anchor_idx + 1, len(texts)):
        if _re.search(CHAPTER_RE, texts[i]):
            end_idx = i - 1
            break
        if texts[i]:
            end_idx = i
    # 建 锚点顺序列表（按 ANCHOR_SEQ 顺序）
    seq = [(aid, anchors[aid]) for aid, _, _ in ANCHOR_SEQ if aid in anchors]
    files = []
    for cid, anchor_key in ID_ANCHOR.items():
        if anchor_key not in anchors and anchor_key != "__CHAPTER__":
            files.append({"id": cid, "块范围": [], "标题": ""})
            continue
        if anchor_key == "__CHAPTER__":
            idx = chapter_idx
            # F01 封面终点 = 第一个锚点（F02 开标一览表）-1
            end = (seq[0][1] - 1) if seq else (end_idx + chapter_end_extra)
        else:
            idx = anchors[anchor_key]
            end = end_idx + chapter_end_extra
            for j, (aid2, _idx2) in enumerate(seq):
                if aid2 == anchor_key and j + 1 < len(seq):
                    end = seq[j + 1][1] - 1
                    break
        title = ""
        # 标题取该锚点段落文本（缩略 60 字）
        if idx < len(blocks) and blocks[idx].get("type") == "para":
            title = _clean(_para_text(blocks[idx]["node"]))[:60]
        files.append({"id": cid, "块范围": [idx, end], "标题": title})
    return {"项目": project, "格式章节": chapter_title, "格式文件": files}


def build_contract_from_docx(src_docx, project):
    """从 docx 文件构建契约（复用 _extract_blocks）。"""
    from .gen_blocks import _extract_blocks
    blocks, _ = _extract_blocks(src_docx)
    return build_contract(blocks, project)


def write_contract(ent, project, contract, out_path=None):
    """落盘契约 JSON 到 招标解析/格式契约/格式契约.json（默认）。返回路径。"""
    import json
    from _shared import core
    proj_dir = Path(ent) / "项目级" / project
    if not proj_dir.is_dir():
        raise GenError("项目目录不存在：项目级/%s" % project)
    p = Path(out_path) if out_path else proj_dir / "招标解析" / CONTRACT_DEFAULT_RELPATH
    p.parent.mkdir(parents=True, exist_ok=True)
    core.write_json(p, contract)
    return p
