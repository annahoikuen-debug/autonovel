# AutoNovel ローカル開発ランチャー (PowerShell)
#
# Backend (FastAPI/Uvicorn) + Huey Worker + Frontend (Vite) を一括起動する。
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts/start_local.ps1
#   powershell -ExecutionPolicy Bypass -File scripts/start_local.ps1 -DryRun
#   powershell -ExecutionPolicy Bypass -File scripts/start_local.ps1 -SkipInstall
#   powershell -ExecutionPolicy Bypass -File scripts/start_local.ps1 -NoBrowser
#
# 設計方針:
#   1. 起動に使う Python ���依存関係まで検証して選ぶ（空の .venv で起動失敗するのを防ぐ）
#   2. 全サービスの stdout/stderr を logs/ へ記録する（失敗原因が黒箱にならない）
#   3. ヘルスチェックが通るまで待ってからブラウザを開く（固定 10 秒待ちをやめる）
#   4. プロセスが死んだらログの末尾を表示して全サービスを停止する
#
param(
    [switch]$DryRun,
    [switch]$SkipInstall,
    [switch]$NoBrowser,
    [switch]$NoWorker,
    [switch]$RecreateVenv,
    [int]$ReadyTimeoutSec = 180
)

$ErrorActionPreference = "Stop"

# --------------------------------------------------------------------------- #
# パス
# --------------------------------------------------------------------------- #

# scripts\ 配下に置かれているので、1 つ上へ上がるのがプロジェクトルート。
$ScriptDir = $PSScriptRoot
$Root = Split-Path $ScriptDir -Parent
$FrontendDir = Join-Path $Root "frontend"
$LogDir = Join-Path $Root "logs"
$PidFile = Join-Path $LogDir "autonovel.pids"

$BackendPort = 8200
$FrontendPort = 5173

function Write-Step($msg) { Write-Host "[*] $msg" -ForegroundColor Cyan }
function Write-Ok($msg) { Write-Host "[OK] $msg" -ForegroundColor Green }
function Write-Warn2($msg) { Write-Host "[!] $msg" -ForegroundColor Yellow }
function Write-Err2($msg) { Write-Host "[X] $msg" -ForegroundColor Red }

Set-Location $Root

# Detect and add Node.js path to PATH if needed
$nodePaths = @(
    "C:\Program Files\nodejs",
    "C:\Program Files (x86)\nodejs"
)
foreach ($p in $nodePaths) {
    if ((Test-Path "$p\node.exe") -and ($env:PATH -notlike "*$p*")) {
        $env:PATH = "$p;$env:PATH"
    }
}

# --------------------------------------------------------------------------- #
# Python インタプリタの解決
# --------------------------------------------------------------------------- #

# バックエンドの起動に必要なモジュール。1 つでも欠けていれば起動は即失敗する。
$RequiredModules = @("fastapi", "uvicorn", "huey", "sqlalchemy", "alembic", "pydantic")

function Invoke-NativeQuiet {
    <#
      ネイティブコマンドを「終了コードだけ」返す形で実行する。
      $ErrorActionPreference='Stop' のままだと、ModuleNotFoundError などが
      stderr に出た瞬間に NativeCommandError としてスクリプト全体が落ちる。
    #>
    param([string]$Exe, [string[]]$NativeArgs)
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & $Exe @NativeArgs *> $null
        return $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $prev
    }
}

function Test-PythonUsable {
    param([string]$Exe, [string[]]$Modules)
    if (-not $Exe) { return $false }
    if (-not (Test-Path $Exe)) { return $false }
    $probe = ($Modules | ForEach-Object { "import $_" }) -join "; "
    return ((Invoke-NativeQuiet -Exe $Exe -NativeArgs @("-c", $probe)) -eq 0)
}

function Resolve-Python {
    <#
      .venv (依存が揃っている場合のみ) → 現在の Python → py ランチャー の順に評価する。
      「ディレクトリがある」だけでは不十分で、実際に import できるかを見る。
    #>
    $candidates = @()

    $venvPython = Join-Path $Root ".venv\Scripts\python.exe"
    if (-not $RecreateVenv -and (Test-Path $venvPython)) {
        $candidates += ,@{ Label = ".venv"; Exe = $venvPython }
    }

    $onPath = (Get-Command python -ErrorAction SilentlyContinue)
    if ($onPath) { $candidates += ,@{ Label = "PATH python"; Exe = $onPath.Source } }

    $pyLauncher = (Get-Command py -ErrorAction SilentlyContinue)
    if ($pyLauncher) { $candidates += ,@{ Label = "py launcher"; Exe = $pyLauncher.Source } }

    foreach ($c in $candidates) {
        if (Test-PythonUsable -Exe $c.Exe -Modules $RequiredModules) {
            return $c
        }
        Write-Verbose "not usable: $($c.Label) ($($c.Exe))"
    }
    return $null
}

