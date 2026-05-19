# Apify コスト比較ログ

## 2026-05-17（調整前）
| ワークフロー | コスト | 設定 |
|---|---|---|
| collect | $0.1254 | — |
| buzz | $0.2667 | max-items=200（デフォルト）、12アカウント |
| money | $0.7192 | max_items_per_query=100、24クエリ |
| **合計** | **$1.1113** | |

### 変更内容
- buzz: `--max-items 200 → 100`
- money: `max_items_per_query: 100 → 50`

## 2026-05-18（調整後）
| ワークフロー | コスト | 設定 |
|---|---|---|
| collect | $0.1291 | — |
| buzz | $0.1576 | max-items=100、12アカウント、1131件収集 |
| money | $0.6205 | max_items_per_query=50、24クエリ、683件収集 |
| **合計** | **$0.9072** | **▼$0.204（-18%）** |

## 2026-05-19（追加修正）

### 修正内容
- push競合対策: `buzz-collect.yml` / `collect.yml` の push リトライ時に `git stash` → `git pull --rebase` → `git stash pop` → 再commitする流れへ変更。
- cronコメント整理: GitHub Actions の cron コメントを JST 表記に統一。
- moneyコスト削減: `money_collection.search_interval_days: 2` を追加し、広域検索は2日に1回、追跡アカウントは毎日収集に変更。
- moneyクエリ削減: 広域検索クエリを17本 → 10本へ削減。

### 2026-05-20（push 競合の恒久対策）
- 3ワークフロー（collect / buzz / money）に `concurrency: repo-data-push` を設定し、main への書き込みを直列化。
- `.github/scripts/push_data.sh` を追加。rebase ではなく merge、ログ jsonl は行マージ、buzz.html は再ビルドで解決。

### 確認ポイント
- Buzz Ranking Collector が push 競合で失敗していないか。
- AI News Collector が push 競合で失敗していないか。
- money の `apify_cost_usd` が、広域検索ありの日で $0.25〜$0.35 前後に下がるか。
- 5/19 は広域検索スキップ日、5/20 は広域検索実行日の想定。
- money の Actor 起動数は、変更前 8回/日 → 変更後 平均3回/日が目安。
