# AutoNovel 起動診断 (Doctor)
#
# 起動できないときに「どこがおかしいか」を 1 回の実行で特定する。
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts/doctor.ps1
#   powershell -ExecutionPolicy Bypass -File scripts/doctor.ps1 -Deep   (import 時間まで計測)
#
# 終了コード: 0 = 起動可能 / 1 = 問題あり

param(
    [switch]$Deep
)

$ErrorActionPreference = "Continue"
$ScriptDir = $PSScriptRoot
$Root = Split-Path $ScriptDir -Parent
Set-Location $Root

$script:problems = New-Object System.Collections.Generic.List[string]
$script:warnings = New-Object System.Collections.Generic.List[string]

function Section($title) {
    Write-Host ""
    Write-Host "== $title " -ForegroundColor Cyan -NoNewline
    Write-Host ("=" * [Math]::Max(0, 60 - $title.Length)) -ForegroundColor DarkCyan
}
function Ok($msg) { Write-Host "  [OK]   $msg" -ForegroundColor Green }
function Warn($msg) { Write-Host "  [WARN] $msg" -ForegroundColor Yellow; $script:warnings.Add($msg) | Out-Null }
function Bad($msg) { Write-Host "  [FAIL] $msg" -ForegroundColor Red; $script:problems.Add($msg) | Out-Null }
function Info($msg) { Write-Host "         $msg" -ForegroundColor DarkGray }

Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "        AutoNovel - Startup Doctor                     " -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan
Info "root: $Root"

# --------------------------------------------------------------------------- #
Section "1. Project layout"
# --------------------------------------------------------------------------- #
foreach ($p in @(
        @{ n = "pyproject.toml"; p = "pyproject.toml" },
        @{ n = ".env"; p = ".env" },
        @{ n = ".env.example"; p = ".env.example" },
        @{ n = "alembic.ini"; p = "alembic.ini" },
        @{ n = "src/backend/server.py"; p = "src\backend\server.py" },
        @{ n = "src/backend/tasks/huey.py"; p = "src\backend\tasks\huey.py" },
        @{ n = "frontend/package.json"; p = "frontend\package.json" },
        @{ n = "autonovel.db"; p = "autonovel.db" })) {
    if (Test-Path $p.p) { Ok $p.n }
    else { Bad ("missing: " + $p.n) }
}

# npm install は中断されやすく、node_modules が残っても .bin が欠けると
# `npm run dev` が "'vite' が認識されていません" で即死する。
if (Test-Path "frontend\node_modules") {
    if (Test-Path "frontend\node_modules\.bin\vite.cmd") { Ok "frontend/node_modules/.bin/vite.cmd" }
    else {
        Bad "frontend/node_modules/.bin/vite.cmd is missing - the npm install is incomplete"
        Info "fix: cd frontend && npm install"
    }
}
else {
    Bad "frontend/node_modules is missing"
    Info "fix: cd frontend && npm install  (or run アプリ起動_ローカル.bat without -SkipInstall)"
}

# --------------------------------------------------------------------------- #
Section "2. Toolchain"
# --------------------------------------------------------------------------- #
$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
$pyCmd = Get-Command py -ErrorAction SilentlyContinue
$nodeCmd = Get-Command node -ErrorAction SilentlyContinue
$npmCmd = Get-Command npm -ErrorAction SilentlyContinue

if ($pythonCmd) { Ok "python : $($pythonCmd.Source)"; Info (& $pythonCmd.Source --version 2>&1) }
elseif ($pyCmd) { Ok "py     : $($pyCmd.Source)" }
else { Bad "no python / py launcher found" }

if ($nodeCmd) { Ok "node   : $($nodeCmd.Source)"; Info (& $nodeCmd.Source --version 2>&1) }
else { Bad "node not found (frontend dev server needs it)" }

if ($npmCmd) { Ok "npm    : $($npmCmd.Source)" }
else { Bad "npm not found" }

# --------------------------------------------------------------------------- #
Section "3. Python candidates (which one can actually start the backend?)"
# --------------------------------------------------------------------------- #
$required = @("fastapi", "uvicorn", "huey", "sqlalchemy", "alembic", "pydantic")
$usable = $null
$broken = New-Object System.Collections.Generic.List[string]