function New-Venv {
    Write-Step "Creating .venv ..."
    $created = $false
    $pyLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($pyLauncher) {
        Invoke-NativeQuiet -Exe $pyLauncher.Source -NativeArgs @("-3.12", "-m", "venv", (Join-Path $Root ".venv")) | Out-Null
        if (Test-Path $venvPython) { $created = $true }
    }
    if (-not $created) {
        $onPath = Get-Command python -ErrorAction SilentlyContinue
        if ($onPath) {
            Invoke-NativeQuiet -Exe $onPath.Source -NativeArgs @("-m", "venv", (Join-Path $Root ".venv")) | Out-Null
            if (Test-Path $venvPython) { $created = $true }
        }
    }
    if (-not $created) {
        Write-Err2 "Could not create .venv. Install Python 3.12+ and retry."
        return $false
    }
    return $true
}

# --------------------------------------------------------------------------- #
# 1. Python 環境
# --------------------------------------------------------------------------- #

Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "        AutoNovel - Local Development Launcher          " -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host ""

Write-Step "[1/6] Resolving Python interpreter ..."
$venvPython = Join-Path $Root ".venv\Scripts\python.exe"
$python = Resolve-Python

if ($RecreateVenv -and (Test-Path (Join-Path $Root ".venv"))) {
    Write-Warn2 "-RecreateVenv specified; removing existing .venv ..."
    Remove-Item -Recurse -Force (Join-Path $Root ".venv") -ErrorAction SilentlyContinue
    $python = $null
}

if (-not $python -and -not $SkipInstall) {
    Write-Warn2 "No Python with the required packages was found."
    if (New-Venv) {
        Write-Step "Installing backend dependencies into .venv (this can take a few minutes) ..."
        & $venvPython -m pip install --upgrade pip 2>&1 | Out-Null
        & $venvPython -m pip install -e ".[dev]" 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Write-Err2 'pip install failed. Run manually:  .venv\Scripts\python.exe -m pip install -e ".[dev]"'
            exit 1
        }
        $python = Resolve-Python
    }
}

if (-not $python) {
    Write-Err2 "Could not find a Python that can import: $($RequiredModules -join ', ')"
    Write-Host ""
    Write-Host "  Fix it with one of:" -ForegroundColor Yellow
    Write-Host '    1) .venv\Scripts\python.exe -m pip install -e ".[dev]"'
    Write-Host '    2) py -m pip install -e ".[dev]"   (installs into the global interpreter)'
    Write-Host "    3) scripts\doctor.ps1  (prints a detailed diagnosis)"
    Write-Host ""
    exit 1
}

$PythonExe = $python.Exe
$pyVersion = (& $PythonExe -c "import sys; print(sys.version.split()[0])" 2>$null | Select-Object -Last 1)
Write-Ok "Python: $PythonExe  [$($python.Label)] Python $pyVersion"

# --------------------------------------------------------------------------- #
# 2. 環境変数
# --------------------------------------------------------------------------- #

Write-Step "[2/6] Configuring environment ..."
$env:HUEY_BACKEND = "sqlite"
$env:DATABASE_URL = "sqlite:///./autonovel.db"
$env:HUEY_IMMEDIATE = "false"
$env:PYTHONPATH = $Root
$env:PYTHONUNBUFFERED = "1"   # ログがバッファされて看不到的原因を出すのを防ぐ
Write-Ok "HUEY_BACKEND = $env:HUEY_BACKEND"
Write-Ok "DATABASE_URL = $env:DATABASE_URL"

if (-not (Test-Path (Join-Path $Root ".env"))) {
    if (Test-Path (Join-Path $Root ".env.example")) {
        Copy-Item (Join-Path $Root ".env.example") (Join-Path $Root ".env")
        Write-Ok "Created .env from .env.example"
    }
}

# --------------------------------------------------------------------------- #
# 3. フロントエンド依存
# --------------------------------------------------------------------------- #

Write-Step "[3/6] Checking frontend dependencies ..."

# node_modules の存在だけでは不十分。.bin\vite.cmd が無いと `npm run dev` が
# "'vite' が内部または外部コマンドとして認識されていません" で即死する
# (install が中断された / node_modules だけ残った状態)。
$needsNpmInstall = $false
if (-not (Test-Path (Join-Path $FrontendDir "node_modules"))) {
    Write-Warn2 "frontend\node_modules is missing."
    $needsNpmInstall = $true
}
elseif (-not (Test-Path (Join-Path $FrontendDir "node_modules\.bin\vite.cmd"))) {
    Write-Warn2 "frontend\node_modules\.bin\vite.cmd is missing - the npm install is incomplete."
    $needsNpmInstall = $true
}

