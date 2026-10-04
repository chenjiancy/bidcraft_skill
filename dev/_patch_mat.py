# -*- coding: utf-8 -*-
"""③ 素材清单补全：把 filler 组合构建实际使用但未列明的素材登记进清单。"""
import json
from pathlib import Path

p = Path(r"E:\监理标书制作\和县建设工程监理有限公司\项目级\马鞍山和县化工园尾水水质提升工程（EPC总承包）监理\招标解析\素材清单.json")
d = json.loads(p.read_text(encoding="utf-8"))

# 1) 资质：补 房屋建筑工程监理甲级（组合占位 glob 使用，清单未列）
qual = d.setdefault("qualification_required", [])
existing = {q.get("name") for q in qual}
if "监理企业资质证书（房屋建筑甲级）" not in existing:
    qual.append({
        "name": "监理企业资质证书（房屋建筑甲级）",
        "status": "在库",
        "path": "资质/房屋建筑工程监理甲级_20281222_P0.png、资质/房屋建筑工程监理甲级_20281222_P1.png",
        "note": "房建甲级，2028-12-22前有效，2页",
        "用途": "附表1组织机构/【图片：企业资质证书扫描件】组合",
        "占位符键": "【图片：企业资质证书扫描件】",
    })

# 2) 荣誉：补 先进监理企业 + 监理示范工程（组合占位 glob 使用，清单未列）
honors = d.setdefault("honors", [])
honor_paths = {h.get("path") for h in honors}
add_honors = [
    ("先进监理企业（2025年度）", "荣誉/先进监理企业_20250101.png", "在库", "附表10其他资料（奖励）", "【荣誉行】/【图片：先进（优秀）监理企业证书】"),
    ("监理示范工程（2022）", "荣誉/监理示范工程_20221201.png", "在库", "附表10其他资料（奖励）", "【图片：监理示范（优质）工程】"),
    ("监理示范工程（2024）", "荣誉/监理示范工程_20241201.png", "在库", "附表10其他资料（奖励）", "【图片：监理示范（优质）工程】"),
    ("监理示范工程（2025）", "荣誉/监理示范工程_20251201.png", "在库", "附表10其他资料（奖励）", "【图片：监理示范（优质）工程】"),
]
for name, path, status, use, ph in add_honors:
    if path not in honor_paths:
        honors.append({
            "name": name, "status": status, "path": path,
            "用途": use, "占位符键": ph,
        })
        honor_paths.add(path)

# 3) 企业基础信息：补 委托代理人姓名（filler 组合占位使用；此前清单未登记）
biz = d.setdefault("企业基础信息", {})
if not (biz.get("委托代理人姓名") or "").strip():
    biz["委托代理人姓名"] = "孙婧"

p.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
print("qualification_required:", len(qual), "| honors:", len(honors), "| 委托代理人姓名:", biz.get("委托代理人姓名"))
