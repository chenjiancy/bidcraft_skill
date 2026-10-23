# -*- coding: utf-8 -*-
"""维度落实样张：12 维度代表性组合 → dev/reports/dimension-samples/<名>.docx。
用法：python dev/prototypes/_gen_dimension_samples.py [维度名...]；无参 = 全部。"""
import shutil
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from m6_tech import export, layout  # noqa: E402

OUT = Path(r"E:\bidcraft_skill\dev\reports\dimension-samples")
OUT.mkdir(parents=True, exist_ok=True)

BASE = "preset=single-column;palette=deep-indigo;cover=full-block;decoration=standard;font=gov-gongwen;imageRatio=mid;imageRule=hybrid;imageLayout=split-h;pageSetup=p1-standard-a4;headingSystem=h1-gbt-arabic;tocStyle=t1-jianyu-auto;tableStyle=tb1-three-line;captionSystem=c2-cy-chapter;paragraphStyle=pa7-jianyu-15;headerFooter=hf1-classic-enterprise"

SAMPLE_DEFS = [
    ("s00_默认基线", BASE),
    ("s01_字体_现代商务", BASE.replace("font=gov-gongwen", "font=modern-business")),
    ("s02_字体_全仿宋公文", BASE.replace("font=gov-gongwen", "font=fangsong-official")),
    ("s03_标题_南阳七级混排", BASE.replace("headingSystem=h1-gbt-arabic", "headingSystem=h4-nanyang-7level")),
    ("s04_标题_通辽暗标式", BASE.replace("headingSystem=h1-gbt-arabic", "headingSystem=h10-tongliao-tender")),
    ("s05_表格_表头底纹全框", BASE.replace("tableStyle=tb1-three-line", "tableStyle=tb4-header-fill")),
    ("s06_表格_网格细线", BASE.replace("tableStyle=tb1-three-line", "tableStyle=tb5-grid-fine")),
    ("s07_题注_全文连续", BASE.replace("captionSystem=c2-cy-chapter", "captionSystem=c1-gbt-seq")),
    ("s08_题注_附录字母", BASE.replace("captionSystem=c2-cy-chapter", "captionSystem=c6-appendix-letter")),
    ("s09_封面_渐变", BASE.replace("cover=full-block", "cover=gradient")),
    ("s10_封面_顶部通栏", BASE.replace("cover=full-block", "cover=top-banner")),
    ("s11_封面_底部缎带", BASE.replace("cover=full-block", "cover=ribbon-bottom")),
    ("s12_封面_纯文字极简", BASE.replace("cover=full-block", "cover=minimal-type")),
    ("s13_封面_图底压字", BASE.replace("cover=full-block", "cover=image-underlay")),
    ("s14_装饰_丰富", BASE.replace("decoration=standard", "decoration=rich")),
    ("s15_装饰_标题线", BASE.replace("decoration=standard", "decoration=heading-rule")),
    ("s16_装饰_图标点缀", BASE.replace("decoration=standard", "decoration=icon-accent")),
    ("s17_图排_上下分栏", BASE.replace("imageLayout=split-h", "imageLayout=split-v")),
    ("s18_图排_通栏横幅", BASE.replace("imageLayout=split-h", "imageLayout=banner")),
    ("s19_图排_侧注式", BASE.replace("imageLayout=split-h", "imageLayout=side-note")),
    ("s20_图排_图卡混排", BASE.replace("imageLayout=split-h", "imageLayout=card-mix")),
    ("s21_图比_高图比50", BASE.replace("imageRatio=mid", "imageRatio=high")),
    ("s22_图比_低图比10", BASE.replace("imageRatio=mid", "imageRatio=low")),
    ("s23_图规则_仅照片", BASE.replace("imageRule=hybrid", "imageRule=photo-only")),
    ("s24_图规则_仅图表", BASE.replace("imageRule=hybrid", "imageRule=chart-only")),
    ("s25_目录_无页码", BASE.replace("tocStyle=t1-jianyu-auto", "tocStyle=t3-qinghai-nopage")),
    ("s26_目录_两级紧凑", BASE.replace("tocStyle=t1-jianyu-auto", "tocStyle=t10-minimal-2level")),
    ("s27_页眉页脚_居中庄重", BASE.replace("headerFooter=hf1-classic-enterprise", "headerFooter=hf2-centered-solemn")),
    ("s28_页面_海口25", BASE.replace("pageSetup=p1-standard-a4", "pageSetup=p2-haikou-25")),
    ("s29_装饰_角点+双栏", BASE.replace("decoration=standard", "decoration=corner-dots").replace("preset=single-column", "preset=two-column")),
    ("s30_分隔页_章首色带", BASE.replace("decoration=standard", "decoration=section-band").replace("preset=single-column", "preset=divider")),
]

only = sys.argv[1:]
done, failed = [], []
for name, override in SAMPLE_DEFS:
    if only and name not in only:
        continue
    tmp = tempfile.TemporaryDirectory()
    try:
        ent = layout._builtin_preview_fixture(tmp.name)
        out_dir = ent / "项目级" / "预览项目" / "技术标" / "产出"
        export.cmd_tech_export(SimpleNamespace(
            root=tmp.name, enterprise="预览企业", project="预览项目",
            override=override, bid_mode="", out=str(out_dir), force=True))
        src = out_dir / "技术标_预览项目.docx"
        dst = OUT / ("%s.docx" % name)
        shutil.copyfile(str(src), str(dst))
        done.append(name)
        print("OK  %s" % name)
    except Exception as e:  # noqa: BLE001
        failed.append((name, str(e)[:200]))
        print("FAIL %s  %s" % (name, str(e)[:200]))
    finally:
        tmp.cleanup()
print("DONE=%d FAILED=%d" % (len(done), len(failed)))
if failed:
    for n, e in failed:
        print("  !! %s: %s" % (n, e))
