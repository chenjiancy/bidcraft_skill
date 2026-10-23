# -*- coding: utf-8 -*-
"""A. 批量生成 10 个版面范式样张 docx（dev/reports/layout-preview/），供转 PDF 拼图对比。"""
import json
import shutil
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from m6_tech import export  # noqa: E402
from m6_tech import layout as layout_mod  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "dev" / "reports" / "layout-preview"

PRESETS = [
    "single-column", "tabular", "two-column", "card", "image-left",
    "divider", "data-row", "image-right", "hybrid-flow", "minimal-clean",
]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = {"schema": "m6.layout-preview/v1", "items": []}
    for pid in PRESETS:
        tmp = tempfile.TemporaryDirectory()
        try:
            ent = layout_mod._builtin_preview_fixture(tmp.name)
            out_dir = ent / "项目级" / "预览项目" / "技术标" / "产出"
            export.cmd_tech_export(SimpleNamespace(
                root=tmp.name, enterprise="预览企业", project="预览项目",
                override="preset=%s" % pid, bid_mode="", out=str(out_dir), force=True))
            src = out_dir / "技术标_预览项目.docx"
            target = OUT / ("%s_技术标样张.docx" % pid)
            shutil.copyfile(str(src), str(target))
            manifest["items"].append({"preset": pid, "docx": str(target)})
            print("OK %s" % pid)
        finally:
            tmp.cleanup()
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                                       encoding="utf-8")
    print("清单: %s" % (OUT / "manifest.json"))


if __name__ == "__main__":
    main()
