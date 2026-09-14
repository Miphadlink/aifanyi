"""整文件翻译：解析常见文本格式 → 分段翻译 → 导出 txt / 语音。"""
from __future__ import annotations

import re
import uuid
from pathlib import Path

from server.config import DATA_DIR, UPLOAD_DIR
from server.services.translator import translate_text
from server.services.tts import synthesize_sync

FILE_OUT_DIR = DATA_DIR / "file_translate"
FILE_OUT_DIR.mkdir(parents=True, exist_ok=True)

SUPPORTED_EXTS = {
    ".txt", ".md", ".markdown", ".srt", ".vtt", ".csv", ".log",
    ".html", ".htm", ".xml", ".json", ".docx", ".pdf",
}

# 单次送翻译的最大字符数，超长按段切分
CHUNK_SIZE = 1800


def extract_text(path: str) -> tuple[str, str]:
    """按扩展名抽取纯文本。返回 (text, format_note)。"""
    p = Path(path)
    ext = p.suffix.lower()
    if ext not in SUPPORTED_EXTS:
        raise ValueError(f"不支持的格式: {ext}。支持: {', '.join(sorted(SUPPORTED_EXTS))}")

    if ext in (".txt", ".md", ".markdown", ".log"):
        return _read_text_file(p), ext.lstrip(".")
    if ext == ".csv":
        return _read_text_file(p), "csv"
    if ext in (".srt", ".vtt"):
        return _extract_subtitles(p), ext.lstrip(".")
    if ext in (".html", ".htm"):
        return _extract_html(p), "html"
    if ext == ".xml":
        return _extract_xml(p), "xml"
    if ext == ".json":
        return _extract_json(p), "json"
    if ext == ".docx":
        return _extract_docx(p), "docx"
    if ext == ".pdf":
        return _extract_pdf(p), "pdf"
    raise ValueError(f"不支持的格式: {ext}")


