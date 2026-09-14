"""FastAPI 入口：文字 / 图片 / 视频 / 游戏翻译 API。"""
from __future__ import annotations

import asyncio
import base64
import io
import os
import platform
import shutil
import sys
import uuid
from pathlib import Path

# Whisper 等从 HuggingFace 拉模型；国内优先镜像，避免 ConnectTimeout
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
# 新版 HF xet 下载在国内/镜像下易 401，禁用走传统下载
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from server.config import UPLOAD_DIR, load_settings, save_settings
from server.services import game_launcher
from server.services.game_capture import capture_loop
from server.services.ocr import ocr_image
from server.services.translator import (
    list_remote_models,
    translate_text,
    translate_text_stream,
)
from server.services.tts import list_voices, synthesize
from server.services.video_pipeline import (
    AUDIO_EXTS,
    VIDEO_EXTS,
    ffmpeg_available,
    get_ffmpeg,
    video_tasks,
)

app = FastAPI(title="AI 智能翻译", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class TextBody(BaseModel):
    text: str
    source_lang: str = "auto"
    target_lang: str = "zh"


class SettingsBody(BaseModel):
    api_base: str | None = None
    api_key: str | None = None
    model: str | None = None
    text_model: str | None = None
    image_model: str | None = None
    video_model: str | None = None
    game_model: str | None = None
    target_lang: str | None = None
    source_lang: str | None = None
    use_local: bool | None = None
    local_model: str | None = None
    game_sample_ms: int | None = None


class ModelsFetchBody(BaseModel):
    api_base: str | None = None
    api_key: str | None = None


class ImageBody(BaseModel):
    image_base64: str
    source_lang: str = "auto"
    target_lang: str = "zh"
    overlay: bool = False


class GamePathBody(BaseModel):
    path: str


class ConfirmBody(BaseModel):
    path: str


class CaptureBody(BaseModel):
    session_id: str
    enabled: bool


class TtsBody(BaseModel):
    text: str
    lang: str = "zh"
    voice: str | None = None
    rate: str = "+0%"


class VideoBody(BaseModel):
    path: str
    source_lang: str = "auto"
    target_lang: str = "zh"
    use_existing_subs: bool = True
    embed_sub: bool = False
    tts: bool = False


def _gpu_name() -> str:
    try:
        import subprocess

        proc = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        name = (proc.stdout or "").strip().splitlines()
        return name[0] if name else "未检测到 NVIDIA GPU"
    except Exception:
        return "未检测到 NVIDIA GPU"


@app.get("/health")
def health() -> dict:
    return {
        "ok": True,
        "python": sys.version.split()[0],
        "ffmpeg": ffmpeg_available(),
        "ffmpeg_path": get_ffmpeg(),
        "gpu": _gpu_name(),
        "platform": platform.platform(),
    }


@app.get("/settings")
def get_settings_api() -> dict:
    return load_settings()


@app.post("/settings")
def post_settings(body: SettingsBody) -> dict:
    payload = {k: v for k, v in body.model_dump().items() if v is not None}
    return save_settings(payload)


@app.post("/models")
async def api_list_models(body: ModelsFetchBody | None = None) -> dict:
    """按当前/传入的 Base+Key 拉取可用模型列表。"""
    api_base = body.api_base if body else None
    api_key = body.api_key if body else None
    result = await list_remote_models(api_base, api_key)
    if result.get("error"):
        raise HTTPException(status_code=502, detail=result["error"])
    return result


@app.post("/translate/text")
async def api_translate_text(body: TextBody) -> dict:
    if not body.text.strip():
        raise HTTPException(status_code=400, detail="文本为空")
    result = await translate_text(
        body.text, body.source_lang, body.target_lang, scene="text"
    )
    if result.get("error") and not result.get("text"):
        raise HTTPException(status_code=502, detail=result["error"])
    return result


@app.post("/translate/text/stream")
async def api_translate_text_stream(body: TextBody):
    if not body.text.strip():
        raise HTTPException(status_code=400, detail="文本为空")

    async def gen():
        async for chunk in translate_text_stream(
            body.text, body.source_lang, body.target_lang, scene="text"
        ):
            import json

            yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n"
        yield "data: [DONE]\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.post("/tts")
async def api_tts(body: TtsBody) -> dict:
    result = await synthesize(body.text, body.lang, body.voice, body.rate)
    if result.get("error"):
        raise HTTPException(status_code=502, detail=result["error"])
    return result


@app.get("/tts/audio")
async def api_tts_audio(path: str):
    """按服务端返回的 path 播放音频（仅允许 data/tts 目录）。"""
    from server.services.tts import TTS_DIR

    p = Path(path).resolve()
    root = TTS_DIR.resolve()
    if not str(p).startswith(str(root)) or not p.is_file():
        raise HTTPException(status_code=400, detail="非法音频路径")
    return FileResponse(str(p), media_type="audio/mpeg", filename=p.name)


@app.get("/tts/voices")
async def api_tts_voices() -> dict:
    voices = await list_voices()
    return {"voices": voices}


@app.post("/translate/image")
async def api_translate_image(body: ImageBody) -> dict:
    try:
        raw = base64.b64decode(body.image_base64)
    except Exception:
        raise HTTPException(status_code=400, detail="图片 base64 无效")

    tmp_dir = UPLOAD_DIR / "images"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    img_path = tmp_dir / f"{uuid.uuid4().hex}.png"
    img_path.write_bytes(raw)

    try:
        boxes = await asyncio.to_thread(ocr_image, str(img_path))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    result_boxes = []
    for b in boxes:
        res = await translate_text(
            b["text"], body.source_lang, body.target_lang, scene="image"
        )
        result_boxes.append(
            {
                "box": b["box"],
                "text": b["text"],
                "translation": res.get("text") or "",
            }
        )

    overlay_url = None
    if body.overlay and result_boxes:
        overlay_url = await asyncio.to_thread(
            _draw_overlay, str(img_path), result_boxes
        )

    joined_src = " ".join(b["text"] for b in result_boxes)
    joined_tgt = " ".join((b.get("translation") or "") for b in result_boxes)
    return {
        "source": joined_src,
        "target": joined_tgt,
        "boxes": result_boxes,
        "overlay_data_url": overlay_url,
    }


def _draw_overlay(image_path: str, boxes: list[dict]) -> str:
    """把译文画在半透明底条上，返回 data URL。"""
    from PIL import Image, ImageDraw, ImageFont

    img = Image.open(image_path).convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    try:
        font = ImageFont.truetype("msyh.ttc", 18)
    except Exception:
        font = ImageFont.load_default()

    for item in boxes:
        pts = item.get("box") or []
        if len(pts) < 2:
            continue
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
        draw.rectangle([x0, y0, x1, y1], fill=(10, 14, 20, 200))
        text = item.get("translation") or item.get("text") or ""
        draw.text((x0 + 4, y0 + 2), text, fill=(245, 248, 252, 255), font=font)

    composed = Image.alpha_composite(img, overlay).convert("RGB")
    buf = io.BytesIO()
    composed.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}"


