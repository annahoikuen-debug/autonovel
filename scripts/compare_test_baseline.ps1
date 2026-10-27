<#
.SYNOPSIS
    テスト回帰ベースライン自動比較スクリプト（Plan V53-V6 Step 5）。

.DESCRIPTION
    本リポジトリは HEAD 時点で既に約 130 件の失敗/エラーが既存する。
    そのため「失敗件数そのもの」は情報を持たず、**何を追加したか**だけが
    意味を持つ。本スクリプトは次の手順で新規回帰（regression）だけを列挙する。

      1. HEAD の git worktree を一時ディレクトリに detach 作成する（baseline）。
      2. 同一の pytest セレクションを baseline と現行ツリーの両方で実行する。
      3. 両実行の FAILED / ERROR ノードID集合の差分を取る。
      4. 「現行にのみ存在し baseline には無い」テスト = 新規回帰 のみを列挙する。
         1 件でもあれば終了コード 1、無ければ 0 で終了する。
      5. 一時 worktree は `finally` ブロックで必ず削除する
         （エラー・Ctrl-C・途中失敗のいずれでも残さない）。

    再実行可能（冪等）: worktree パスは GUID を含む一時ディレクトリであり、
    実行開始時に `git worktree prune` を実行するため、前回の中断残骸も回収される。

.PARAMETER Selection
    実行する pytest セレクション（既定は主要ディレクトリ一式）。
    例: -Selection "tests/unit tests/services" / -Selection "tests/regression"

.PARAMETER SkipBaseline
    baseline worktree を作らず、現行ツリーのみを実行する。
    差分は出せないが失败ノードIDを一覧表示し、素早い手元チェックに使える。
    この場合 신규回帰は常に 0 件扱い（終了コード 0）で終了する。

.PARAMETER PythonExe
    pytest 実行に使う Python 実行ファイル。
    既定は環境変数 AUTONOVEL_PYTHON、无ければ C:\Python314\python.exe、、
    さらに無ければ `py` ラUNCHER を使う。

.EXAMPLE
    pwsh -File scripts/compare_test_baseline.ps1

.EXAMPLE
    # 差分取らず現行のみ高速確認（数分で終わる）
    pwsh -File scripts/compare_test_baseline.ps1 -SkipBaseline -Selection "tests/perf"

.EXAMPLE
    # 全体をベースライン比較（約 8 分 x 2）
    pwsh -File scripts/compare_test_baseline.ps1
#>

[CmdletBinding()]
param(
    [string]$Selection = "tests/unit tests/services tests/models tests/integration tests/regression tests/e2e",
    [switch]$SkipBaseline,
    [string]$PythonExe = ""
)

$ErrorActionPreference = "Stop"

# ---------------------------------------------------------------------------
# 環境準備
# ---------------------------------------------------------------------------

$RepoRoot = Split-Path -Parent $PSScriptRoot
Push-Location $RepoRoot

function Resolve-PythonExe {
    param([string]$Preferred)
    if ($Preferred) { return $Preferred }
    if ($env:AUTONOVEL_PYTHON) { return $env:AUTONOVEL_PYTHON }
    if (Test-Path "C:\Python314\python.exe") { return "C:\Python314\python.exe" }
    return "py"
}

$Py = Resolve-PythonExe -Preferred $PythonExe
# 日本語出力を PowerShell のコンソールで化けさせない
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"

