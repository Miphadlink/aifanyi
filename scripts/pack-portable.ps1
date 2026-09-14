# Portable pack script - ASCII only paths/messages to avoid PS encoding issues
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$env:ELECTRON_MIRROR = "https://npmmirror.com/mirrors/electron/"

Get-Process "AI智能翻译", "ait-server" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue

Write-Host "==> build vite"
npm run build:vite
if ($LASTEXITCODE -ne 0) { throw "vite failed" }

$serverExe = Join-Path $root "release\server-dist\ait-server\ait-server.exe"
if (-not (Test-Path $serverExe)) {
  Write-Host "==> build server"
  & (Join-Path $root ".venv\Scripts\python.exe") -m PyInstaller packaging\server.spec `
    --distpath release\server-dist --workpath release\server-build --noconfirm
  if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }
}

Write-Host "==> copy ffmpeg"
$ffSrc = Join-Path $root "tools\ffmpeg\bin\ffmpeg.exe"
$ffDstDir = Join-Path $root "release\server-dist\ait-server\ffmpeg"
New-Item -ItemType Directory -Force -Path $ffDstDir | Out-Null
if (Test-Path $ffSrc) {
  Copy-Item $ffSrc (Join-Path $ffDstDir "ffmpeg.exe") -Force
}

Write-Host "==> stage clean app"
$stage = Join-Path $root "release\_pack_stage"
if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
New-Item -ItemType Directory -Path $stage | Out-Null
Copy-Item (Join-Path $root "package.json") $stage
Copy-Item (Join-Path $root "dist") (Join-Path $stage "dist") -Recurse
Copy-Item (Join-Path $root "electron") (Join-Path $stage "electron") -Recurse

Write-Host "==> electron-packager"
$packagerJs = Join-Path $root "node_modules\electron-packager\bin\electron-packager.js"
$asarJs = Join-Path $root "node_modules\@electron\asar\bin\asar.js"
$node = (Get-Command node).Source
$serverAbs = (Resolve-Path (Join-Path $root "release\server-dist\ait-server")).Path
$outDir = Join-Path $root "release"

$packArgs = @(
  $packagerJs
  $stage
  "AITranslator"
  "--platform=win32"
  "--arch=x64"
  ("--out=" + $outDir)
  "--overwrite"
  "--asar"
  "--ignore=node_modules"
  ("--extra-resource=" + $serverAbs)
)
& $node @packArgs
if ($LASTEXITCODE -ne 0) { throw "electron-packager failed" }

$final = Join-Path $outDir "AITranslator-win32-x64"
if (-not (Test-Path $final)) { throw "output folder missing: $final" }

Write-Host "==> verify no secrets"
$asar = Join-Path $final "resources\app.asar"
$extract = Join-Path $env:TEMP ("ait_chk_" + [guid]::NewGuid().ToString("N"))
& $node $asarJs extract $asar $extract
if (Test-Path (Join-Path $extract ".env")) { throw "asar contains .env" }
$leak = Get-ChildItem $extract -Recurse -File -ErrorAction SilentlyContinue |
  Select-String -Pattern "sk-[A-Za-z0-9]{20,}" -ErrorAction SilentlyContinue
Remove-Item $extract -Recurse -Force -ErrorAction SilentlyContinue
if ($leak) { throw "API key found in asar" }

$serverInRes = Join-Path $final "resources\ait-server"
if (-not (Test-Path (Join-Path $serverInRes "ait-server.exe"))) {
  throw "bundled server missing under resources/ait-server"
}

Write-Host "OK portable pack:"
Write-Host "  $final"
Write-Host "  entry: $final\AITranslator.exe"
Write-Host "  server: $final\resources\ait-server\ait-server.exe"
