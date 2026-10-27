# H1R 判断記録（保留した項目）

- **文書ID**: `H1R_DECISIONS`
- **作成日**: 2026-10-02
- **出典計画**: [`PLAN_H1R_POST_REVIEW_REMEDIATION_10STEPS.md`](../plans/PLAN_H1R_POST_REVIEW_REMEDIATION_10STEPS.md)

本書は H1R で**実施しなかった**項目と、その判断理由・次に取る手順を記録する。
「後回しにした」ではなく「なぜ後回しにしたか」を固定するための文書。

---

## 1. H1R-7: mypy 1197 errors → 0 を**実施しない**

### 判断

**実施しない。**

### 実測値

```
py -m mypy src --ignore-missing-imports
Found 1197 errors in 272 files (checked 1053 source files)
```

内訳の例（いずれも型注釈の未整備）:

| エラー | 件数（概数） | 実害 |
|:---|:---|:---|
| `no-redef` | 多数 | 名前衝突。H1R-3 で `server.py` の 1 件だけ解消 |
| `attr-defined` | 多数 | 誤った属性参照の可能性 |
| `arg-type` / `assignment` | 多数 | 型の不整合 |
| `misc` / `override` 等 | 多数 | — |

### 理由

1. **0 化してもバグは 1 件も減らない。** 計画の当初想定されていた
   「バグ 50 件 → 20 件 → 5 件 → 0 件」という可是ererror 件数とバグ件数の
   線形関係は、**H1 の実測で否定されている**（ruff 767 件を 1 計画で解消して
   バグは 0 件減っていない）。
2. **工数対効果が明確にゼロ。** 1197 件を型注釈と Narrowing で潰すのは
   複数計画に分割され、各計画마다レビュー负担が発生する。
3. **既に凍結済み。** CI の `static-analysis` ジョブは
   `python scripts/ci_lint_ratchet.py`（ruff のみ hard gate）と
   `mypy src || true`（記録のみ）で構成済み。現状 0 に到達しなくても
   CI は緑を保つ。

### ただし実施した 1 件

`src/backend/server.py:213` の `no-redef`（`health` のモジュール/関数名衝突）は
**実害がある**（:214 以降のモジュールレベルコードが `health.router` を参照すれば壊れる）ため、
H1R-3 で解消した。孤立した 1 件なので意図的に拾った。

**1197 → 1196 errors**（H1R-3 の実測結果）。

---

## 2. H1R-8: `PdfExporter` の修正は**保留**（Product 判断待ち）

### 現状（実測）

`src/services/exporters/base.py` の `PdfExporter.export_stream()` は
**Markdown を返している**。`EpubExporter` と同型。

出力の同一性は H1R でバイト単位に確認済み:

```
PdfExporter    sha256 = 96db6bc59801fdb1  (MarkdownExporter と同一)
EpubExporter   sha256 = 96db6bc59801fdb1  (MarkdownExporter と同一)
```

### 判断

**本計画では直さない。** ただし既存 10 テストが「Markdown を出す」ことを
assert しており、`src/services/exporters/base.py` と
`tests/unit/services/exporters/` は R3 のファイル所有表の外にある。
**しかもこれは「機能を捨てる」判断であり、Product の領域**である。

### 次に取る手順（3 ステップ）

1. **利用実績を確認する。**
   `GET /export/books/{book_id}?platform=pdf` の呼び出し元を
   access log またはフロントのコードから確認する。

2. **使われていない場合（30 分で終わる）**
   - `PdfExporter.export_stream` を `NotImplementedError` に置換する
   - `tests/unit/services/exporters/test_base.py::test_pdf_exporter` と
     `tests/unit/services/exporters/test_base_exporters_ext.py` の
     `PdfExporter` 前提 8 件を**同時に**更新する
   - `docs/api.md` に「PDF は `/api/export/ebook`（multimedia）系統のみ
     利用可能」と明記する

3. **使われている場合**
   - PDF ライブラリ（`reportlab` / `fpdf`）の導入は**新機能追加**であり、
     新機能を 1 行も足さないという H1 の原則に反する
   - 別計画として起票する（性能・依存・ライセンスの評価が必要）

### 追跡

`TODO(H1-9)`（`src/services/exporters/base.py` 内コメント、
`docs/H1_SECURITY_AUDIT.md` §5 参照）。

---

## 3. H1R-9: 未追跡 `plans/PLAN_Q1_QUERY_TOOLING_PHASE1_2_72STEPS.md`

### 実測

```
$ git status --short
?? plans/PLAN_Q1_QUERY_TOOLING_PHASE1_2_72STEPS.md
```

`plans/` ディレクトリは追跡対象だが、このファイル 1 件だけ未追跡のまま残っている。

### 判断

**どうもしない。所有者に委ねる。**

このファイルは H1 / H1R のどちらの計画でも作成されたものではなく、
H1 の作業開始前（`git status` の初回観測時点）から存在していた。
所有者を推測して commit するのは、所有権を勝手に奪うことに等しいため行わない。

### 次に取る手順

所有者は以下のどちらかを選ぶ:

- **追跡する**: `git add plans/PLAN_Q1_QUERY_TOOLING_PHASE1_2_72STEPS.md` して commit
- **追跡しない**: `.gitignore` に 1 行追加（他の plan ファイルは追跡しているため、
  個別に無視する判断が必要）

---

## 4. H1R で**実施した**ことの要約（判断の対比）

| 項目 | 判断 | 理由 |
|:---|:---|:---|
| H1R-1 実物 smoke | **実施** | B-1 の穴を 10 件で埋める。archangel を増やすより効く |
| H1R-2 FE テスト修復 + archangel | **実施** | H1 自身が原因。放置できない |
| H1R-3 `server.py` 名衝突 | **実施** | mypy 1 件 + 将来の事故防止。2 行で済む |
| H1R-3 parity テスト刷新 | **実施** | ソース文字列 grep は誤検出する（実証済み） |
| H1R-4 FE 既存 7 件 | **記録のみ** | 各テストが「古い」のか「退行」なのかの判定が必要で範囲外 |
| H1R-7 mypy 1197 → 0 | **実施しない** | バグが減らない。工数対効果ゼロ |
| H1R-8 PdfExporter | **保留** | Product 判断。手順だけ記録 |
| H1R-9 plans/ の未追跡 | **保留** | 所有者に委ねる |