# 実行ログの一時置き場（baseline を作らない場合にも使う）
$LogDir = Join-Path ([System.IO.Path]::GetTempPath()) ("autonovel-testcmp-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $LogDir -Force | Out-Null

$WorktreePath = Join-Path ([System.IO.Path]::GetTempPath()) ("autonovel-baseline-" + [guid]::NewGuid().ToString("N"))
$WorktreeCreated = $false

# ---------------------------------------------------------------------------
# pytest 実行と結果パース
# ---------------------------------------------------------------------------

function Invoke-PytestRun {
    <#
      対象ディレクトリで pytest を実行し、{ ノードID -> 'FAILED'|'ERROR' } を返す。
      結果の判定は pytest の短い要約（-rfE）にある FAILED/ERROR 行から取る。
      collection error も ERROR 行として出るので取りこぼさない。
    #>
    param(
        [Parameter(Mandatory)][string]$WorkDir,
        [Parameter(Mandatory)][string]$Label,
        [Parameter(Mandatory)][string]$LogFile
    )

    Write-Host "==> [$Label] pytest 実行: $Selection" -ForegroundColor Cyan
    Write-Host "    作業ディレクトリ: $WorkDir"

    $pytestArgs = @("-m", "pytest") +
                  @($Selection.Split(" ") | Where-Object { $_ }) +
                  @("-q", "--tb=no", "-rfE", "-p", "no:randomly", "--color=no")

    Push-Location $WorkDir
    try {
        # 出力をファイルに残しつつ画面にも出す（tee 相当）。
        # NOTE: Out-Host でパイプラインを消費しないと、tee の出力自体が
        #       関数の戻り値に混ざって hashtable が壊れる。
        & $Py @pytestArgs 2>&1 | Tee-Object -FilePath $LogFile | Out-Host
        $exitCode = $LASTEXITCODE
    } catch {
        Write-Host "    pytest 実行例外: $_" -ForegroundColor Red
        $exitCode = 1
    } finally {
        Pop-Location
    }

    # 短い要約から FAILED / ERROR を抽出（ANSI エスケープは除去してから照合する）
    $failures = @{}
    if (Test-Path $LogFile) {
        foreach ($raw in (Get-Content -LiteralPath $LogFile -Encoding UTF8)) {
            $line = $raw -replace "`e\[[0-9;]*[A-Za-z]", ""
            if ($line -match '^(FAILED|ERROR)\s+(\S+)') {
                $failures[$Matches[2]] = $Matches[1]
            }
        }
    }

    Write-Host ("    終了コード {0} / 失敗・エラー {1} 件" -f $exitCode, $failures.Count) -ForegroundColor Yellow
    return $failures
}

# ---------------------------------------------------------------------------
# メイン処理（worktree _cleanup は必ず finally で行う）
# ---------------------------------------------------------------------------

try {
    # 残存した作業ツリー情報（前回の中断分）を掃除してから開始する
    & git -C $RepoRoot worktree prune 2>&1 | Out-Null

    if (-not (Test-Path (Join-Path $RepoRoot ".git"))) {
        throw "git リポジトリではありません: $RepoRoot"
    }

    if ($SkipBaseline) {
        # ---- 現行ツリーのみ実行モード ----
        $currentFailures = Invoke-PytestRun -WorkDir $RepoRoot -Label "current" `
            -LogFile (Join-Path $LogDir "current.log")

        Write-Host "`n---- 現行ツリーの失敗一覧 (-SkipBaseline なので差分なし) ----" -ForegroundColor Cyan
        if ($currentFailures.Count -eq 0) {
            Write-Host "    （なし）"
        } else {
            $currentFailures.GetEnumerator() | Sort-Object Name | ForEach-Object {
                Write-Host ("    {0} {1}" -f $_.Value, $_.Name)
            }
        }
        Write-Host "`n新規回帰: 0 件（ベースライン未実行のため判定しない）" -ForegroundColor Green
        exit 0
    }

    # ---- baseline worktree 作成 ----
    Write-Host "==> baseline worktree を作成: $WorktreePath" -ForegroundColor Cyan
    & git -C $RepoRoot worktree add $WorktreePath HEAD --detach 2>&1 | Write-Host
    if ($LASTEXITCODE -ne 0) {
        throw "git worktree add に失敗しました（パス衝突や未コミットの submodule を疑ってください）"
    }
    $WorktreeCreated = $true

    # ---- 両方で実行 ----
    $baselineFailures = Invoke-PytestRun -WorkDir $WorktreePath -Label "baseline (HEAD)" `
        -LogFile (Join-Path $LogDir "baseline.log")
    $currentFailures = Invoke-PytestRun -WorkDir $RepoRoot -Label "current (作業ツリー)" `
        -LogFile (Join-Path $LogDir "current.log")

    # ---- 差分抽出 ----
    $newRegressions = @()
    $fixed = @()
    foreach ($nodeId in $currentFailures.Keys) {
        if (-not $baselineFailures.ContainsKey($nodeId)) { $newRegressions += $nodeId }
    }
    foreach ($nodeId in $baselineFailures.Keys) {
        if (-not $currentFailures.ContainsKey($nodeId)) { $fixed += $nodeId }
    }
    $newRegressions = $newRegressions | Sort-Object
    $fixed = $fixed | Sort-Object

    Write-Host "`n===================== 回帰ベースライン比較 =====================" -ForegroundColor Cyan
    Write-Host ("  baseline (HEAD) 失敗: {0} 件" -f $baselineFailures.Count)
    Write-Host ("  current           失敗: {0} 件" -f $currentFailures.Count)
    Write-Host ("  解消された失敗     : {0} 件" -f $fixed.Count)
    Write-Host ("  新規回帰（新出）  : {0} 件" -f $newRegressions.Count)

    if ($fixed.Count -gt 0) {
        Write-Host "`n---- 解消された失敗（参考・失敗扱いはしない） ----" -ForegroundColor DarkGray
        $fixed | ForEach-Object { Write-Host ("    [fixed] {0}" -f $_) -ForegroundColor DarkGray }
    }

    Write-Host "`n---- 新規回帰のみ ----" -ForegroundColor Cyan
    if ($newRegressions.Count -eq 0) {
        Write-Host "    新規回帰なし" -ForegroundColor Green
    } else {
        foreach ($nodeId in $newRegressions) {
            Write-Host ("    {0} {1}" -f $currentFailures[$nodeId], $nodeId) -ForegroundColor Red
        }
    }
    Write-Host "===============================================================" -ForegroundColor Cyan

    if ($newRegressions.Count -gt 0) {
        exit 1
    }
    exit 0

} finally {
    # ---------------------------------------------------------------------------
    # 後始末: エラー・Ctrl-C・途中終了のいずれでも必ず一時 worktree を消す
    # ---------------------------------------------------------------------------
    if ($WorktreeCreated) {
        Write-Host "`n==> 一時 worktree を削除: $WorktreePath" -ForegroundColor Cyan
        & git -C $RepoRoot worktree remove --force $WorktreePath 2>&1 | Write-Host
        if ($LASTEXITCODE -ne 0) {
            # 消せなかった場合は登録情報を外，至少 `git worktree prune` で回収できるようにする
            & git -C $RepoRoot worktree prune 2>&1 | Out-Null
        }
    }
    if (Test-Path $LogDir) {
        Remove-Item -LiteralPath $LogDir -Recurse -Force -ErrorAction SilentlyContinue
    }
    Pop-Location
}
