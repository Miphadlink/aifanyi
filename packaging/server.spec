# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 规格：便携后端。不含任何 API Key。"""
import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, copy_metadata

# spec 在 packaging/ 下，项目根为上一级
ROOT = Path(SPECPATH).resolve().parent
os.chdir(ROOT)

block_cipher = None

datas = []
binaries = []
hiddenimports = [
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan.on",
    "server.main",
    "server.run_server",
    "server.config",
    "server.services.translator",
    "server.services.ocr",
    "server.services.tts",
    "server.services.video_pipeline",
    "server.services.game_launcher",
    "server.services.game_capture",
    "server.services.file_translate",
    "win32gui",
    "win32process",
    "win32api",
    "pythoncom",
    "edge_tts",
    "faster_whisper",
    "ctranslate2",
    "onnxruntime",
    "rapidocr_onnxruntime",
    "mss",
    "PIL.Image",
    "PIL.ImageDraw",
    "PIL.ImageFont",
    "docx",
    "pypdf",
    "httpx",
    "httpcore",
    "h11",
    "anyio",
    "sniffio",
    "dotenv",
]

for pkg in ["fastapi", "starlette", "pydantic", "uvicorn", "edge_tts", "rapidocr_onnxruntime"]:
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        pass

for dist in ["fastapi", "starlette", "pydantic", "uvicorn", "edge-tts", "python-multipart"]:
    try:
        datas += copy_metadata(dist)
    except Exception:
        pass

a = Analysis(
    [str(ROOT / "server" / "run_server.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "torch", "tensorflow"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ait-server",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="ait-server",
)
