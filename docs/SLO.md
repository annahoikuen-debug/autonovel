# AutoNovel SLO（Service Level Objective）

SaaS としての信頼性目標を定義する。SLO は内部目標であり、
実績 3 ヶ月分のデータに基づいて SLA（顧客向け保証）を策定する。

## 測定対象メトリクス

| メトリクスタイプ | Prometheus メトリク名 | ラベル |
|---|---|---|
| 可用性 | `up`（/health エンドポイント）| job, instance |
| 生成成功数 | `generation_success_total` | workflow_type |
| 生成失敗数 | `generation_failure_total` | workflow_type |
| 生成所要時間 | `novel_generation_duration_seconds` | workflow_type |

## SLO 目標値（MVP 版）

| 指標 | 目標値 | 測定期間 | 測定方法 |
|---|---|---|---|
| 可用性 | 99.5%/月 | 30 日 | `/health/liveness` の 200 レスポンス率 |
| 生成成功率 | 99.0% | 30 日 | `generation_success_total / (generation_success_total + generation_failure_total)` |
| 95p 応答時間（生成系 API） | ≤ 30 秒 | 30 日 | `novel_generation_duration_seconds` の 95 パーセンタイル |
| 95p 応答時間（軽量系 API） | ≤ 500 ms | 30 日 | HTTP リクエスト所要時間の 95 パーセンタイル |
| エラー率（5xx） | < 1.0% | 30 日 | 全 API の 5xx レスポンス率 |

## アラートしきい値（推奨）

| アラート | しきい値 | 継続時間 | 通知先 |
|---|---|---|---|
| 可用性低下 | 成功率 < 99% | 5 分 | Slack / メール |
| 生成失敗急増 | 失敗率 > 5% | 5 分 | Slack / メール |
| 生成応答遅延 | 95p > 60 秒 | 10 分 | Slack / メール |

## 運用フロー

1. 毎週月曜：前週の SLO 実績を確認
2. 毎月末：月次の SLO 実績を集計し、SLA 策定の検討材料とする
3. SLO 未達成時：事後分析（postmortem）を実施し、改善アクションを登録

## 除外事項

- 計画メンテナンス時間（事前告知あり）
- 利用者側のネットワーク障害
- LLM プロバイダ側のサービス停止（API プロバイダの SLA に依存）
