"""视频流水线：探测媒体 → 抽音 → Whisper ASR → 翻译 → SRT/ASS。"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import shutil
import subprocess
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from server.config import ROOT, VIDEO_OUT_DIR, load_settings
from server.services.translator import translate_text

VIDEO_EXTS = {
    ".mp4", ".mkv", ".mov", ".avi", ".webm", ".flv", ".wmv", ".m4v",
    ".ts", ".m2ts", ".mts", ".vob", ".mpg", ".mpeg",
}
AUDIO_EXTS = {".mp3", ".wav", ".flac", ".aac", ".m4a", ".ogg"}

_LOCAL_BIN = ROOT / "tools" / "ffmpeg" / "bin"

# 国内默认走 HF 镜像，避免 faster-whisper 下模型超时
# 可用环境变量 HF_ENDPOINT=https://hf-mirror.com 覆盖
if not os.environ.get("HF_ENDPOINT"):
    os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")


def _frozen_ffmpeg_dir() -> Path | None:
    """打包版：exe 旁的 ffmpeg/ 目录。"""
    import sys

    if not getattr(sys, "frozen", False):
        return None
    cand = Path(sys.executable).resolve().parent / "ffmpeg"
    return cand if cand.is_dir() else None


def _find_exe(name: str) -> str | None:
    """按优先级找可执行文件：打包旁 ffmpeg → 项目 tools → PATH → imageio。"""
    frozen = _frozen_ffmpeg_dir()
    if frozen:
        p = frozen / f"{name}.exe"
        if p.exists():
            return str(p)
    local = _LOCAL_BIN / f"{name}.exe"
    if local.exists():
        return str(local)
    env_dir = os.getenv("FFMPEG_DIR")
    if env_dir:
        cand = Path(env_dir) / f"{name}.exe"
        if cand.exists():
            return str(cand)
    on_path = shutil.which(name)
    if on_path:
        return on_path
    if name == "ffmpeg":
        try:
            import imageio_ffmpeg

            return imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            return None
    return None


def get_ffmpeg() -> str | None:
    return _find_exe("ffmpeg")


def get_ffprobe() -> str | None:
    return _find_exe("ffprobe")


def ffmpeg_available() -> bool:
    """有 ffmpeg 即可用（ffprobe 可选，缺失时用 ffmpeg -i 解析）。"""
    return get_ffmpeg() is not None


def _run(cmd: list[str], timeout: int = 600) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def probe_media(path: str) -> dict:
    """探测流信息。优先 ffprobe，否则用 ffmpeg -i 解析 stderr。"""
    ffprobe = get_ffprobe()
    if ffprobe:
        proc = _run(
            [
                ffprobe, "-v", "error", "-print_format", "json",
                "-show_format", "-show_streams", path,
            ],
            timeout=60,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"无法读取媒体文件: {proc.stderr.strip()[:200]}")
        data = json.loads(proc.stdout or "{}")
        streams = data.get("streams") or []
        has_audio = any(s.get("codec_type") == "audio" for s in streams)
        has_subtitle = any(s.get("codec_type") == "subtitle" for s in streams)
        duration = float((data.get("format") or {}).get("duration") or 0)
        return {
            "has_audio": has_audio,
            "has_subtitle": has_subtitle,
            "duration": duration,
            "format_name": (data.get("format") or {}).get("format_name", ""),
        }

    ffmpeg = get_ffmpeg()
    if not ffmpeg:
        raise RuntimeError("未检测到 ffmpeg，请安装到 tools/ffmpeg/bin 或系统 PATH")
    proc = _run([ffmpeg, "-hide_banner", "-i", path], timeout=60)
    err = proc.stderr or ""
    if "Invalid data found" in err or "could not find codec parameters" in err.lower():
        # 仍可能有效，继续粗解析
        pass
    has_audio = bool(re.search(r"Stream #\d+:\d+.*Audio:", err))
    has_subtitle = bool(re.search(r"Stream #\d+:\d+.*Subtitle:", err))
    duration = 0.0
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", err)
    if m:
        h, mi, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
        duration = h * 3600 + mi * 60 + s
    if not has_audio and not has_subtitle and duration <= 0:
        raise RuntimeError(f"无法读取媒体文件: {err.strip()[:200]}")
    return {
        "has_audio": has_audio,
        "has_subtitle": has_subtitle,
        "duration": duration,
        "format_name": "",
    }


def extract_audio(video_path: str, wav_path: str) -> None:
    ffmpeg = get_ffmpeg()
    if not ffmpeg:
        raise RuntimeError("未检测到 ffmpeg")
    proc = _run(
        [
            ffmpeg, "-y", "-i", video_path,
            "-vn", "-ac", "1", "-ar", "16000",
            "-f", "wav", wav_path,
        ]
    )
    if proc.returncode != 0:
        raise RuntimeError(f"抽音轨失败: {proc.stderr.strip()[-300:]}")


def extract_subtitle_track(video_path: str, srt_path: str) -> bool:
    """尝试抽出第一条字幕轨为 srt；失败返回 False。"""
    ffmpeg = get_ffmpeg()
    if not ffmpeg:
        return False
    proc = _run(
        [
            ffmpeg, "-y", "-i", video_path,
            "-map", "0:s:0", "-c:s", "srt", srt_path,
        ]
    )
    return proc.returncode == 0 and Path(srt_path).exists()


def whisper_transcribe(wav_path: str, language: str | None = None) -> list[dict]:
    """faster-whisper 转写，返回 [{start, end, text}]。"""
    # 确保加载前 HF_ENDPOINT 已生效
    os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
    try:
        from faster_whisper import WhisperModel
    except Exception as exc:
        raise RuntimeError(f"faster-whisper 未安装: {exc}") from exc

    settings = load_settings()
    model_name = os.getenv("WHISPER_MODEL", "small")
    # 默认优先 GPU；缺 cublas 等库时自动回退 CPU，不依赖用户改显卡设置
    prefer_gpu = os.getenv("WHISPER_DEVICE", "auto").lower()
    model = None
    last_err: Exception | None = None
    if prefer_gpu in ("auto", "cuda"):
        try:
            model = WhisperModel(model_name, device="cuda", compute_type="float16")
        except Exception as exc:
            last_err = exc
            model = None
    if model is None:
        try:
            model = WhisperModel(model_name, device="cpu", compute_type="int8")
        except Exception as exc:
            raise RuntimeError(
                f"Whisper 模型加载失败: {exc}"
                + (f"（GPU 失败原因: {last_err}）" if last_err else "")
            ) from exc

    lang = None if not language or language == "auto" else language
    try:
        segments, _info = model.transcribe(wav_path, language=lang, vad_filter=True)
        result = []
        for seg in segments:
            text = (seg.text or "").strip()
            if not text:
                continue
            result.append({"start": float(seg.start), "end": float(seg.end), "text": text})
        return result
    except Exception as exc:
        # 若 GPU 在推理阶段才报 cublas 等错误，再强制 CPU 重试一次
        msg = str(exc)
        if "cublas" in msg.lower() or "cuda" in msg.lower():
            model = WhisperModel(model_name, device="cpu", compute_type="int8")
            segments, _info = model.transcribe(wav_path, language=lang, vad_filter=True)
            result = []
            for seg in segments:
                text = (seg.text or "").strip()
                if not text:
                    continue
                result.append({"start": float(seg.start), "end": float(seg.end), "text": text})
            return result
        raise


def parse_srt(srt_path: str) -> list[dict]:
    """简易 SRT 解析：忽略空块。"""
    raw = Path(srt_path).read_text(encoding="utf-8", errors="replace")
    blocks = re.split(r"\n\s*\n", raw.strip())
    items = []
    for block in blocks:
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        if len(lines) < 2:
            continue
        time_line = lines[1] if "-->" in lines[1] else (lines[0] if "-->" in lines[0] else "")
        if "-->" not in time_line:
            continue
        start_s, end_s = [p.strip() for p in time_line.split("-->")]
        text = "\n".join(lines[2:] if "-->" in lines[1] else lines[1:])
        items.append(
            {
                "start": _srt_time_to_sec(start_s),
                "end": _srt_time_to_sec(end_s.split()[0]),
                "text": text.replace("\n", " ").strip(),
            }
        )
    return items


def _srt_time_to_sec(t: str) -> float:
    # 00:00:01,000 或 00:00:01.000
    t = t.replace(",", ".")
    parts = t.split(":")
    if len(parts) != 3:
        return 0.0
    h, m = int(parts[0]), int(parts[1])
    s = float(parts[2])
    return h * 3600 + m * 60 + s


def _sec_to_srt_time(sec: float) -> str:
    if sec < 0:
        sec = 0
    ms = int(round(sec * 1000))
    h, ms = divmod(ms, 3600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write_srt(segments: list[dict], path: str) -> None:
    lines = []
    for i, seg in enumerate(segments, 1):
        lines.append(str(i))
        lines.append(f"{_sec_to_srt_time(seg['start'])} --> {_sec_to_srt_time(seg['end'])}")
        lines.append(seg["text"])
        lines.append("")
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def write_ass(segments: list[dict], path: str) -> None:
    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Microsoft YaHei,48,&H00FFFFFF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,2,1,2,30,30,40,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    def ass_time(sec: float) -> str:
        cs = int(round(sec * 100))
        h, cs = divmod(cs, 360000)
        m, cs = divmod(cs, 6000)
        s, cs = divmod(cs, 100)
        return f"{h:d}:{m:02d}:{s:02d}.{cs:02d}"

    events = []
    for seg in segments:
        text = seg["text"].replace("\n", "\\N")
        events.append(
            f"Dialogue: 0,{ass_time(seg['start'])},{ass_time(seg['end'])},Default,,0,0,0,,{text}"
        )
    Path(path).write_text(header + "\n".join(events) + "\n", encoding="utf-8")


async def translate_segments(
    segments: list[dict],
    source_lang: str,
    target_lang: str,
    on_progress=None,
) -> list[dict]:
    out = []
    total = max(len(segments), 1)
    for i, seg in enumerate(segments):
        res = await translate_text(seg["text"], source_lang, target_lang, scene="video")
        text = res.get("text") or seg["text"]
        out.append({**seg, "text": text})
        if on_progress:
            await on_progress(i + 1, total)
    return out


def file_hash(path: str) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


@dataclass
class VideoTasks:
    tasks: dict[str, dict] = field(default_factory=dict)

    def create(self, path: str, source_lang: str, target_lang: str,
               use_existing_subs: bool, embed_sub: bool, tts: bool = False) -> dict:
        task_id = uuid.uuid4().hex[:12]
        record = {
            "task_id": task_id,
            "status": "queued",
            "progress": 0,
            "message": "排队中",
            "path": path,
            "source_lang": source_lang,
            "target_lang": target_lang,
            "use_existing_subs": use_existing_subs,
            "embed_sub": embed_sub,
            "tts": tts,
            "output_srt": None,
            "output_ass": None,
            "output_audio": None,
            "output_dubbed": None,
            "error": None,
        }
        self.tasks[task_id] = record
        return record

    def get(self, task_id: str) -> dict | None:
        return self.tasks.get(task_id)

    async def run(self, task_id: str) -> None:
        rec = self.tasks[task_id]
        rec["status"] = "running"
        rec["progress"] = 5
        rec["message"] = "探测媒体信息"
        path = rec["path"]
        try:
            info = probe_media(path)
            if not info["has_audio"] and not info["has_subtitle"]:
                raise RuntimeError("文件无音轨且无字幕轨，无法翻译")

            base = Path(path)
            stem = base.stem
            work = VIDEO_OUT_DIR / f"{stem}_{task_id}"
            work.mkdir(parents=True, exist_ok=True)
            wav = str(work / "audio.wav")
            raw_srt = str(work / "raw.srt")

            segments: list[dict] = []
            if rec["use_existing_subs"] and info["has_subtitle"]:
                rec["message"] = "抽取已有字幕轨"
                rec["progress"] = 20
                if extract_subtitle_track(path, raw_srt):
                    segments = parse_srt(raw_srt)
            if not segments:
                if not info["has_audio"]:
                    raise RuntimeError("无音轨且未能抽取字幕")
                rec["message"] = "抽取音轨"
                rec["progress"] = 25
                extract_audio(path, wav)
                rec["message"] = "语音识别中"
                rec["progress"] = 40
                lang = rec["source_lang"] if rec["source_lang"] != "auto" else None
                segments = await asyncio.to_thread(whisper_transcribe, wav, lang)

            if not segments:
                raise RuntimeError("未识别到有效语音/字幕内容")

            rec["message"] = "翻译字幕"
            rec["progress"] = 55

            async def on_progress(done: int, total: int) -> None:
                ratio = done / total
                rec["progress"] = 55 + ratio * 35
                rec["message"] = f"翻译 {done}/{total}"

            translated = await translate_segments(
                segments, rec["source_lang"], rec["target_lang"], on_progress
            )

            out_srt = str(work / f"{stem}.{rec['target_lang']}.srt")
            out_ass = str(work / f"{stem}.{rec['target_lang']}.ass")
            write_srt(translated, out_srt)
            write_ass(translated, out_ass)
            rec["output_srt"] = out_srt
            rec["output_ass"] = out_ass

            if rec["embed_sub"]:
                rec["message"] = "嵌入软字幕"
                rec["progress"] = 95
                embedded = str(work / f"{stem}.subbed.mp4")
                ok = await asyncio.to_thread(_embed_sub, path, out_srt, embedded)
                if ok:
                    rec["output_embedded"] = embedded

            if rec.get("tts"):
                rec["message"] = "生成译文配音"
                rec["progress"] = 80
                audio_path = str(work / f"{stem}.{rec['target_lang']}.tts.mp3")
                dubbed_path = str(work / f"{stem}.dubbed.mp4")
                audio_ok = await asyncio.to_thread(
                    _build_tts_track, translated, rec["target_lang"], audio_path, work
                )
                if audio_ok:
                    rec["output_audio"] = audio_path
                    rec["message"] = "合成配音视频"
                    rec["progress"] = 92
                    if await asyncio.to_thread(_mux_dub, path, audio_path, dubbed_path):
                        rec["output_dubbed"] = dubbed_path

            rec["status"] = "done"
            rec["progress"] = 100
            rec["message"] = "完成"
        except Exception as exc:
            rec["status"] = "failed"
            rec["error"] = str(exc)
            rec["message"] = f"失败: {exc}"


def _embed_sub(video_path: str, srt_path: str, out_path: str) -> bool:
    ffmpeg = get_ffmpeg()
    if not ffmpeg:
        return False
    proc = _run(
        [
            ffmpeg, "-y", "-i", video_path, "-i", srt_path,
            "-c", "copy", "-c:s", "mov_text",
            "-metadata:s:s:0", "language=chi", out_path,
        ]
    )
    return proc.returncode == 0


def _build_tts_track(
    segments: list[dict],
    lang: str,
    out_mp3: str,
    work_dir: Path,
) -> bool:
    """按时间轴拼 TTS 片段：先合成每段 mp3，再按 start 偏移拼接。"""
    from server.services.tts import synthesize_sync

    ffmpeg = get_ffmpeg()
    if not ffmpeg:
        return False

    parts: list[tuple[float, Path]] = []
    for i, seg in enumerate(segments):
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        res = synthesize_sync(text, lang=lang)
        if res.get("error") or not res.get("path"):
            continue
        parts.append((float(seg.get("start") or 0), Path(res["path"])))

    if not parts:
        return False

    # 用 adelay + amix 按时间轴铺到整轨；段落多时分批 mix 防参数过长
    filter_inputs: list[str] = []
    cmd = [ffmpeg, "-y"]
    for idx, (_start, mp3) in enumerate(parts):
        cmd += ["-i", str(mp3)]
        delay_ms = max(int(_start * 1000), 0)
        filter_inputs.append(
            f"[{idx}:a]aresample=24000,adelay={delay_ms}|{delay_ms}[a{idx}]"
        )
    mix_in = "".join(f"[a{i}]" for i in range(len(parts)))
    filter_graph = ";".join(filter_inputs) + f";{mix_in}amix=inputs={len(parts)}:duration=longest:dropout_transition=0[out]"
    cmd += [
        "-filter_complex", filter_graph,
        "-map", "[out]",
        "-c:a", "libmp3lame", "-q:a", "4",
        out_mp3,
    ]
    proc = _run(cmd, timeout=900)
    return proc.returncode == 0 and Path(out_mp3).exists()


def _mux_dub(video_path: str, audio_path: str, out_path: str) -> bool:
    """原视频画面 + 译文音轨，替换原音。"""
    ffmpeg = get_ffmpeg()
    if not ffmpeg:
        return False
    proc = _run(
        [
            ffmpeg, "-y", "-i", video_path, "-i", audio_path,
            "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "copy", "-c:a", "aac", "-shortest",
            out_path,
        ]
    )
    return proc.returncode == 0 and Path(out_path).exists()


video_tasks = VideoTasks()