if ($needsNpmInstall) {
    if ($SkipInstall) {
        Write-Err2 "Run 'npm install' in frontend\ or drop -SkipInstall."
        exit 1
    }
    Write-Step "Running npm install (this can take a few minutes) ..."
    Push-Location $FrontendDir
    try {
        $prevEap = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        & npm.cmd install *> $null
        $npmCode = $LASTEXITCODE
        $ErrorActionPreference = $prevEap
        if ($npmCode -ne 0) {
            Write-Err2 "npm install failed in frontend\."
            exit 1
        }
    }
    finally { Pop-Location }
    Write-Ok "frontend dependencies installed"
}
else {
    Write-Ok "frontend dependencies present (node_modules + .bin/vite.cmd)"
}

# --------------------------------------------------------------------------- #
# 4. データベース初期化
# --------------------------------------------------------------------------- #

Write-Step "[4/6] Initializing database (safe migration) ..."
& $PythonExe (Join-Path $ScriptDir "init_db.py")
if ($LASTEXITCODE -ne 0) {
    Write-Err2 "Database initialization failed (scripts\init_db.py)."
    exit 1
}

# --------------------------------------------------------------------------- #
# 5. 起動（または DryRun）
# --------------------------------------------------------------------------- #

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$plan = @(
    "  - Backend : $PythonExe -m uvicorn src.backend.server:app --port $BackendPort",
    "  - Worker  : $PythonExe -m huey.bin.huey_consumer src.backend.tasks.huey.huey",
    "  - Frontend: npm run dev  (cwd: frontend\)"
)

if ($DryRun) {
    Write-Step "[5/6] DryRun - no process will be started."
    Write-Host "  - Backend : uvicorn src.backend.server:app --port $BackendPort" -ForegroundColor Gray
    Write-Host "  - Worker  : huey_consumer src.backend.tasks.huey.huey" -ForegroundColor Gray
    Write-Host "  - Frontend: npm run dev" -ForegroundColor Gray
    Write-Host "  - init_db: scripts\init_db.py" -ForegroundColor Gray
    Write-Host ""
    Write-Host "[DryRun] Done. No processes started." -ForegroundColor Magenta
    exit 0
}

# 既に他のプロセスがポートを掴んでいる場合は先に落とす（多重起動防止）
foreach ($port in @($BackendPort, $FrontendPort)) {
    $listeners = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    if ($listeners) {
        Write-Warn2 "Port $port is already in use; stopping the existing process ..."
        foreach ($l in $listeners) {
            & taskkill /PID $l.OwningProcess /T /F 2>&1 | Out-Null
        }
        Start-Sleep -Milliseconds 800
    }
}

function Start-ServiceProcess {
    # 注: パラメータ名に $Args は使わない。PowerShell の自動変数と衝突して
    #     Start-Process へ null が渡るため。
    param(
        [string]$Name,
        [string]$FilePath,
        [string[]]$ArgList,
        [string]$WorkingDirectory
    )
    $out = Join-Path $LogDir "$Name.log"
    $err = Join-Path $LogDir "$Name.err.log"
    Remove-Item $out, $err -ErrorAction SilentlyContinue
    $p = Start-Process -FilePath $FilePath -ArgumentList $ArgList `
        -WorkingDirectory $WorkingDirectory -PassThru `
        -RedirectStandardOutput $out -RedirectStandardError $err -NoNewWindow
    Write-Ok ("{0,-9} pid={1,-7} log={2}" -f $Name, $p.Id, $out)
    return @{ Name = $Name; Proc = $p; Out = $out; Err = $err }
}

function Show-ServiceLogTail {
    param($Service, [int]$Lines = 30)
    foreach ($file in @($Service.Out, $Service.Err)) {
        if ((Test-Path $file) -and (Get-Item $file).Length -gt 0) {
            Write-Host "--- $(Split-Path $file -Leaf) (last $Lines lines) ---" -ForegroundColor DarkYellow
            Get-Content $file -Tail $Lines | ForEach-Object { Write-Host "    $_" -ForegroundColor DarkGray }
        }
    }
}

Write-Step "[5/6] Starting services ..."
$services = @()

