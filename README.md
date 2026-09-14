# AI 智能翻译

Windows 桌面多模态翻译工具：文字 / 图片 / 视频 / 游戏。

技术栈：Electron + Vue3 + FastAPI（Python 3.12）。

## 环境要求

- Windows 10/11
- Node.js 22+
- Python 3.12（`py -3.12`）
- ffmpeg（视频功能；`winget install Gyan.FFmpeg`）
- 可选：NVIDIA GPU + Ollama（本地翻译）

## 快速开始

```powershell
# 1. 安装前端依赖
npm install

# 2. 创建 Python 环境并安装后端依赖
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r server\requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 3. 配置 API（复制模板后填写）
Copy-Item .env.example .env
# 编辑 .env，填入 TRANSLATE_API_KEY

# 4. 环境自检
.\.venv\Scripts\python.exe scripts\env_check.py

# 5. 开发模式（两个终端）
# 终端 A：后端
.\.venv\Scripts\python.exe -m uvicorn server.main:app --host 127.0.0.1 --port 8765 --reload
# 终端 B：前端
npm run dev:vite
# 可选终端 C：Electron 壳
npm run dev:electron
```

浏览器开发可直接打开 `http://127.0.0.1:5173`（游戏拖入启动需 Electron）。

## 目录结构

```
electron/     Electron 主进程与 preload
src/          Vue3 前端
server/       FastAPI 后端
scripts/      环境自检等脚本
data/         本地配置、缓存、字幕输出
```

## 功能说明

| 模块 | 能力 |
|------|------|
| 文字 | 流式翻译、历史记录 |
| 图片 | OCR + 对照/覆盖 |
| 视频 | 多格式 → Whisper → SRT/ASS |
| 游戏 | 拖入 exe/文件夹启动 → 浮窗覆盖译文 |

游戏翻译不注入进程、不读内存，仅屏幕层叠加；网游反作弊场景请勿使用。

## 作者

ZHANGCHAO
