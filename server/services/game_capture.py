"""游戏窗口捕获与实时 OCR 翻译。"""
from __future__ import annotations

import asyncio
import time
from typing import Callable

import numpy as np
from PIL import Image

from server.config import load_settings
from server.services import game_launcher
from server.services.ocr import merge_boxes, ocr_image
from server.services.translator import translate_text


def capture_region(rect: dict) -> Image.Image | None:
    """按屏幕矩形截屏。"""
    try:
        import mss

        with mss.mss() as sct:
            mon = {
                "left": int(rect["x"]),
                "top": int(rect["y"]),
                "width": max(int(rect["w"]), 1),
                "height": max(int(rect["h"]), 1),
            }
            shot = sct.grab(mon)
            img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BXT")
            return img.convert("RGB")
    except Exception:
        return None


def _frame_diff_ratio(prev: np.ndarray | None, curr: np.ndarray) -> float:
    if prev is None or prev.shape != curr.shape:
        return 1.0
    # 缩小后再比，降低开销
    small_prev = prev[::8, ::8]
    small_curr = curr[::8, ::8]
    diff = np.mean(np.abs(small_prev.astype(np.int16) - small_curr.astype(np.int16)))
    return float(diff / 255.0)


class GameCaptureLoop:
    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task] = {}
        self._cache: dict[str, str] = {}

    def start(self, session_id: str) -> None:
        if session_id in self._tasks:
            return
        session = game_launcher.SESSIONS.get(session_id)
        if not session:
            raise KeyError("会话不存在")
        session.capture_enabled = True
        self._tasks[session_id] = asyncio.create_task(self._loop(session_id))

    def stop(self, session_id: str) -> None:
        session = game_launcher.SESSIONS.get(session_id)
        if session:
            session.capture_enabled = False
        task = self._tasks.pop(session_id, None)
        if task:
            task.cancel()

    async def _loop(self, session_id: str) -> None:
        session = game_launcher.SESSIONS[session_id]
        prev_gray: np.ndarray | None = None
        while session.capture_enabled and session.status == "running":
            settings = load_settings()
            interval = max(int(settings.get("game_sample_ms") or 300), 150)
            rect = game_launcher.get_window_rect(session)
            if not rect or rect["w"] < 80 or rect["h"] < 60:
                await asyncio.sleep(interval / 1000)
                continue

            img = await asyncio.to_thread(capture_region, rect)
            if img is None:
                await asyncio.sleep(interval / 1000)
                continue

            arr = np.asarray(img.convert("L"))
            ratio = _frame_diff_ratio(prev_gray, arr)
            prev_gray = arr
            # 画面几乎没变就跳过 OCR
            if ratio < 0.012:
                await asyncio.sleep(interval / 1000)
                continue

            try:
                boxes = await asyncio.to_thread(ocr_image, self._save_tmp(img, session_id))
            except Exception:
                session.lines = []
                await asyncio.sleep(interval / 1000)
                continue

            merged = merge_boxes(boxes)
            if not merged:
                session.lines = []
                await asyncio.sleep(interval / 1000)
                continue

            lines: list[dict] = []
            for item in merged[:12]:
                original = item["text"]
                if len(original) < 2:
                    continue
                cached = self._cache.get(original)
                if cached:
                    translated = cached
                else:
                    res = await translate_text(
                        original,
                        "auto",
                        settings.get("target_lang", "zh"),
                        scene="game",
                    )
                    translated = res.get("text") or original
                    self._cache[original] = translated
                    # 简单上限，防止无限膨胀
                    if len(self._cache) > 800:
                        self._cache.clear()
                r = item["rect"]
                lines.append(
                    {
                        "x": r["x"] - rect["x"],
                        "y": r["y"] - rect["y"],
                        "w": r["w"],
                        "h": r["h"],
                        "text": translated,
                        "original": original,
                    }
                )
            session.lines = lines
            await asyncio.sleep(interval / 1000)

    def _save_tmp(self, img: Image.Image, session_id: str) -> str:
        from server.config import CACHE_DIR

        path = CACHE_DIR / f"game_{session_id}.png"
        img.save(path)
        return str(path)


capture_loop = GameCaptureLoop()
