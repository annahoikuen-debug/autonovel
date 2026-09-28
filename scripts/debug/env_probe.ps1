$ErrorActionPreference = "Continue"
# scripts\debug  ->  scripts  ->  project root
Set-Location (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent) | Out-Null

function Check($label, $path) {
    if (Test-Path $path) { Write-Host ("[OK]   {0,-28} {1}" -f $label, $path) -ForegroundColor Green }
    else { Write-Host ("[MISS] {0,-28} {1}" -f $label, $path) -ForegroundColor Red }
}

Write-Host "=== Paths ===" -ForegroundColor Cyan
Check "venv (.venv)"        ".venv"
Check "venv python"         ".venv\Scripts\python.exe"
Check "frontend/node_modules" "frontend\node_modules"
Check "huey module"         "src\backend\tasks\huey.py"
Check "alembic.ini"         "alembic.ini"
Check "env file"            ".env"
Check "docker-compose"      "docker-compose.yml"
Check "requirements.txt"    "requirements.txt"
Check "pyproject.toml"      "pyproject.toml"

Write-Host ""
Write-Host "=== src/backend/tasks ===" -ForegroundColor Cyan
if (Test-Path "src\backend\tasks") { Get-ChildItem "src\backend\tasks" -Name | ForEach-Object { Write-Host "  $_" } }
else { Write-Host "  (directory missing)" -ForegroundColor Red }

Write-Host ""
Write-Host "=== src/backend/tasks/huey (dir) ===" -ForegroundColor Cyan
if (Test-Path "src\backend\tasks\huey") { Get-ChildItem "src\backend\tasks\huey" -Name -Recurse | ForEach-Object { Write-Host "  $_" } }
else { Write-Host "  (directory missing)" -ForegroundColor Red }

Write-Host ""
Write-Host "=== Toolchain ===" -ForegroundColor Cyan
foreach ($c in @("python", "py", "node", "npm", "docker")) {
    $cmd = Get-Command $c -ErrorAction SilentlyContinue
    if ($cmd) { Write-Host ("  {0,-8} -> {1}" -f $c, $cmd.Source) -ForegroundColor Gray }
    else { Write-Host ("  {0,-8} -> NOT FOUND" -f $c) -ForegroundColor Red }
}
Write-Host ""
Write-Host "  py -0p (installed pythons):"
try { & py -0p 2>&1 | ForEach-Object { Write-Host "    $_" -ForegroundColor DarkGray } } catch { Write-Host "    (none)" -ForegroundColor Red }

Write-Host ""
Write-Host "=== Ports in use (5173 / 8200) ===" -ForegroundColor Cyan
foreach ($p in @(5173, 8200)) {
    $conn = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue
    if ($conn) { Write-Host "  port $p IN USE (pid $($conn.OwningProcess))" -ForegroundColor Yellow }
    else { Write-Host "  port $p free" -ForegroundColor DarkGray }
}

Write-Host ""
Write-Host "=== Stray processes ===" -ForegroundColor Cyan
Get-Process python*, node* -ErrorAction SilentlyContinue |
    Select-Object Name, Id, @{Name = "MemMB"; Expression = { [math]::Round($_.WorkingSet64 / 1MB, 1) } } |
    Format-Table -AutoSize | Out-String -Width 120
