"""环境自检：Python 版本、ffmpeg、可选 GPU。用法: py -3.12 scripts/env_check.py"""
from __future__ import annotations

import shutil
import subprocess
import sys


def main() -> int:
    print("=== AI 智能翻译 · 环境自检 ===")
    ok = True
    ver = sys.version.split()[0]
    major, minor = sys.version_info[:2]
    print(f"Python: {ver}")
    if (major, minor) < (3, 10):
        print("  [错误] 需要 Python 3.10+，推荐 3.12（py -3.12）")
        ok = False
    else:
        print("  [通过]")

    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if ffmpeg and ffprobe:
        print(f"ffmpeg: {ffmpeg}")
        print("  [通过]")
    else:
        print("ffmpeg: 未安装")
        print("  [警告] 视频翻译不可用。安装: winget install Gyan.FFmpeg")
        # 视频依赖缺失不阻断文字/图片/游戏

    try:
        proc = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        line = (proc.stdout or "").strip()
        if line:
            print(f"GPU: {line}")
            print("  [通过] 可本地推理")
        else:
            print("GPU: 无 NVIDIA 输出")
    except Exception:
        print("GPU: nvidia-smi 不可用（可继续用云端 API）")

    print("=== 检查结束 ===")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
