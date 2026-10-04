# -*- coding: utf-8 -*-
"""对比 ZipInfo 元数据（时间戳/属性/extra字段）OLD vs RT。"""
import zipfile
from pathlib import Path

DEMO = Path(r"E:\bidcraft_skill\dev\preview_demo")
OLD = Path(r"E:\监理标书制作\示例建设工程监理有限公司\项目级\示例示例园区尾水水质提升工程（EPC总承包）监理\项目模板\资格证明及辅助资料表.docx")
RT = DEMO / "matrix" / "old_roundtrip_资格证明.docx"

def infos(p):
    with zipfile.ZipFile(p) as z:
        return {i.filename: i for i in z.infolist()}

a, b = infos(OLD), infos(RT)
out = ["%-38s %-22s | %-22s" % ("entry", "OLD", "RT")]
for name in a:
    ia, ib = a[name], b[name]
    out.append("%-38s t=%s/%s  cr=%s/%s  sys=%s/%s  ext=%s/%s  extra=%d/%d  ver=%d/%d" % (
        name, ia.date_time, ib.date_time, ia.create_system, ib.create_system,
        ia.create_version, ib.create_version, ia.external_attr, ib.external_attr,
        len(ia.extra), len(ib.extra), ia.extract_version, ib.extract_version))
(DEMO / "rezip" / "meta_diff.txt").write_text("\n".join(out), encoding="utf-8")
