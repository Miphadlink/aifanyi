"""翻译引擎：优先云端 OpenAI 兼容 API，可选 Ollama 本地。"""
from __future__ import annotations

import time
from typing import AsyncIterator

import httpx

from server.config import load_settings

LANG_NAME = {
    "auto": "自动检测",
    "zh": "中文",
    "en": "English",
    "ja": "日本語",
    "ko": "한국어",
}


def _lang_label(code: str) -> str:
    return LANG_NAME.get(code, code)


def _build_messages(text: str, source_lang: str, target_lang: str) -> list[dict]:
    src = _lang_label(source_lang)
    tgt = _lang_label(target_lang)
    system = (
        "你是专业翻译引擎。只输出译文，不要解释。"
        "保留段落结构；专有名词按目标语言习惯处理；不要加引号包裹全文。"
    )
    user = f"将下列内容从{src}翻译成{tgt}：\n\n{text}"
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def _endpoint(settings: dict) -> tuple[str, dict, str]:
    """返回 (base_url, headers, model)。本地走 Ollama OpenAI 兼容口。"""
    if settings.get("use_local"):
        return (
            "http://127.0.0.1:11434/v1",
            {"Authorization": "Bearer ollama"},
            settings.get("local_model") or "qwen2.5:7b-instruct",
        )
    base = (settings.get("api_base") or "").rstrip("/")
    key = settings.get("api_key") or ""
    if not key:
        # 云端必须有 Key，否则立刻失败，避免长时间挂起
        return "", {}, settings.get("model") or "gpt-4o-mini"
    headers = {"Authorization": f"Bearer {key}"}
    return base, headers, settings.get("model") or "gpt-4o-mini"


def resolve_model(settings: dict, scene: str | None = None) -> str:
    """按场景取模型：text/image/video/game，空则用全局 model。"""
    if scene:
        specific = settings.get(f"{scene}_model") or ""
        if specific:
            return specific
    if settings.get("use_local"):
        return settings.get("local_model") or "qwen2.5:7b-instruct"
    return settings.get("model") or "gpt-4o-mini"


async def translate_text(
    text: str,
    source_lang: str = "auto",
    target_lang: str = "zh",
    scene: str | None = None,
    model: str | None = None,
) -> dict:
    """非流式整段翻译。scene: text|image|video|game；model 可强制覆盖。"""
    settings = load_settings()
    base, headers, default_model = _endpoint(settings)
    chosen = model or resolve_model(settings, scene)
    if not base:
        return {
            "text": text,
            "engine": "passthrough",
            "latency_ms": 0,
            "error": "未配置 API Key，请到设置页填写（或启用本地 Ollama）",
        }
    messages = _build_messages(text, source_lang, target_lang)
    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{base}/chat/completions",
                headers=headers,
                json={
                    "model": chosen,
                    "messages": messages,
                    "temperature": 0.2,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            translated = data["choices"][0]["message"]["content"].strip()
    except Exception as exc:  # 网络/鉴权/解析统一抛给上层可读信息
        return {
            "text": "",
            "engine": chosen,
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "error": f"翻译失败: {exc}",
        }
    return {
        "text": translated,
        "engine": chosen,
        "latency_ms": int((time.perf_counter() - started) * 1000),
        "source_lang": source_lang,
        "target_lang": target_lang,
    }


async def translate_text_stream(
    text: str,
    source_lang: str = "auto",
    target_lang: str = "zh",
    scene: str | None = None,
    model: str | None = None,
) -> AsyncIterator[dict]:
    """流式翻译：yield {"type":"delta"|"done", ...}。"""
    settings = load_settings()
    base, headers, _default_model = _endpoint(settings)
    chosen = model or resolve_model(settings, scene)
    if not base:
        yield {
            "type": "done",
            "text": "",
            "engine": "passthrough",
            "latency_ms": 0,
            "error": "未配置 API Key，请到设置页填写（或启用本地 Ollama）",
        }
        return

    messages = _build_messages(text, source_lang, target_lang)
    started = time.perf_counter()
    parts: list[str] = []
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream(
                "POST",
                f"{base}/chat/completions",
                headers=headers,
                json={
                    "model": chosen,
                    "messages": messages,
                    "temperature": 0.2,
                    "stream": True,
                },
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        break
                    # 解析 OpenAI 兼容 delta
                    try:
                        import json

                        chunk = json.loads(payload)
                        delta = chunk["choices"][0].get("delta") or {}
                        piece = delta.get("content") or ""
                    except Exception:
                        continue
                    if piece:
                        parts.append(piece)
                        yield {"type": "delta", "text": piece}
    except Exception as exc:
        yield {
            "type": "done",
            "text": "".join(parts),
            "engine": chosen,
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "error": f"翻译失败: {exc}",
        }
        return

    yield {
        "type": "done",
        "text": "".join(parts),
        "engine": chosen,
        "latency_ms": int((time.perf_counter() - started) * 1000),
        "source_lang": source_lang,
        "target_lang": target_lang,
    }


async def list_remote_models(api_base: str | None = None, api_key: str | None = None) -> dict:
    """调用 OpenAI 兼容 GET /models 拉取模型列表。"""
    settings = load_settings()
    base = (api_base or settings.get("api_base") or "").rstrip("/")
    key = api_key if api_key is not None else (settings.get("api_key") or "")
    if not base:
        return {"error": "未配置 API Base"}
    if not key and not settings.get("use_local"):
        return {"error": "未配置 API Key"}

    # /v1/chat... 的 base，models 通常是 {base}/models
    url = f"{base}/models"
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        return {"error": f"获取模型列表失败: {exc}"}

    raw = data.get("data") if isinstance(data, dict) else data
    models: list[str] = []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, str):
                models.append(item)
            elif isinstance(item, dict):
                mid = item.get("id") or item.get("name")
                if mid:
                    models.append(str(mid))
    models = sorted(set(models))
    return {"models": models}