def _read_text_file(p: Path) -> str:
    raw = p.read_bytes()
    for enc in ("utf-8", "utf-8-sig", "gbk", "gb18030", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _extract_subtitles(p: Path) -> str:
    """去掉时间轴与序号，只保留字幕文本。"""
    lines = _read_text_file(p).splitlines()
    texts: list[str] = []
    for line in lines:
        s = line.strip()
        if not s or s.upper() == "WEBVTT":
            continue
        if s.isdigit() or "-->" in s:
            continue
        texts.append(s)
    return "\n".join(texts)


def _extract_html(p: Path) -> str:
    html = _read_text_file(p)
    html = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
    html = re.sub(r"(?s)<[^>]+>", "\n", html)
    html = re.sub(r"&nbsp;", " ", html)
    html = re.sub(r"&amp;", "&", html)
    html = re.sub(r"&lt;", "<", html)
    html = re.sub(r"&gt;", ">", html)
    return _normalize_blank_lines(html)


def _extract_xml(p: Path) -> str:
    xml = _read_text_file(p)
    xml = re.sub(r"(?s)<[^>]+>", "\n", xml)
    return _normalize_blank_lines(xml)


def _extract_json(p: Path) -> str:
    """提取字符串值，便于翻译；对象结构丢弃。"""
    import json

    raw = _read_text_file(p)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return raw

    parts: list[str] = []

    def walk(node):
        if isinstance(node, str):
            t = node.strip()
            if t:
                parts.append(t)
        elif isinstance(node, dict):
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(data)
    return "\n".join(parts) if parts else raw


def _extract_docx(p: Path) -> str:
    try:
        from docx import Document
    except Exception as exc:
        raise ValueError(f"无法解析 docx: {exc}") from exc
    doc = Document(str(p))
    paras = [para.text.strip() for para in doc.paragraphs if para.text and para.text.strip()]
    return "\n".join(paras)


def _extract_pdf(p: Path) -> str:
    try:
        from pypdf import PdfReader
    except Exception as exc:
        raise ValueError(f"无法解析 pdf: {exc}") from exc
    reader = PdfReader(str(p))
    texts = []
    for page in reader.pages:
        t = page.extract_text() or ""
        if t.strip():
            texts.append(t.strip())
    return "\n".join(texts)


def _normalize_blank_lines(text: str) -> str:
    lines = [ln.strip() for ln in text.splitlines()]
    out: list[str] = []
    for ln in lines:
        if ln:
            out.append(ln)
        elif out and out[-1] != "":
            out.append("")
    return "\n".join(out).strip()


def split_chunks(text: str, size: int = CHUNK_SIZE) -> list[str]:
    """按段落尽量完整地切块，避免把句子从中间切断。"""
    paras = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
    if not paras:
        paras = [text] if text.strip() else []
    chunks: list[str] = []
    buf = ""
    for para in paras:
        if len(para) > size:
            if buf:
                chunks.append(buf.strip())
                buf = ""
            # 超长段按句切
            sentences = re.split(r"(?<=[。！？.!?；;])\s*", para)
            sub = ""
            for s in sentences:
                if len(sub) + len(s) + 1 > size and sub:
                    chunks.append(sub.strip())
                    sub = s
                else:
                    sub = f"{sub} {s}".strip() if sub else s
            if sub:
                chunks.append(sub.strip())
            continue
        cand = f"{buf}\n\n{para}".strip() if buf else para
        if len(cand) > size and buf:
            chunks.append(buf.strip())
            buf = para
        else:
            buf = cand
    if buf.strip():
        chunks.append(buf.strip())
    return chunks


async def translate_file(
    path: str,
    source_lang: str = "auto",
    target_lang: str = "zh",
) -> dict:
    """整文件翻译，结果落盘为 txt，并返回路径。"""
    text, fmt = extract_text(path)
    if not text.strip():
        raise ValueError("文件中未提取到可翻译文本")

    chunks = split_chunks(text)
    translated_parts: list[str] = []
    engines: list[str] = []
    for i, chunk in enumerate(chunks, 1):
        res = await translate_text(chunk, source_lang, target_lang, scene="text")
        if res.get("error") and not res.get("text"):
            raise ValueError(res["error"])
        translated_parts.append(res.get("text") or chunk)
        if res.get("engine"):
            engines.append(res["engine"])

    out_text = "\n\n".join(translated_parts)
    job_id = uuid.uuid4().hex[:12]
    src_name = Path(path).stem
    out_path = FILE_OUT_DIR / f"{src_name}_{target_lang}_{job_id}.txt"
    out_path.write_text(out_text, encoding="utf-8")

    return {
        "text": out_text,
        "source_chars": len(text),
        "target_chars": len(out_text),
        "chunks": len(chunks),
        "format": fmt,
        "output_txt": str(out_path),
        "engine": engines[-1] if engines else "",
    }


async def text_to_mp3_async(
    text: str,
    lang: str = "zh",
    out_name: str | None = None,
) -> dict:
    """把译文合成整段 mp3（过长时按段合成后用 ffmpeg 拼接）。"""
    from server.services.tts import synthesize

    text = (text or "").strip()
    if not text:
        return {"error": "文本为空"}

    chunks = split_chunks(text, size=1200)
    if len(chunks) == 1:
        res = await synthesize(chunks[0], lang=lang)
        if res.get("error"):
            return res
        src = Path(res["path"])
        job_id = uuid.uuid4().hex[:12]
        dest = FILE_OUT_DIR / (out_name or f"tts_{job_id}.mp3")
        dest.write_bytes(src.read_bytes())
        return {"path": str(dest), "voice": res.get("voice"), "chunks": 1}

    from server.services.video_pipeline import get_ffmpeg, _run

    ffmpeg = get_ffmpeg()
    if not ffmpeg:
        return {"error": "未找到 ffmpeg，无法拼接长语音"}

    part_paths: list[Path] = []
    for chunk in chunks:
        res = await synthesize(chunk, lang=lang)
        if res.get("error"):
            return {"error": res["error"]}
        part_paths.append(Path(res["path"]))

    list_file = FILE_OUT_DIR / f"concat_{uuid.uuid4().hex[:8]}.txt"
    lines = [f"file '{p.as_posix()}'" for p in part_paths]
    list_file.write_text("\n".join(lines), encoding="utf-8")
    job_id = uuid.uuid4().hex[:12]
    dest = FILE_OUT_DIR / (out_name or f"tts_{job_id}.mp3")
    proc = _run(
        [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(list_file), "-c", "copy", str(dest)],
        timeout=600,
    )
    list_file.unlink(missing_ok=True)
    if proc.returncode != 0 or not dest.exists():
        return {"error": f"语音拼接失败: {proc.stderr[-200:] if proc.stderr else ''}"}
    return {"path": str(dest), "voice": "edge-tts", "chunks": len(chunks)}


def text_to_mp3(
    text: str,
    lang: str = "zh",
    out_name: str | None = None,
) -> dict:
    """同步包装，供脚本使用。"""
    import asyncio

    return asyncio.run(text_to_mp3_async(text, lang, out_name))
