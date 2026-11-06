@echo off
setlocal
cd /d "%~dp0"
echo.
echo ###############################################################################
echo [非推奨] このバッチファイルは非推奨です。
echo 代わりに `scripts\start_local.ps1` をご使用ください。
echo   powershell -ExecutionPolicy Bypass -File scripts\start_local.ps1
echo このスクリプトは将来のバージョンで削除されます。
echo ###############################################################################
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start_docker.ps1"
endlocal