$candidates = @()
if (Test-Path ".venv\Scripts\python.exe") { $candidates += ,@{ Label = ".venv"; Exe = (Resolve-Path ".venv\Scripts\python.exe").Path } }
if ($pythonCmd) { $candidates += ,@{ Label = "PATH python"; Exe = $pythonCmd.Source } }
if ($pyCmd) { $candidates += ,@{ Label = "py launcher"; Exe = $pyCmd.Source } }

foreach ($c in $candidates) {
    $ver = (& $c.Exe -c "import sys;print(sys.version.split()[0])" 2>&1)
    $ver = ($ver | Select-Object -Last 1)

    # 重要: $LASTEXITCODE は次のコマンドを実行した時点で上書きされる。
    # import できるか判定するには、直後に値を控えておく。
    $missing = @()
    foreach ($m in $required) {
        & $c.Exe -c "import $m" 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) { $missing += $m }
    }

    if ($missing.Count -eq 0) {
        Ok ("{0,-12} {1}  -> usable" -f $c.Label, $ver)
        if (-not $usable) { $usable = $c }
    }
    else {
        # 壊れた候補は一旦控えておき、他の Python が使えるかどうかを見てから
        # 警告 / 致命的な問題 に振り分ける（先に評価した候補を Bad にすると、
        # 後ろに使える Python があっても全体会因为で誤検知する）。
        $broken.Add(("{0,-12} {1}  -> missing: {2}" -f $c.Label, $ver, ($missing -join ", "))) | Out-Null
    }
}

foreach ($line in $broken) {
    if ($usable) { Warn $line }
    else { Bad $line }
}

if (-not $candidates.Count) { Bad "no python interpreter found" }
if ($usable) {
    Ok "launcher will use: $($usable.Exe) [$($usable.Label)]"
    if ($broken.Count -gt 0) {
        Info "start_local.ps1 will skip the broken candidate(s) above automatically."
    }
}
else {
    Bad "no interpreter can import the backend dependencies"
    Info 'fix: .venv\Scripts\python.exe -m pip install -e ".[dev]"   (or: py -m pip install -e ".[dev]")'
    Info "or  : start_local.ps1 (without -SkipInstall) creates/repairs .venv automatically"
    Info "or  : start_local.ps1 -RecreateVenv"
}

# --------------------------------------------------------------------------- #
Section "4. Configuration (.env)"
# --------------------------------------------------------------------------- #
if (Test-Path ".env") {
    $envLines = Get-Content ".env" -ErrorAction SilentlyContinue
    Info ("{0} keys defined" -f ($envLines | Where-Object { $_ -match '^\s*[A-Za-z_][A-Za-z0-9_]*\s*=' }).Count)

    $appEnv = ($envLines | Where-Object { $_ -match '^\s*APP_ENV\s*=' }) -replace '^\s*APP_ENV\s*=\s*', ''
    Info "APP_ENV = $appEnv"

    $placeholder = $envLines | Where-Object {
        $_ -match '^\s*(GEMINI_API_KEY|OPENAI_API_KEY|ANTHROPIC_API_KEY)\s*=\s*(your_.*|changeme.*|)$'
    }
    if ($placeholder) {
        Warn "API keys are still placeholders - AI features will return 403 at runtime"
        foreach ($p in $placeholder) { Info $p }
    }

    # .env に無いキーは extra='ignore' で黙って捨てられる
    $configPy = "src\backend\config.py"
    if (Test-Path $configPy) {
        $known = (Select-String -Path $configPy -Pattern '^\s{4}([A-Z][A-Z0-9_]+):' -AllMatches).Matches |
        ForEach-Object { $_.Groups[1].Value }
        $defined = $envLines | Where-Object { $_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=' } |
        ForEach-Object { ($_ -split '=')[0].Trim() }
        $unknown = $defined | Where-Object { $_ -notin $known -and $_ -notmatch '^(POSTGRES_|VITE_|CORS_)' } | Sort-Object -Unique
        if ($unknown) {
            Warn "these .env keys do not exist in src/backend/config.py and are ignored:"
            Info ($unknown -join ", ")
        }
    }
}
else {
    Warn ".env not found - copy .env.example to .env"
}

# --------------------------------------------------------------------------- #
Section "5. Database"
# --------------------------------------------------------------------------- #
if (Test-Path "autonovel.db") {
    $sizeMB = [math]::Round((Get-Item "autonovel.db").Length / 1MB, 2)
    Ok "autonovel.db exists ($sizeMB MB)"
    try {
        Add-Type -AssemblyName System.Data.SQLite -ErrorAction SilentlyContinue
    }
    catch { }
    foreach ($sidecar in @("autonovel.db-wal", "autonovel.db-shm")) {
        if (Test-Path $sidecar) { Info "$sidecar present (WAL mode active)" }
    }
}
else {
    Warn "autonovel.db not found - it will be created by scripts\init_db.py on first start"
}

if (Test-Path "alembic.ini") {
    $versions = @(Get-ChildItem "src\backend\alembic\versions" -Filter "*.py" -ErrorAction SilentlyContinue)
    Ok "alembic migrations: $($versions.Count) files"
    if ($usable) {
        $rev = & $usable.Exe -c "import sys; sys.path.insert(0,'.'); from alembic.config import Config; from alembic.script import ScriptDirectory; s=ScriptDirectory.from_config(Config('alembic.ini')); print(s.get_current_head())" 2>&1
        Info "head revision: $rev"
    }
}

# --------------------------------------------------------------------------- #
Section "6. Ports and stray processes"
# --------------------------------------------------------------------------- #
$anyRunning = $false
foreach ($port in @(8200, 5173)) {
    $c = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    if ($c) {
        Warn "port $port is in use by PID $($c[0].OwningProcess) - start_local.ps1 will stop it, or run アプリ停止.bat first"
        $anyRunning = $true
    }
    else { Ok "port $port free" }
}

$strays = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
    $_.CommandLine -and (
        $_.CommandLine -match "huey_consumer" -or
        ($_.CommandLine -match "uvicorn" -and $_.CommandLine -match "src\.backend\.server") -or
        ($_.CommandLine -match "vite" -and $_.CommandLine -match "autonovel")
    )
}
if ($strays) {
    Warn "AutoNovel processes already running:"
    foreach ($s in $strays) { Info ("PID {0}: {1}" -f $s.ProcessId, $s.Name) }
    Info "stop them with: アプリ停止.bat"
}
elseif (-not $anyRunning) {
    Ok "no AutoNovel processes running"
}

