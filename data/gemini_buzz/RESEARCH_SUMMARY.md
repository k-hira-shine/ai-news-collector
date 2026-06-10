# Gemini Buzz Research Summary

実施日: 2026-06-10

## 結果

- 対象期間: 2024-06-10 から 2026-06-10
- 最終ランキング: 55件
- 驚き投稿: 22件
- 新機能投稿: 33件
- 開始時点: 26件
- 純増: 29件

## 検索

| 検索プロファイル | Apify費用 | 実行後の件数 |
|---|---:|---:|
| broad | $0.0120 | 34 |
| features | $0.0247 | 46 |
| feature-expansion | $0.0201 | 56 |
| 品質再判定 | $0 | 55 |

Apify合計は約`$0.0568`。この3回に対応するGeminiの二次判定と翻訳は約`$0.0153`で、合計は約`$0.0721`。

## 品質管理

- ルール判定とGemini 2.5 Flash-Liteの両方が承認した投稿だけを採用。
- FLORA、Project Genieなど、Geminiを利用する別製品が主役の投稿を除外。
- 反応誘導や販促投稿を除外。
- 実リリースではなく、将来予測だけを述べる投稿を除外。
- 英語投稿は原文を保持し、日本語訳を表示。

## 再実行

GitHub Actionsの`Gemini Buzz One-off Research`で以下を順に選ぶ。

1. `query_profile: broad`
2. `query_profile: features`
3. `query_profile: feature-expansion`

通常は既存ランキングへURL単位で追記されるため、同じ投稿は重複しない。
