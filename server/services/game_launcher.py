"""游戏启动与会话：拖入 exe/lnk/文件夹 → 启动 → 绑定窗口。"""
from __future__ import annotations

import os
import re
import uuid
from pathlib import Path

import win32process
import win32gui

EXCLUDE_NAME_RE = re.compile(
    r"(unins|uninstall|crashhandler|unitycrashhandler|dxsetup|vcredist|"
    r"ue4prereq|dotnet|setup|launcher_helper)",
    re.I,
)


def detect_candidates(path: str) -> list[dict]:
    """根据用户拖入的路径，找出可能的主程序 exe。"""
    p = Path(path)
    if p.is_file() and p.suffix.lower() == ".exe":
        return [{"path": str(p), "reason": "用户指定的可执行文件"}]
    if p.is_file() and p.suffix.lower() == ".lnk":
        target = _resolve_lnk(str(p))
        if target:
            return [{"path": target, "reason": f"快捷方式目标: {target}"}]
        return []
    if p.is_file():
        return []
    # 目录：扫描一层 + 常见子目录
    root = p
    found: list[dict] = []
    scan_dirs = [root]
    for child in root.iterdir():
        if child.is_dir() and child.name.lower() in {"win", "win64", "win32", "game", "bin"}:
            scan_dirs.append(child)
    for d in scan_dirs:
        try:
            for item in d.iterdir():
                if item.suffix.lower() != ".exe":
                    continue
                name = item.name.lower()
                if EXCLUDE_NAME_RE.search(name):
                    continue
                reason = _describe_game(root, item)
                found.append({"path": str(item), "reason": reason})
        except OSError:
            continue
    # 优先：名字含 game / 主目录 exe
    found.sort(key=lambda x: (0 if "game" in Path(x["path"]).name.lower() else 1, x["path"]))
    return found[:12]


def _describe_game(root: Path, exe: Path) -> str:
    tags = []
    if (exe.parent / "UnityPlayer.dll").exists() or (exe.parent / f"{exe.stem}_Data").exists():
        tags.append("Unity")
    if (root / "Data").exists() or (root / "www").exists() or exe.name.lower() == "game.exe":
        tags.append("RPG Maker?")
    if list(root.glob("*.pck")):
        tags.append("Godot?")
    if not tags:
        tags.append("未知引擎")
    return " / ".join(tags)


def _resolve_lnk(lnk_path: str) -> str | None:
    """用 PowerShell 解析 .lnk 目标（避免额外依赖）。"""
    import subprocess

    ps = (
        "$sh = New-Object -ComObject WScript.Shell; "
        f"$lnk = $sh.CreateShortcut('{lnk_path}'); "
        "Write-Output $lnk.TargetPath"
    )
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True,
            text=True,
            timeout=10,
        )
        target = (proc.stdout or "").strip()
        return target or None
    except Exception:
        return None


def detect_engine(exe_path: str) -> str:
    exe = Path(exe_path)
    parent = exe.parent
    if (parent / "UnityPlayer.dll").exists() or (parent / f"{exe.stem}_Data").is_dir():
        return "Unity"
    if (parent / "GameAssembly.dll").exists():
        return "Unity/IL2CPP"
    if (parent / "Data").is_dir() or (parent / "www").is_dir():
        return "RPG Maker"
    if list(parent.glob("*.pck")):
        return "Godot"
    return "Unknown"


class GameSession:
    def __init__(self, exe_path: str):
        self.session_id = uuid.uuid4().hex[:12]
        self.exe_path = exe_path
        self.game_name = Path(exe_path).stem
        self.engine = detect_engine(exe_path)
        self.pid: int | None = None
        self.window_title = ""
        self.hwnd: int | None = None
        self.status = "created"
        self.capture_enabled = False
        self.lines: list[dict] = []


SESSIONS: dict[str, GameSession] = {}


def launch_session(exe_path: str) -> GameSession:
    """启动游戏进程并尝试绑定主窗口。"""
    exe = Path(exe_path)
    if not exe.exists():
        raise FileNotFoundError(f"游戏文件不存在: {exe_path}")
    session = GameSession(str(exe))
    cwd = str(exe.parent)
    # DETACHED 不抢控制台；工作目录设为游戏根，兼容 RPG Maker 资源路径
    import subprocess

    proc = subprocess.Popen(
        [str(exe)],
        cwd=cwd,
        shell=False,
    )
    session.pid = proc.pid
    session.status = "running"
    SESSIONS[session.session_id] = session
    # 窗口可能稍后才出现，先尝试一次
    bind_window(session)
    return session


def bind_window(session: GameSession) -> bool:
    """按 PID 找主窗口。"""
    if not session.pid:
        return False
    result: list[int] = []

    def enum_cb(hwnd, _extra):
        if not win32gui.IsWindowVisible(hwnd):
            return
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        if pid == session.pid:
            title = win32gui.GetWindowText(hwnd)
            if title:
                result.append(hwnd)

    win32gui.EnumWindows(enum_cb, None)
    if not result:
        return False
    # 取面积最大窗口当主窗口
    best = None
    best_area = -1
    for hwnd in result:
        try:
            rect = win32gui.GetWindowRect(hwnd)
            area = (rect[2] - rect[0]) * (rect[3] - rect[1])
        except Exception:
            continue
        if area > best_area:
            best_area = area
            best = hwnd
    if best is None:
        return False
    session.hwnd = best
    session.window_title = win32gui.GetWindowText(best)
    return True


def get_window_rect(session: GameSession) -> dict | None:
    if session.hwnd is None:
        bind_window(session)
    if session.hwnd is None:
        return None
    try:
        if not win32gui.IsWindow(session.hwnd):
            session.status = "exited"
            return None
        left, top, right, bottom = win32gui.GetWindowRect(session.hwnd)
        return {"x": left, "y": top, "w": right - left, "h": bottom - top}
    except Exception:
        return None


def stop_session(session_id: str) -> bool:
    session = SESSIONS.get(session_id)
    if not session:
        return False
    session.capture_enabled = False
    session.status = "stopped"
    if session.pid:
        try:
            import subprocess

            subprocess.run(
                ["taskkill", "/PID", str(session.pid), "/T", "/F"],
                capture_output=True,
                timeout=10,
            )
        except Exception:
            pass
    SESSIONS.pop(session_id, None)
    return True
