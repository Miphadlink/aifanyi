"""OCR 服务：RapidOCR，未安装时返回明确错误。"""
from __future__ import annotations

from typing import Any

_ocr_engine: Any = None
_ocr_error: str | None = None


def _get_engine():
    global _ocr_engine, _ocr_error
    if _ocr_engine is not None:
        return _ocr_engine
    if _ocr_error is not None:
        raise RuntimeError(_ocr_error)
    try:
        from rapidocr_onnxruntime import RapidOCR

        _ocr_engine = RapidOCR()
        return _ocr_engine
    except Exception as exc:
        _ocr_error = f"OCR 引擎不可用: {exc}。请安装 rapidocr-onnxruntime"
        raise RuntimeError(_ocr_error) from exc


def ocr_image(image_path: str) -> list[dict]:
    """返回 [{box: [[x,y]...], text: str}]。"""
    engine = _get_engine()
    result, _elapse = engine(image_path)
    boxes: list[dict] = []
    if not result:
        return boxes
    for item in result:
        # RapidOCR 单条: [box, text, score]
        box, text, score = item[0], item[1], float(item[2] if len(item) > 2 else 1.0)
        if score < 0.5:
            continue
        pts = [[float(p[0]), float(p[1])] for p in box]
        boxes.append({"box": pts, "text": str(text)})
    return boxes


def merge_boxes(boxes: list[dict], y_tol: float = 12.0) -> list[dict]:
    """把同一水平附近的短行合并成对话块，降低调用次数。"""
    if not boxes:
        return []
    items = sorted(boxes, key=lambda b: (min(p[1] for p in b["box"]), min(p[0] for p in b["box"])))
    merged: list[dict] = []
    for item in items:
        ys = [p[1] for p in item["box"]]
        xs = [p[0] for p in item["box"]]
        top, bottom, left, right = min(ys), max(ys), min(xs), max(xs)
        if merged:
            last = merged[-1]
            if abs(last["bottom"] - top) < y_tol and left < last["right"] + 40:
                last["texts"].append(item["text"])
                last["boxes"].extend(item["box"])
                last["left"] = min(last["left"], left)
                last["right"] = max(last["right"], right)
                last["top"] = min(last["top"], top)
                last["bottom"] = max(last["bottom"], bottom)
                continue
        merged.append(
            {
                "texts": [item["text"]],
                "boxes": list(item["box"]),
                "left": left,
                "right": right,
                "top": top,
                "bottom": bottom,
            }
        )
    result = []
    for m in merged:
        result.append(
            {
                "box": m["boxes"],
                "text": " ".join(m["texts"]),
                "rect": {
                    "x": m["left"],
                    "y": m["top"],
                    "w": m["right"] - m["left"],
                    "h": m["bottom"] - m["top"],
                },
            }
        )
    return result
