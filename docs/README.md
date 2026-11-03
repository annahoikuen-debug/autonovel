# AutoNovel ドキュメント インデックス

AutoNovel のドキュメント群です。ユーザー向けマニュアル・Q&A・開発者向けドキュメント・運用ドキュメント・法務ドキュメントに分類されています。

> 📘 **どこから読み始めるか**  
> - サービスを使い始める方 → [ユーザーガイド](easy_mode_guide.md)  
> - よくある質問を探している方 → [Q&A (FAQ)](FAQ.md)  
> - 開発・カスタマイズしたい方 → [開発者ガイド](development_guide.md) / [APIリファレンス](api.md)  
> - 本番運用・トラブルシュート → [運用・トラブルシューティング](STARTUP_TROUBLESHOOTING.md)  
> - 法務・利用規約 → [法務](legal/README.md)

---

## 👥 ユーザー向けドキュメント

| ドキュメント | 概要 | 対象 |
|---|---|---|
| [ユーザーガイド（入口の歩き方)](easy_mode_guide.md) | 3つの入口（かんたん執筆 / 共創ウィザード / Studio）の使い方と導線 | 初心者〜中級者 |
| [Easy Mode Suite（かんたんスイート)](easy_mode_suite.md) | Interactive Writer / Full Auto Generator / Gacha Pitch / Quick Digest / Producer Handoff の詳細 | 中級者〜 |
| [マルチメディア ユーザーマニュアル](user/multimedia.md) | Asset Pack（画像・音声・EPUB）の生成とトラブルシューティング | マルチメディア利用者 |
| [Publishing Guide（投稿プラットフォーム向けフォーマットガイド)](publishing_guide.md) | なろう・カクヨム・アルファポリス・KDP・青空文庫への出力仕様 | 投稿サイト利用者 |
| [Q&A (FAQ)](FAQ.md) | 著作権・料金プラン・投稿・R18・データ保存・解約など、よくある質問と回答 | 全ユーザー |
| [Easy Mode API仕様書](easy_mode_api.md) | `/easy_mode` エンドポイントのリクエスト・レスポンス詳細 | API利用者 |

---

## 👨‍💻 開発者向けドキュメント

| ドキュメント | 概要 | 対象 |
|---|---|---|
| [開発者ガイド](development_guide.md) | 開発環境の構築・コーディング規約・テスト実行方法 | 開発者 |
| [アーキテクチャ](architecture.md) | 4層アーキテクチャ（domain/application/infrastructure/interfaces）の設計 | 開発者・アーキテクト |
| [4層圧縮モジュール](compression_module.md) | FourLayerCompressor の構造・DI・設定・テスト | 開発者（圧縮モジュール担当） |
| [APIリファレンス](api.md) | バックエンドREST APIのエンドポイント一覧・パラメータ・レスポンス例 | API開発者 |

---

## 🚀 運用ドキュメント

| ドキュメント | 概要 | 対象 |
|---|---|---|
| [起動とトラブルシューティング](STARTUP_TROUBLESHOOTING.md) | 起動手順・起動できないときの対処・起動速度の最適化 | 運用者 |
| [本番デプロイチェックリスト](PRODUCTION_DEPLOYMENT_CHECKLIST.md) | 本番環境へのデプロイ前に確認すべき項目 | 運用者 |
| [SLO（サービス品質目標)](SLO.md) | サービス品質目標と効果測定結果 | 運用者・責任者 |
| [現況ステータス（SSOT）](STATUS.md) | 実装状況の唯一の正（ソース・オブ・トルース） | 全ステークホルダー |

---

## ⚖️ 法務ドキュメント

| ドキュメント | 概要 | 対象 |
|---|---|---|
| [プライバシーポリシー](legal/PRIVACY_POLICY.md) | 個人情報・創作データの取り扱い | 全ユーザー |
| [利用規約](legal/TERMS_OF_SERVICE.md) | サービス利用条件・知的財産権の帰属 | 全ユーザー |

---

## 📂 ドキュメント配置一覧

```
docs/
├── README.md                      # 本ファイル（ドキュメントインデックス）
├── easy_mode_guide.md             # ユーザーガイド（3入口の歩き方）
├── easy_mode_suite.md             # Easy Mode Suite 機能詳細
├── development_guide.md           # 開発者ガイド
├── architecture.md                # 4層アーキテクチャ設計
├── compression_module.md          # 4層圧縮モジュール詳細
├── api.md                         # バックエンドAPIリファレンス
├── easy_mode_api.md               # Easy Mode API仕様書
├── publishing_guide.md            # 投稿プラットフォーム向けフォーマットガイド
├── STARTUP_TROUBLESHOOTING.md     # 起動とトラブルシューティング
├── PRODUCTION_DEPLOYMENT_CHECKLIST.md  # 本番デプロイチェックリスト
├── SLO.md                         # サービス品質目標
├── STATUS.md                      # 現況ステータス（SSOT）
├── user/
│   └── multimedia.md              # マルチメディア ユーザーマニュアル
├── legal/
│   ├── PRIVACY_POLICY.md          # プライバシーポリシー
│   └── TERMS_OF_SERVICE.md        # 利用規約
├── adr/                           # アーキテクチャ決定記録
├── architecture/                  # アーキテクチャ詳細資料
├── features/                      # 機能仕様資料
├── images/                        # ドキュメント用画像
├── bugs/                          # バグ報告・既知問題
├── implementation_plans/          # 実装計画書
├── plans/                         # 計画・ロードマップ資料
│   └── archived/                  # アーカイブ済み計画
└── readme_vs_actual_status.md     # README vs 実態 精査レポート（SUPERSEDED・履歴用）
```

---

## 🔗 関連リンク

- [AutoNovel ランディングページ](https://github.com/annahoikuen-debug/autonovel) — サービス紹介・料金プラン・導入事例
- [GitHub リポジトリ](https://github.com/annahoikuen-debug/autonovel) — ソースコード・Issue・Pull Request
- [CHANGELOG.md](../../CHANGELOG.md) — 変更履歴
- [CONTRIBUTING.md](../../CONTRIBUTING.md) — 貢献ガイド

---

> 💡 **ヒント**: このドキュメント群は実装の真实に合わせて随時更新されています。記述と実際の動作に乖離を見つけた場合は、[GitHub Issue](https://github.com/annahoikuen-debug/autonovel/issues) でご報告ください。
