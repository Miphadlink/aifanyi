"""本地配置：优先读项目根目录 .env，其次环境变量。"""
from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
CACHE_DIR = DATA_DIR / "cache"
UPLOAD_DIR = DATA_DIR / "uploads"
VIDEO_OUT_DIR = DATA_DIR / "subtitles"

for d in (DATA_DIR, CACHE_DIR, UPLOAD_DIR, VIDEO_OUT_DIR):
    d.mkdir(parents=True, exist_ok=True)

load_dotenv(ROOT / ".env")

SETTINGS_FILE = DATA_DIR / "settings.json"

DEFAULT_SETTINGS = {
    "api_base": os.getenv("TRANSLATE_API_BASE", "https://api.openai.com/v1"),
    "api_key": os.getenv("TRANSLATE_API_KEY", ""),
    "model": os.getenv("TRANSLATE_MODEL", "gpt-4o-mini"),
    # 分场景模型；空则回退 model
    "text_model": os.getenv("TEXT_MODEL", ""),
    "image_model": os.getenv("IMAGE_MODEL", ""),
    "video_model": os.getenv("VIDEO_MODEL", "agnes-video-v2.0"),
    "game_model": os.getenv("GAME_MODEL", ""),
    "target_lang": "zh",
    "source_lang": "auto",
    "use_local": False,
    "local_model": os.getenv("LOCAL_MODEL", "qwen2.5:7b-instruct"),
    "game_sample_ms": 300,
}


def load_settings() -> dict:
    """读取设置，字段缺失时用默认值补齐。"""
    data = dict(DEFAULT_SETTINGS)
    if SETTINGS_FILE.exists():
        try:
            raw = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                data.update(raw)
        except (json.JSONDecodeError, OSError):
            # 配置损坏时不阻断启动，回退默认
            pass
    return data


def save_settings(payload: dict) -> dict:
    """合并写入设置并返回完整配置。"""
    current = load_settings()
    for key, value in payload.items():
        if value is not None and key in DEFAULT_SETTINGS:
            current[key] = value
    SETTINGS_FILE.write_text(
        json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return current
