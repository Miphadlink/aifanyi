# 打包 Windows 绿色版：先做干净暂存目录，再打包，杜绝 .env 入包
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$env:ELECTRON_MIRROR = "https://npmmirror.com/mirrors/electron/"
Get-Process "AI智能翻译" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue

npm run build:vite
if ($LASTEXITCODE -ne 0) { throw "vite build failed" }

$stage = Join-Path $root "release\_pack_stage"
if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
New-Item -ItemType Directory -Path $stage | Out-Null

# 只拷贝界面与主进程，绝不拷 .env / server / data
Copy-Item (Join-Path $root "package.json") $stage
Copy-Item (Join-Path $root "dist") (Join-Path $stage "dist") -Recurse
Copy-Item (Join-Path $root "electron") (Join-Path $stage "electron") -Recurse

$packagerJs = Join-Path $root "node_modules\electron-packager\bin\electron-packager.js"
$asarJs = Join-Path $root "node_modules\@electron\asar\bin\asar.js"
$node = (Get-Command node).Source

$packArgs = @(
  $packagerJs
  $stage
  'AITranslator'
  '--platform=win32'
  '--arch=x64'
  '--out=' + (Join-Path $root "release")
  '--overwrite'
  '--asar'
  '--ignore=node_modules'
)
& $node @packArgs
if ($LASTEXITCODE -ne 0) { throw "electron-packager failed" }

# 统一成中文目录名，避免 PowerShell/编码导致双份目录
$built = Join-Path $root "release\AITranslator-win32-x64"
$final = Join-Path $root "release\AI智能翻译-win32-x64"
if (Test-Path $final) { Remove-Item $final -Recurse -Force }
if (Test-Path $built) { Rename-Item $built -NewName "AI智能翻译-win32-x64" }
# 清理历史乱码目录
Get-ChildItem (Join-Path $root "release") -Directory | Where-Object {
  $_.Name -ne 'AI智能翻译-win32-x64' -and $_.Name -like 'AI*'
} | ForEach-Object { Remove-Item $_.FullName -Recurse -Force -ErrorAction SilentlyContinue }

$asar = Join-Path $root "release\AI智能翻译-win32-x64\resources\app.asar"
$extract = Join-Path $env:TEMP ("ait_asar_" + [guid]::NewGuid().ToString('N'))
& $node $asarJs extract $asar $extract
if (Test-Path (Join-Path $extract ".env")) {
  Remove-Item $extract -Recurse -Force -ErrorAction SilentlyContinue
  throw "pack failed: .env in asar"
}
$leak = Get-ChildItem $extract -Recurse -File -ErrorAction SilentlyContinue |
  Select-String -Pattern 'sk-[A-Za-z0-9]{20,}' -ErrorAction SilentlyContinue
$files = @(Get-ChildItem $extract | Select-Object -ExpandProperty Name)
Remove-Item $extract -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item $stage -Recurse -Force -ErrorAction SilentlyContinue
if ($leak) { throw "pack failed: API key found" }

Write-Host "OK clean pack. asar top-level:" ($files -join ', ')
Write-Host "Output: release\AI智能翻译-win32-x64"