$services += Start-ServiceProcess -Name "backend" `
    -FilePath $PythonExe `
    -ArgList @("-m", "uvicorn", "src.backend.server:app", "--host", "127.0.0.1", "--port", "$BackendPort") `
    -WorkingDirectory $Root

if (-not $NoWorker) {
    $services += Start-ServiceProcess -Name "worker" `
        -FilePath $PythonExe `
        -ArgList @("-m", "huey.bin.huey_consumer", "src.backend.tasks.huey.huey") `
        -WorkingDirectory $Root
}

$services += Start-ServiceProcess -Name "frontend" `
    -FilePath "npm.cmd" `
    -ArgList @("run", "dev", "--", "--port", "$FrontendPort", "--strictPort") `
    -WorkingDirectory $FrontendDir

# stop_local.ps1 が確実に止められるよう PID を残す
($services | ForEach-Object { "$($_.Name)=$($_.Proc.Id)" }) -join "`n" |
    Set-Content -Path $PidFile -Encoding UTF8
Write-Ok "PID file: $PidFile"

# --------------------------------------------------------------------------- #
# 6. 準備完了待ち（ヘルスチェック）
# --------------------------------------------------------------------------- #

function Test-HttpOk {
    param([string]$Url, [int]$TimeoutSec = 3)
    try {
        $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec $TimeoutSec
        return ($r.StatusCode -ge 200 -and $r.StatusCode -lt 400)
    }
    catch { return $false }
}

Write-Step "[6/6] Waiting for services to become ready (timeout: ${ReadyTimeoutSec}s) ..."
$deadline = (Get-Date).AddSeconds($ReadyTimeoutSec)
$backendReady = $false
$frontendReady = $false

while ((Get-Date) -lt $deadline) {
    foreach ($svc in $services) {
        if ($svc.Proc.HasExited) {
            Write-Err2 "$($svc.Name) exited unexpectedly (code $($svc.Proc.ExitCode))."
            Show-ServiceLogTail -Service $svc
            Write-Host ""
            Write-Host "  Run 'powershell -ExecutionPolicy Bypass -File scripts\doctor.ps1' for a full diagnosis." -ForegroundColor Yellow
            foreach ($s in $services) {
                if (-not $s.Proc.HasExited) { & taskkill /PID $s.Proc.Id /T /F 2>&1 | Out-Null }
            }
            Remove-Item $PidFile -ErrorAction SilentlyContinue
            exit 1
        }
    }

    if (-not $backendReady -and (Test-HttpOk "http://127.0.0.1:$BackendPort/health")) {
        $backendReady = $true
        Write-Ok "Backend is ready  -> http://localhost:$BackendPort"
    }
    if (-not $frontendReady -and (Test-HttpOk "http://127.0.0.1:$FrontendPort/")) {
        $frontendReady = $true
        Write-Ok "Frontend is ready -> http://localhost:$FrontendPort"
    }
    if ($backendReady -and $frontendReady) { break }
    Start-Sleep -Seconds 2
}

Write-Host ""
if ($backendReady) { Write-Ok "Backend  : http://localhost:$BackendPort  (docs: /docs)" -ForegroundColor Green }
else { Write-Err2 "Backend did not become ready. Check logs\backend.err.log" }
if ($frontendReady) { Write-Ok "Frontend : http://localhost:$FrontendPort" -ForegroundColor Green }
else { Write-Err2 "Frontend did not become ready. Check logs\frontend.err.log" }

if ($backendReady -and $frontendReady -and -not $NoBrowser) {
    Start-Process "http://localhost:$FrontendPort" | Out-Null
}

Write-Host ""
Write-Host "Logs     : $LogDir\backend.log | worker.log | frontend.log" -ForegroundColor DarkGray
Write-Host "Stop     : run アプリ停止.bat  (or scripts\stop_local.ps1)" -ForegroundColor DarkGray
Write-Host "Press Ctrl+C to stop all services." -ForegroundColor Yellow
Write-Host ""

# --------------------------------------------------------------------------- #
# 監視ループ
# --------------------------------------------------------------------------- #

try {
    while ($true) {
        Start-Sleep -Seconds 5
        foreach ($svc in $services) {
            if ($svc.Proc.HasExited) {
                Write-Err2 "$($svc.Name) stopped unexpectedly. Last log lines:"
                Show-ServiceLogTail -Service $svc
                throw "service $($svc.Name) exited"
            }
        }
    }
}
finally {
    Write-Host ""
    Write-Step "Stopping all services ..."
    foreach ($svc in $services) {
        if ($svc.Proc -and -not $svc.Proc.HasExited) {
            & taskkill /PID $svc.Proc.Id /T /F 2>&1 | Out-Null
        }
    }
    Remove-Item $PidFile -ErrorAction SilentlyContinue
    Write-Ok "All services stopped."
}
