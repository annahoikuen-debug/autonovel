<#
.SYNOPSIS
    AutoNovel スモークテスト - 起動済みバックエンドに対して基本エンドポイントを叩く。

.DESCRIPTION
    バックエンドが起動済みの前提で以下を検証:
      1. GET /health                          -> 200 + status ok
      2. POST /easy_mode/generate             -> 200 + suggestions にタスク ID
      3. GET /easy_mode/status/{task_id}       -> 200 + status フィールド存在
      4. GET /easy_mode/export/0              -> 422 (バリデーション)
      5. GET /easy_mode/export/1              -> 200 または 404 (DB 状態依存、500 は禁止)

    いずれかが期待外の場合は非ゼロで終了。CI のデプロイ後検証にも利用可。

.PARAMETER BaseUrl
    バックエンドの BASE URL (既定: http://localhost:8200)

.EXAMPLE
    .\scripts\smoke_test.ps1
    .\scripts\smoke_test.ps1 -BaseUrl http://localhost:8200
#>

[CmdletBinding()]
param(
    [string]$BaseUrl = "http://localhost:8200"
)

$ErrorActionPreference = "Stop"
$overallOk = $true

function Invoke-Check {
    param(
        [string]$Name,
        [scriptblock]$Action,
        [scriptblock]$Assert
    )
    Write-Host "==> $Name" -ForegroundColor Cyan
    try {
        $result = & $Action
        $ok = & $Assert $result
        if ($ok) {
            Write-Host "    PASS" -ForegroundColor Green
        } else {
            Write-Host "    FAIL" -ForegroundColor Red
            $script:overallOk = $false
        }
    } catch {
        Write-Host "    ERROR: $_" -ForegroundColor Red
        $script:overallOk = $false
    }
}

# HTTP ステータスコードを 5.1 でも例外にせず取得するヘルパー。
#
# 注意: Windows PowerShell 5.1（.bat ランチャーが呼ぶ powershell.exe）には
# Invoke-WebRequest の -SkipHttpErrorCheck パラメータが存在しない。5.1 では
# 4xx/5xx が terminating error になり、$ErrorActionPreference = "Stop" の下では
# try/catch で捕まえない限りスクリプト全体が中断する。PowerShell 7 の
# -SkipHttpErrorCheck は 5.1 では「A parameter cannot be found」として解釈され、
# 健全なアプリに対しても FAIL を報告してしまう。
#
# 5.1 では 4xx/5xx が WebException として投げられ、Response に
# [System.Net.HttpStatusCode] が入る。接続不能など真の障害は Response が無いか
# Response が無いので、再送出せず呼び出し側の catch に委ねる。
# -UseBasicParsing は 5.1 で IE ベースの DOM パーサ起動を避けるために必須。
function Get-HttpStatusCode {
    param(
        [Parameter(Mandatory = $true)][string]$Uri
    )
    try {
        $resp = Invoke-WebRequest -Uri $Uri -Method GET -TimeoutSec 5 -UseBasicParsing
        return [int]$resp.StatusCode
    } catch [System.Net.WebException] {
        $code = $null
        if ($_.Exception.Response -ne $null) {
            $code = [int]$_.Exception.Response.StatusCode
        }
        if ($code -ne $null) { return $code }
        throw
    } catch {
        # WebException 以外（DNS 失敗・タイムアウト等）は真の障害として再送出する。
        # 黙って FAIL 扱いにすると「接続できない」を「500 が返った」と取り違えるため、必ず再送出する。
        throw
    }
}

# 1. /health
Invoke-Check "GET /health" {
    Invoke-RestMethod -Uri "$BaseUrl/health" -Method GET -TimeoutSec 5
} {
    param($r)
    $r.status -eq "ok"
}

# 2. /easy_mode/generate
$taskId = $null
Invoke-Check "POST /easy_mode/generate" {
    $body = @{
        current_chapter         = "煙が晴れると、怪物が姿を現した。"
        chapter_history         = @()
        character_params       = @{}
        content_length_limit   = 2000
    } | ConvertTo-Json -Depth 3
    Invoke-RestMethod -Uri "$BaseUrl/easy_mode/generate" -Method POST -Body $body -ContentType "application/json" -TimeoutSec 5
} {
    param($r)
    if (-not $r.suggestions) { return $false }
    $joined = ($r.suggestions -join " ")
    if ($joined -match "/easy_mode/status/(\d+)") {
        $script:taskId = $Matches[1]
        return $true
    }
    return $false
}

# 3. /easy_mode/status/{task_id}
if ($taskId) {
    Invoke-Check "GET /easy_mode/status/$taskId" {
        Invoke-RestMethod -Uri "$BaseUrl/easy_mode/status/$taskId" -Method GET -TimeoutSec 5
    } {
        param($r)
        $r.task_id -eq $taskId -and $null -ne $r.status
    }
}

# 4. /easy_mode/export/0 (422)
Invoke-Check "GET /easy_mode/export/0 (expect 422)" {
    Get-HttpStatusCode -Uri "$BaseUrl/easy_mode/export/0"
} {
    param($r)
    $r -eq 422
}

# 5. /easy_mode/export/1 (200 or 404, but not 500)
Invoke-Check "GET /easy_mode/export/1 (expect 200/404, never 500)" {
    Get-HttpStatusCode -Uri "$BaseUrl/easy_mode/export/1"
} {
    param($r)
    $r -eq 200 -or $r -eq 404
}

if ($overallOk) {
    Write-Host "`nSmoke test PASSED." -ForegroundColor Green
    exit 0
} else {
    Write-Host "`nSmoke test FAILED." -ForegroundColor Red
    exit 1
}
