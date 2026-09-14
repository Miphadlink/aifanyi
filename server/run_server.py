"""便携版后端入口：供 PyInstaller 打包，启动本地 FastAPI。"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def _prepare_env() -> None:
    # 国内 HF 镜像 / 禁用 xet，避免无网关环境下 ASR 下载失败
    os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

    # 打包后可执行文件旁的 ffmpeg
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        ffmpeg_bin = exe_dir / "ffmpeg"
        if ffmpeg_bin.is_dir():
            os.environ.setdefault("FFMPEG_DIR", str(ffmpeg_bin))
        # PATH 里也加上，方便 shutil.which
        os.environ["PATH"] = str(ffmpeg_bin) + os.pathsep + os.environ.get("PATH", "")


def _ensure_stdio() -> None:
    """windowed 打包时 sys.stdout/stderr 可能为 None，Uvicorn 日志会崩。"""
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    if sys.stdin is None:
        sys.stdin = open(os.devnull, "r", encoding="utf-8")


def main() -> None:
    _prepare_env()
    _ensure_stdio()
    # 必须在设置环境后再 import 应用
    import uvicorn

    from server.main import app  # noqa: PLC0415

    host = "127.0.0.1"
    port = 8765
    for i, arg in enumerate(sys.argv):
        if arg == "--host" and i + 1 < len(sys.argv):
            host = sys.argv[i + 1]
        if arg == "--port" and i + 1 < len(sys.argv):
            port = int(sys.argv[i + 1])
    # 关闭彩色日志，避免 isatty 相关问题
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info",
        log_config={
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "()": "uvicorn.logging.DefaultFormatter",
                    "fmt": "%(levelprefix)s %(message)s",
                    "use_colors": False,
                },
            },
            "handlers": {
                "default": {
                    "formatter": "default",
                    "class": "logging.StreamHandler",
                    "stream": "ext://sys.stderr",
                },
            },
            "root": {"handlers": ["default"], "level": "INFO"},
        },
    )


if __name__ == "__main__":
    main()
