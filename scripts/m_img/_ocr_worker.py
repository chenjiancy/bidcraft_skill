# -*- coding: utf-8 -*-
"""img-audit 的 OCR 工作器 —— 由 OCR 专用 venv（BIDCRAFT_OCR_PY）的 python 执行。

用法：python _ocr_worker.py <图片绝对路径>
输出：stdout 一行 JSON {"texts": [...], "error": null | "..."}
说明：paddleocr 3.x 推理在部分 Windows 机需关闭 oneDNN（FLAGS_use_mkldnn=0），
本工作器已在进程内设置；首次运行会下载/加载模型（较慢，超时按 180s 计）。
"""
import os
import sys
import json

os.environ.setdefault("FLAGS_use_mkldnn", "0")


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"texts": [], "error": "missing image path"}, ensure_ascii=False))
        return 1
    img = sys.argv[1]
    if not os.path.isfile(img):
        print(json.dumps({"texts": [], "error": "image not found: %s" % img}, ensure_ascii=False))
        return 1
    try:
        from paddleocr import PaddleOCR
        ocr = PaddleOCR(use_textline_orientation=True, lang="ch", enable_mkldnn=False)
        result = ocr.predict(img)
        texts = []
        for r in result:
            rows = r.get("rec_texts") if isinstance(r, dict) else getattr(r, "rec_texts", None)
            for t in rows or []:
                s = str(t).strip()
                if s:
                    texts.append(s)
        print(json.dumps({"texts": texts, "error": None}, ensure_ascii=False))
        return 0
    except Exception as e:  # 引擎/模型异常 → 如实上报，不假装检查
        print(json.dumps({"texts": [], "error": repr(e)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    sys.exit(main())
