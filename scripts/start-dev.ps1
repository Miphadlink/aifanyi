# 启动开发环境：后端 + 前端（需已 npm install 且 .venv 就绪）
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

if (-not (Test-Path ".venv\Scripts\python.exe")) {
  Write-Host "缺少 .venv，请先: py -3.12 -m venv .venv"
  exit 1
}

Write-Host "启动后端 http://127.0.0.1:8765 ..."
Start-Process -FilePath ".\.venv\Scripts\python.exe" `
  -ArgumentList "-m","uvicorn","server.main:app","--host","127.0.0.1","--port","8765","--reload" `
  -WorkingDirectory $root

Write-Host "启动前端 http://127.0.0.1:5173 ..."
npm run dev:vite
