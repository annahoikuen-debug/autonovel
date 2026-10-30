@echo off
rem ===========================================================================
rem  AutoNovel 起動診断 (Doctor)
rem  起動できないときに把这个文件をダブルクリックしてください。
rem  Python / 依存関係 / .env / DB / ポート / メモリ / import 時間を一括チェックします。
rem ===========================================================================
echo.
echo ###############################################################################
echo [非推奨] このバッチファイルは非推奨です。
echo 代わりに `scripts\start_local.ps1` をご使用ください。
echo   powershell -ExecutionPolicy Bypass -File scripts\start_local.ps1
echo このスクリプトは将来のバージョンで削除されます。
echo ###############################################################################
echo.
setlocal
cd /d "%~dp0"
chcp 65001 > nul
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\doctor.ps1" -Deep
echo.
echo 修正後は、このファイルをもう一度実行して確認してください。
echo 起動するには「アプリ起動_ローカル.bat」をダブルクリック。
pause
endlocal