@app.post("/translate/video/upload")
async def api_video_upload(file: UploadFile = File(...)) -> dict:
    suffix = Path(file.filename or "video.bin").suffix.lower()
    dest = UPLOAD_DIR / f"{uuid.uuid4().hex}{suffix}"
    data = await file.read()
    dest.write_bytes(data)
    return {"path": str(dest), "name": file.filename}


@app.post("/translate/video")
async def api_video_start(body: VideoBody) -> dict:
    path = Path(body.path)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"文件不存在: {body.path}")
    ext = path.suffix.lower()
    if ext not in VIDEO_EXTS and ext not in AUDIO_EXTS:
        raise HTTPException(status_code=400, detail=f"不支持的扩展名: {ext}")
    if not ffmpeg_available():
        raise HTTPException(status_code=500, detail="未安装 ffmpeg，无法处理视频")

    rec = video_tasks.create(
        str(path),
        body.source_lang,
        body.target_lang,
        body.use_existing_subs,
        body.embed_sub,
        body.tts,
    )
    asyncio.create_task(video_tasks.run(rec["task_id"]))
    return _public_task(rec)


@app.get("/translate/video/{task_id}")
async def api_video_status(task_id: str) -> dict:
    rec = video_tasks.get(task_id)
    if not rec:
        raise HTTPException(status_code=404, detail="任务不存在")
    return _public_task(rec)


def _public_task(rec: dict) -> dict:
    return {
        "task_id": rec["task_id"],
        "status": rec["status"],
        "progress": rec["progress"],
        "message": rec["message"],
        "output_srt": rec.get("output_srt"),
        "output_ass": rec.get("output_ass"),
        "output_audio": rec.get("output_audio"),
        "output_dubbed": rec.get("output_dubbed"),
        "error": rec.get("error"),
    }


@app.post("/game/start")
def api_game_start(body: GamePathBody) -> dict:
    path = body.path.strip().strip('"')
    if not path:
        raise HTTPException(status_code=400, detail="路径为空")
    if not Path(path).exists():
        raise HTTPException(status_code=404, detail=f"路径不存在: {path}")

    candidates = game_launcher.detect_candidates(path)
    if not candidates:
        raise HTTPException(status_code=400, detail="未找到可启动的游戏程序")
    if len(candidates) > 1 and Path(path).is_dir():
        return {"need_confirm": True, "candidates": candidates}

    session = game_launcher.launch_session(candidates[0]["path"])
    return _public_session(session)


@app.post("/game/confirm")
def api_game_confirm(body: ConfirmBody) -> dict:
    session = game_launcher.launch_session(body.path)
    return _public_session(session)


@app.post("/game/{session_id}/stop")
def api_game_stop(session_id: str) -> dict:
    capture_loop.stop(session_id)
    ok = game_launcher.stop_session(session_id)
    return {"ok": ok}


@app.post("/game/capture")
def api_game_capture(body: CaptureBody) -> dict:
    session = game_launcher.SESSIONS.get(body.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    if body.enabled:
        capture_loop.start(body.session_id)
    else:
        capture_loop.stop(body.session_id)
    return {"ok": True}


@app.get("/game/{session_id}/status")
def api_game_status(session_id: str) -> dict:
    session = game_launcher.SESSIONS.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    # 窗口可能延迟出现
    if session.hwnd is None:
        game_launcher.bind_window(session)
    return _public_session(session)


def _public_session(session: game_launcher.GameSession) -> dict:
    return {
        "session_id": session.session_id,
        "game_name": session.game_name,
        "pid": session.pid,
        "window_title": session.window_title,
        "engine": session.engine,
        "status": session.status,
        "lines": session.lines,
    }


@app.get("/")
def index() -> dict:
    return {"name": "ai-translator", "docs": "/docs"}
