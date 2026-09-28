@echo off
rem ===========================================================================
rem  AutoNovel ローカル起動
rem  Backend (8200) + Huey Worker + Frontend (5173) を起動します。
rem
rem  起動できないときは 起動診断.bat を先に実行してください。
rem ===========================================================================
setlocal
cd /d "%~dp0"
chcp 65001 > nul
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\start_local.ps1" %*
echo.
echo ------------------------------------------------------------
echo  停止するには「アプリ停止.bat」を実行するか、このウィンドウを閉じてください。
echo ------------------------------------------------------------
pause
endlocal
