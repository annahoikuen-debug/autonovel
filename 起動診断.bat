@echo off
rem ===========================================================================
rem  AutoNovel 起動診断 (Doctor)
rem  起動できないときに把这个文件をダブルクリックしてください。
rem  Python / 依存関係 / .env / DB / ポート / メモリ / import 時間を一括チェックします。
rem ===========================================================================
setlocal
cd /d "%~dp0"
chcp 65001 > nul
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\doctor.ps1" -Deep
echo.
echo 修正後は、このファイルをもう一度実行して確認してください。
echo 起動するには「アプリ起動_ローカル.bat」をダブルクリック。
pause
endlocal