# --------------------------------------------------------------------------- #
Section "7. Machine resources (startup speed depends heavily on these)"
# --------------------------------------------------------------------------- #
$os = Get-CimInstance Win32_OperatingSystem
$freeGB = [math]::Round($os.FreePhysicalMemory / 1MB, 2)
$totalGB = [math]::Round($os.TotalVisibleMemorySize / 1MB, 2)
if ($freeGB -lt 0.8) { Bad "free RAM is only ${freeGB}GB / ${totalGB}GB - the backend cannot import (MemoryError)" }
elseif ($freeGB -lt 2.0) { Warn "free RAM is only ${freeGB}GB / ${totalGB}GB - the backend may die with MemoryError. Close other apps or enable the system-managed pagefile." }
elseif ($freeGB -lt 4.0) { Warn "free RAM is ${freeGB}GB / ${totalGB}GB - startup may be slow" }
else { Ok "free RAM ${freeGB}GB / ${totalGB}GB" }

# ルートがネットワーク/外付けドライブにないかを確認する
# (import ~2300 モジュールは I/O 拘束なので、USB HDD 上では起動が数十秒〜数分かかる)
$driveLetter = ""
try { $driveLetter = [IO.Path]::GetPathRoot($Root).TrimEnd('\').TrimEnd(':') } catch { $driveLetter = "" }

if ($driveLetter) {
    $disk = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='$($driveLetter):'" -ErrorAction SilentlyContinue
    if ($disk) {
        $freeGBd = [math]::Round($disk.FreeSpace / 1GB, 1)
        if ($freeGBd -lt 5) { Bad "free disk space on ${driveLetter}: is only ${freeGBd}GB" }
        else { Ok "free disk space on ${driveLetter}: ${freeGBd}GB" }
    }

    $partition = Get-Partition -DriveLetter $driveLetter -ErrorAction SilentlyContinue
    if ($partition) {
        $physical = Get-Disk -Number $partition.DiskNumber -ErrorAction SilentlyContinue
        if ($physical) {
            Info "project drive ${driveLetter}: -> $($physical.FriendlyName) (BusType=$($physical.BusType), MediaType=$($physical.MediaType))"
            if ($physical.BusType -eq "USB" -or $physical.BusType -eq "SD" -or $physical.BusType -eq "MMC") {
                Warn "the project lives on a $($physical.BusType) device - importing ~2300 modules from it is the main cause of slow startup"
                Info "copying the repository to the internal SSD makes startup several times faster."
            }
        }
    }
}
$cs = Get-CimInstance Win32_ComputerSystem
if (-not $cs.AutomaticManagedPagefile) {
    Warn "Windows pagefile is fixed (automatic management off) - MemoryError is more likely under load"
}

$pyCount = (Get-ChildItem "src" -Recurse -File -Filter "*.py" -ErrorAction SilentlyContinue).Count
$pycCount = (Get-ChildItem "src" -Recurse -File -Filter "*.pyc" -ErrorAction SilentlyContinue).Count
if ($pycCount -lt $pyCount) {
    Warn "byte-compiled cache incomplete ($pycCount / $pyCount .pyc) - first import is slow"
    Info "fix: python -m compileall -q src"
}
else {
    Ok "byte-compiled cache complete ($pycCount .pyc)"
}

# --------------------------------------------------------------------------- #
Section "8. Frontend"
# --------------------------------------------------------------------------- #
$viteConfig = "frontend\vite.config.ts"
if (Test-Path $viteConfig) {
    $text = Get-Content $viteConfig -Raw
    if ($text -match "port\s*:\s*(\d+)") { Info "vite configured port: $($Matches[1])" }
    if ($text -match "proxy" -or $text -match "8200") { Ok "vite proxy to the backend is configured" }
    else { Warn "vite.config.ts does not appear to proxy /api to :8200 - the UI may not reach the backend" }
}
else {
    Warn "frontend/vite.config.ts not found"
}

# --------------------------------------------------------------------------- #
Section "9. Startup smoke test"
# --------------------------------------------------------------------------- #
if ($usable -and -not $script:problems.Count) {
    $env:PYTHONPATH = $Root
    $env:HUEY_BACKEND = "sqlite"
    $env:DATABASE_URL = "sqlite:///./autonovel.db"

    Info "importing src.backend.server (this is the bulk of startup time) ..."
    $sw = [Diagnostics.Stopwatch]::StartNew()
    $probe = & $usable.Exe -c "import src.backend.server as s; print(len(s.app.routes))" 2>&1
    $sw.Stop()
    if ($LASTEXITCODE -eq 0) {
        Ok ("import ok in {0:N1}s, {1} routes" -f $sw.Elapsed.TotalSeconds, ($probe | Select-Object -Last 1))
        if ($sw.Elapsed.TotalSeconds -gt 20) {
            Warn ("startup is slow ({0:N1}s). Check section 7." -f $sw.Elapsed.TotalSeconds)
        }
    }
    else {
        Bad "importing src.backend.server failed"
        $probe | Select-Object -Last 20 | ForEach-Object { Info $_ }
    }
}
elseif ($usable) {
    Warn "skipped because earlier checks failed"
}
else {
    Warn "skipped because no usable Python was found"
}

if ($Deep) {
    Section "10. Heavy SDK import analysis"
    if ($usable) {
        $script = Join-Path $ScriptDir "debug\trace_heavy_imports.py"
        if (Test-Path $script) {
            & $usable.Exe $script 2>&1 | Where-Object { $_ -notmatch "DeprecationWarning|_real_import" } | ForEach-Object { Info $_ }
        }
        else { Warn "scripts\debug\trace_heavy_imports.py not found" }
    }
}

# --------------------------------------------------------------------------- #
Write-Host ""
Write-Host "========================================================" -ForegroundColor Cyan
if ($script:problems.Count -eq 0) {
    Write-Host " RESULT: ready to start ($($script:warnings.Count) warning(s))" -ForegroundColor Green
}
else {
    Write-Host " RESULT: $($script:problems.Count) problem(s) found" -ForegroundColor Red
    foreach ($p in $script:problems) { Write-Host "   - $p" -ForegroundColor Red }
}
foreach ($w in $script:warnings) { Write-Host "   ! $w" -ForegroundColor Yellow }
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host " next:  アプリ起動_ローカル.bat    (start everything)" -ForegroundColor Gray
Write-Host "        アプリ停止.bat            (stop everything)" -ForegroundColor Gray
Write-Host "        Docker  : アプリ起動.bat  (postgres + redis + chroma)" -ForegroundColor Gray

if ($script:problems.Count -gt 0) { exit 1 }
exit 0
