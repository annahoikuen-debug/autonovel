# scripts/debug — 起動・性能の診断ツール

起動できない・起動が遅いときに使う再利用可能なスクリプトを置いておく場所。
使い捨ての一時スクリプトは `scratch/` に移動してよい。

> まず最初に行うべきことは `起動診断.bat`（= `scripts/doctor.ps1`）です。
> Python / 依存関係 / .env / DB / ポート / メモリ / import 時間を一括で確認できます。

## 起動の診断

| スクリプト | 用途 |
|---|---|
| [`../doctor.ps1`](../doctor.ps1) | **第一入口。** 起動できない原因を 10 項目に分けて診断する（`起動診断.bat` がラッパー） |
| [`startup_probe.py`](startup_probe.py) | ポートを掴まずに ASGI アプリを直接起動し、lifespan と主要エンドポイントを検証する |
| [`start_capture.ps1`](start_capture.ps1) | `start_local.ps1` を実際に起動し、backend/frontend の到達性とログを採取する E2E テスト |

## 起動速度の分析

| スクリプト | 用途 |
|---|---|
| [`import_mem_probe.py`](import_mem_probe.py) | `src.backend.server` の import 時間とモジュール数・重い SDK の読み込み状況を計測する |
| [`trace_heavy_imports.py`](trace_heavy_imports.py) | 実行時 import フックで「chromadb / openai / google.genai を誰がトップレベルで import したか」を特定する |
| [`analyze_importtime.py`](analyze_importtime.py) | `python -X importtime` の出力（`logs/importtime*.txt`）を解析し、import 連鎖を表示する |

### 典型的な使い方

```powershell
# 1) >import 全体の所要時間を測る
python scripts\debug\import_mem_probe.py

# 2) なぜ重い SDK が読み込まれるのか特定する
python scripts\debug\trace_heavy_imports.py

# 3) import 連鎖の詳細（自己時間・累積時間）を見る
python -X importtime -c "import src.backend.server" 2> logs\importtime.txt
python scripts\debug\analyze_importtime.py logs\importtime.txt google.genai openai
```

## 使い捨てスクリプトの置き場所

`check_*.py` / `debug_*.py` / `fix_*.py` のように調査のために一度だけ書いたものは
`scratch/` に移動してください。リポジトリ直下に置かれたまま放置されると、
次の人が「どれが生きているツールなのか」が分からなくなります。
