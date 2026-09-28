# AutoNovel ローカル停止スクリプト (PowerShell)
#
# Backend (8200) / Frontend (5173) / Huey Worker を停止する。
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts/stop_local.ps1
#
# 停止の優先順位:
#   1. logs\autonovel.pids に記録された PID（start_local.ps1 が書いたもの）
#   2. ポート 8200 / 5173 を LISTEN しているプロセス
#   3. コマンドラインが autonovel の uvicorn / huey / vite に一致するプロセス
#
# どの経路でも 1 つでも見つかれば停止し、3 秒待っても生き残れば強制終了する。

$ErrorActionPreference = "Continue"

$ScriptDir = $PSScriptRoot
$Root = Split-Path $ScriptDir -Parent
$PidFile = Join-Path $Root "logs\autonovel.pids"
$targetPorts = @(8200, 5173)

$script:stopped = New-Object System.Collections.Generic.HashSet[int]

Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "        AutoNovel - Local Service Stopper               " -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host ""

function Stop-OneProcess {
    param([int]$ProcId, [string]$Label)

    if ($script:stopped.Contains($ProcId)) { return }
    if ($ProcId -le 0) { return }

    $proc = Get-Process -Id $ProcId -ErrorAction SilentlyContinue
    if (-not $proc) {
        $script:stopped.Add($ProcId) | Out-Null
        return
    }

    # /T で子プロセス（例: npm → vite）ごと確実に落とす
    & taskkill /PID $ProcId /T 2>&1 | Out-Null
    Start-Sleep -Milliseconds 600

    $proc = Get-Process -Id $ProcId -ErrorAction SilentlyContinue
    if ($proc) {
        Write-Host "  [$Label] PID $ProcId still alive -> force kill" -ForegroundColor Yellow
        & taskkill /PID $ProcId /T /F 2>&1 | Out-Null
        Start-Sleep -Milliseconds 300
    }

    if (Get-Process -Id $ProcId -ErrorAction SilentlyContinue) {
        Write-Host "  [$Label] WARNING: PID $ProcId could not be terminated." -ForegroundColor Red
    }
    else {
        Write-Host "  [$Label] stopped PID $ProcId ($($proc.ProcessName))" -ForegroundColor Green
        $script:stopped.Add($ProcId) | Out-Null
    }
}

# --- 1. PID ファイル ------------------------------------------------------- #
if (Test-Path $PidFile) {
    Write-Host "[pidfile] Reading $PidFile ..." -ForegroundColor Yellow
    foreach ($line in (Get-Content $PidFile -ErrorAction SilentlyContinue)) {
        if ($line -match '^\s*([A-Za-z]+)\s*=\s*(\d+)\s*$') {
            Stop-OneProcess -ProcId ([int]$Matches[2]) -Label $Matches[1]
        }
    }
    Remove-Item $PidFile -ErrorAction SilentlyContinue
}
else {
    Write-Host "[pidfile] not found (services were not started by start_local.ps1)" -ForegroundColor DarkGray
}

# --- 2. ポートから逆引き --------------------------------------------------- #
foreach ($port in $targetPorts) {
    Write-Host "[port $port] Looking for listeners ..." -ForegroundColor Yellow
    $listeners = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    if ($listeners) {
        foreach ($procId in ($listeners | Select-Object -ExpandProperty OwningProcess -Unique)) {
            Stop-OneProcess -ProcId ([int]$procId) -Label "port$port"
        }
    }
    else {
        Write-Host "  [port $port] no listener." -ForegroundColor DarkGray
    }
}

# --- 3. コマンドライン一致（ワーカーなど） --------------------------------- #
Write-Host "[scan] Looking for residual AutoNovel processes ..." -ForegroundColor Yellow
try {
    $candidates = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        $_.CommandLine -and (
            $_.CommandLine -match "huey_consumer" -or
            $_.CommandLine -match "run_worker\.py" -or
            ($_.CommandLine -match "uvicorn" -and $_.CommandLine -match "src\.backend\.server") -or
            ($_.CommandLine -match "vite" -and $_.CommandLine -match "autonovel")
        )
    }
    if ($candidates) {
        foreach ($c in $candidates) {
            Stop-OneProcess -ProcId ([int]$c.ProcessId) -Label "scan"
        }
    }
    else {
        Write-Host "  [scan] nothing found." -ForegroundColor DarkGray
    }
}
catch {
    Write-Host "  [scan] could not enumerate processes: $_" -ForegroundColor DarkYellow
}

Write-Host ""
Write-Host "[AutoNovel] Stop sequence complete." -ForegroundColor Green
