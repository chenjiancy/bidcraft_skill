# -*- coding: utf-8 -*-
"""临时根端到端手验：组合补丁 → 专家包 → tech-init --expert-pack 生效（不触碰真实素材库）。
验证完自动清理；产物仅打印路径证据。
"""
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scripts"))

import bidcraft
from m6_tech import layout

REPO = Path(__file__).resolve().parents[2]
tmp = tempfile.mkdtemp(prefix="bidcraft_closedloop_")
root = Path(tmp) / "素材库"
shared = root / "共享资源" / "技术标风格"
shared.mkdir(parents=True)
shutil.copy(str(REPO / "共享资源" / "技术标风格" / "layout-presets.json"), str(shared / "layout-presets.json"))
pk = shared / "专家包" / "official-tech"
pk.mkdir(parents=True)
shutil.copy(str(REPO / "共享资源" / "技术标风格" / "专家包" / "official-tech" / "taxonomy.json"),
            str(pk / "taxonomy.json"))

# 1) 组合补丁（模拟设计器「存组合」输出：palette=steel-cyan, decoration=rich）
doc = json.loads((shared / "layout-presets.json").read_text(encoding="utf-8"))
combo = dict(doc["default"])
combo["palette"] = "steel-cyan"
combo["decoration"] = "rich"
patch = root / "组合补丁_端到端.json"
patch.write_text(json.dumps({
    "schema": "m6.layout-designer/v1", "version": "1.2", "kind": "combo-patch",
    "name": "端到端验证组合", "bidMode": "明标", "layout": combo,
}, ensure_ascii=False), encoding="utf-8")

def run(*argv):
    code = 0
    try:
        bidcraft.main(["--root", str(root)] + list(argv))
    except SystemExit as e:
        code = e.code or 0
    return code

# 2) dry-run（不写盘）
assert run("tech-layout", "--apply-combo", str(patch)) == 0
pdir = shared / "专家包" / "custom-single-column-steel-cyan"
assert not pdir.exists(), "dry-run 不应写盘"

# 3) --confirm 生成专家包
assert run("tech-layout", "--apply-combo", str(patch), "--confirm") == 0
m = json.loads((pdir / "包.json").read_text(encoding="utf-8"))
assert m["layoutCombo"]["palette"] == "steel-cyan"
assert m["layoutCombo"]["decoration"] == "rich"
t = json.loads((pdir / "taxonomy.json").read_text(encoding="utf-8"))
assert t["pack"] == "custom-single-column-steel-cyan"

# 4) 专家包进入生成链路：tech-init 建骨架 → tech-outline --expert-pack 绑定（落盘 layout 十五组）
proj = root / "测试企业" / "项目级" / "演示项目"
tech = proj / "技术标"
(tech / "章节").mkdir(parents=True)
tdir = proj / "招标解析"
tdir.mkdir(parents=True)
points = {
    "project": "演示项目",
    "modules": [
        {"id": "basic", "title": "项目基本信息", "type": "fields",
         "fields": {"项目名称": {"value": "演示项目", "evidence": "e"}}},
        {"id": "project_overview", "title": "项目概况", "type": "fields",
         "fields": {"项目概况": {"value": "演示项目为公共建筑", "evidence": "e"}}},
        {"id": "scoring", "title": "评分办法", "type": "score_items",
         "score_items": [{"item": "监理大纲", "weight": 50, "unit": "分", "evidence": "e"}]},
        {"id": "reject", "title": "废标红线", "type": "items",
         "items": [{"type": "格式", "rule": "技术标总页数不超过 60 页；按明标编制", "evidence": "e"}]},
    ],
}
(tdir / "投标要点_演示项目.json").write_text(
    json.dumps(points, ensure_ascii=False), encoding="utf-8")
code = run("init-enterprise", "--name", "测试企业")
assert code == 0, "init-enterprise 应成功"
code = run("tech-init", "--project", "演示项目")
assert code == 0, "tech-init 应成功"
draft = tech / "章节树草案.json"
draft.write_text(json.dumps({
    "schema": "m6.tree/v1", "project": "演示项目",
    "chapters": [{
        "id": "ch-01", "no": "1", "title": "工程概况与监理范围", "level": 1,
        "scoreRefs": [{"idx": 0, "item": "监理大纲", "weight": 50}],
        "keyPoints": ["监理大纲", "工程概况", "监理范围"],
        "wordCnt": 3000, "dependsOnMaterials": ["project_overview"],
    }],
}, ensure_ascii=False), encoding="utf-8")
code = run("tech-outline", "--project", "演示项目", "--file", str(draft),
           "--expert-pack", "custom-single-column-steel-cyan", "--confirm")
assert code == 0, "tech-outline 应成功"
tree = json.loads((tech / "章节树.json").read_text(encoding="utf-8"))
chain = tree.get("layout") if isinstance(tree.get("layout"), dict) else {}
assert chain.get("palette") == "steel-cyan", "生成链路未落 steel-cyan: %r" % chain
assert chain.get("decoration") == "rich", "生成链路未落 rich: %r" % chain

print("CLOSED-LOOP OK: patch -> pack(custom-single-column-steel-cyan) -> tech-init --expert-pack 落盘 palette=steel-cyan decoration=rich")
print("专家包: %s" % pdir)
shutil.rmtree(tmp, ignore_errors=True)
