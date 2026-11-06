@echo off
rem AutoNovel stopper - thin wrapper around scripts\stop_local.ps1 (Step 6)
rem Gracefully terminates Backend (8200), Frontend (5173), and Huey processes.
echo.
echo ###############################################################################
echo [非推奨] このバッチファイルは非推奨です。
echo 代わりに `scripts\start_local.ps1` をご使用ください。
echo   powershell -ExecutionPolicy Bypass -File scripts\start_local.ps1
echo このスクリプトは将来のバージョンで削除されます。
echo ###############################################################################
echo.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\stop_local.ps1"
pause
