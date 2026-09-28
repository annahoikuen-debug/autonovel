# start_local.ps1 を実際に起動し、各サービスの到達性を確認するデバッグランナー。
# 出力: logs\e2e_*.log / logs\e2e_summary.txt
param(
    [int]$WaitSeconds = 120
)

$ErrorActionPreference = "Continue"
$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
Set-Location $root

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$logDir = Join-Path $root "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$startLog = Join-Path $logDir "e2e_start_$stamp.log"

Write-Host "=== AutoNovel E2E startup test ===" -ForegroundColor Cyan
Write-Host "root: $root"
Write-Host "log : $startLog"

# 事前クリーンアップ
powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root "scripts\stop_local.ps1") | Out-Null

$proc = Start-Process -FilePath "powershell" `
    -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", (Join-Path $root "scripts\start_local.ps1"), "-SkipInstall", "-NoBrowser") `
    -WorkingDirectory $root -PassThru `
    -RedirectStandardOutput $startLog -RedirectStandardError "$startLog.err"

$backendUp = $false
$frontendUp = $false
$deadline = (Get-Date).AddSeconds($WaitSeconds)

while ((Get-Date) -lt $deadline) {
    if (-not $backendUp) {
        try { $r = Invoke-WebRequest -Uri "http://127.0.0.1:8200/health" -UseBasicParsing -TimeoutSec 3; if ($r.StatusCode -eq 200) { $backendUp = $true; Write-Host "[+] backend :8200 UP" -ForegroundColor Green } } catch { }
    }
    if (-not $frontendUp) {
        try { $r = Invoke-WebRequest -Uri "http://127.0.0.1:5173/" -UseBasicParsing -TimeoutSec 3; if ($r.StatusCode -eq 200) { $frontendUp = $true; Write-Host "[+] frontend :5173 UP" -ForegroundColor Green } } catch { }
    }
    if ($backendUp -and $frontendUp) { break }
    if ($proc.HasExited) { Write-Host "[!] launcher exited early (code $($proc.ExitCode))" -ForegroundColor Red; break }
    Start-Sleep -Seconds 3
}

$summary = @()
$summary += "backend_up  = $backendUp"
$summary += "frontend_up = $frontendUp"
$summary += "launcher_running = $(-not $proc.HasExited)"
$summary | ForEach-Object { Write-Host $_ }

Write-Host ""
Write-Host "=== python / node / vite processes ===" -ForegroundColor Cyan
Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -match "^(python|node|npm|cmd)\.exe$" -and $_.CommandLine -match "autonovel|uvicorn|huey|vite|npm" } |
    Select-Object ProcessId, Name, CommandLine | Format-Table -AutoSize -Wrap | Out-String -Width 250

Write-Host "=== listening ports ===" -ForegroundColor Cyan
foreach ($p in @(5173, 8200)) {
    $c = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue
    if ($c) { Write-Host "  $p LISTENING (pid $($c[0].OwningProcess))" -ForegroundColor Green }
    else { Write-Host "  $p not listening" -ForegroundColor Red }
}

Write-Host "=== start_local.ps1 stdout ===" -ForegroundColor Cyan
if (Test-Path $startLog) { Get-Content $startLog | ForEach-Object { Write-Host $_ } }
if (Test-Path "$startLog.err") { $e = Get-Content "$startLog.err"; if ($e) { Write-Host "--- stderr ---"; $e | ForEach-Object { Write-Host $_ } } }

Write-Host ""
Write-Host "=== PowerShell job output (backend/worker/frontend) ===" -ForegroundColor Cyan
try {
    $jobs = powershell -NoProfile -Command "Get-Job | Receive-Job -Keep" 2>&1
    $jobs | ForEach-Object { Write-Host $_ }
} catch { Write-Host "  (no job output: $_)" }

# 停止
Write-Host ""
Write-Host "=== stopping ===" -ForegroundColor Yellow
powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root "scripts\stop_local.ps1") | Out-Null
try { if (-not $proc.HasExited) { Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue } } catch {}
Get-Process python, node -ErrorAction SilentlyContinue |
    Where-Object { $_.Path -like "$root*" -or $true } | Out-Null

Write-Host ""
Write-Host "RESULT backend=$backendUp frontend=$frontendUp" -ForegroundColor $(if ($backendUp -and $frontendUp) { "Green" } else { "Red" })
