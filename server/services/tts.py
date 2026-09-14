"""Edge TTS：按语言选音色，合成 mp3 到 data/tts。"""
from __future__ import annotations

import asyncio
import hashlib
import time
from pathlib import Path

from server.config import DATA_DIR

TTS_DIR = DATA_DIR / "tts"
TTS_DIR.mkdir(parents=True, exist_ok=True)

# 语言 → 默认 Edge 音色（神经网络中文/英/日/韩）
DEFAULT_VOICES = {
    "zh": "zh-CN-XiaoxiaoNeural",
    "en": "en-US-JennyNeural",
    "ja": "ja-JP-NanamiNeural",
    "ko": "ko-KR-SunHiNeural",
    "auto": "zh-CN-XiaoxiaoNeural",
}


def resolve_voice(lang: str, voice: str | None = None) -> str:
    if voice:
        return voice
    return DEFAULT_VOICES.get(lang or "zh", DEFAULT_VOICES["zh"])


def _cache_path(text: str, voice: str, rate: str) -> Path:
    key = hashlib.sha1(f"{voice}|{rate}|{text}".encode("utf-8")).hexdigest()[:20]
    return TTS_DIR / f"{key}.mp3"


async def synthesize(
    text: str,
    lang: str = "zh",
    voice: str | None = None,
    rate: str = "+0%",
) -> dict:
    """合成语音，返回本地 mp3 路径。相同文本会命中缓存。"""
    text = (text or "").strip()
    if not text:
        return {"error": "文本为空"}

    chosen = resolve_voice(lang, voice)
    out = _cache_path(text, chosen, rate)
    if out.exists() and out.stat().st_size > 0:
        return {"path": str(out), "voice": chosen, "cached": True}

    try:
        import edge_tts
    except Exception as exc:
        return {"error": f"edge-tts 未安装: {exc}"}

    started = time.perf_counter()
    try:
        communicate = edge_tts.Communicate(text, chosen, rate=rate)
        await communicate.save(str(out))
    except Exception as exc:
        return {"error": f"TTS 失败: {exc}"}

    if not out.exists() or out.stat().st_size == 0:
        return {"error": "TTS 未生成音频"}

    return {
        "path": str(out),
        "voice": chosen,
        "cached": False,
        "latency_ms": int((time.perf_counter() - started) * 1000),
    }


def synthesize_sync(
    text: str,
    lang: str = "zh",
    voice: str | None = None,
    rate: str = "+0%",
) -> dict:
    """同步包装，供视频流水线等非 async 场景调用。"""
    return asyncio.run(synthesize(text, lang, voice, rate))


async def list_voices() -> list[dict]:
    try:
        import edge_tts

        raw = await edge_tts.list_voices()
    except Exception as exc:
        return [{"error": str(exc)}]
    out = []
    for v in raw:
        out.append(
            {
                "short_name": v.get("ShortName"),
                "locale": v.get("Locale"),
                "gender": v.get("Gender"),
            }
        )
    return out
