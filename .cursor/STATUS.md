# ai-news-collector 現状整理

最終更新: 2026-05-13

---

## 公開ページ一覧

| ページ | URL | 説明 |
|---|---|---|
| ニュースダッシュボード | `https://k-hira-shine.github.io/ai-news-collector/` | AI関連ニュース・分析結果（朝便/夕便） |
| バズりランキング | `https://k-hira-shine.github.io/ai-news-collector/buzz.html` | 登録アカウントの投稿エンゲージメントランキング |
| 施策提案 | `https://k-hira-shine.github.io/ai-news-collector/strategy.html` | 収集ニュースをもとにGeminiが生成する動画企画案 |
| 動画マネタイズ事例集 | `https://k-hira-shine.github.io/ai-news-collector/money.html` | 動画収益化の実績事例（日英・カテゴリ別・180日蓄積） |

---

## 自動実行スケジュール（JST）

| ワークフロー | 時刻 | 頻度 | 内容 |
|---|---|---|---|
| `collect.yml` (ニュース) | **03:00 / 16:00** | 毎日2回 | Xニュース収集 → Gemini分析 → index.html / strategy.html 更新 |
| `buzz-collect.yml` | **03:10** | 毎日1回 | バズりアカウント全件収集 → buzz.html 更新 |
| `money-collect.yml` | **03:20** | 毎日1回 | マネタイズ事例収集 → Gemini分析 → money.html 更新 |

> 03:00 / 03:10 / 03:20 と10分ずらしてpushコンフリクトを防いでいる

---

## コスト実績と閾値

### Apify

| ワークフロー | Actor | 実績コスト/回 | 異常値閾値 |
|---|---|---|---|
| ニュース収集 | `xquik/x-tweet-scraper` | $0.10〜0.15 | — |
| バズりランキング | `xquik/x-tweet-scraper` | $0.05〜0.10 | — |
| マネタイズ事例 | `xquik/x-tweet-scraper` | **$0.50〜0.60** | **$1.00超でブラウザ警告** |

- 月間予算上限: `$29.00`（config.yaml `apify_monthly_budget_usd`）
- **$1.00超はrun_status.jsonにwarning → index.htmlのバナーで通知される**

### Gemini API

- ニュース分析: Stage1 (Gemini 2.5 Pro) + Stage2 (Gemini 2.5 Pro)、fallback: Flash
- thinking_budget: stage1=128 / stage2=512 / stage3=256
- マネタイズ分析: Gemini 2.5 Pro（カテゴリ・difficulty・income_mentioned を抽出）

### 停止済みの外部ワークフロー（コスト削減済み）

| プロジェクト | 停止内容 | 理由 |
|---|---|---|
| `k-hira-shine/x-research` (`X-research🎭`) | scheduleをコメントアウト + GitHub Actions無効化 | `apidojo/tweet-scraper` で$0.5〜1.0/日の費用が発生していた |
| `k-hira-shine/x-ai-viral-collector` | daily/weekly両方のscheduleを停止 | `get-leads/all-in-one-x-scraper` で不要な費用が発生していた |

---

## 主要設定値（config.yaml）

### ニュース収集

| 設定 | 値 |
|---|---|
| 検索クエリ数 | 5本（英語3・日本語2） |
| 監視アカウント数 | 19アカウント（公式7・海外研究者6・日本語6） |
| 1クエリ最大取得数 | 150件 |
| 1アカウント最大取得数 | 20件 |
| 収集期間 | 過去2日分 |
| 重複排除キャッシュ | 2日 |
| 使用Actor | `xquik/x-tweet-scraper` |

### マネタイズ事例収集

| 設定 | 値 |
|---|---|
| 指定アカウント | `@fiction_log`（ろじん）、`@gagarotai200` |
| 1アカウント最大取得数 | 500件 |
| 検索クエリ数 | 日本語8本 + 英語19本 = **27本** |
| 1クエリ最大取得数 | 200件 |
| sinceパラメータ | 180日前から |
| 重複排除キャッシュ | **180日** |
| 最低フォロワー数 | 1,000人以上 |

### バズりランキング

| 設定 | 値 |
|---|---|
| 登録アカウント | 6件（`keitowebai`, `usutaku_channel`, `taziku_co`, `rute1203d`, `mercarioji`, `masahirochaen`） |
| UI上でアカウントの追加・削除可能 | ◯（buzz.htmlから操作） |

---

## エラー監視

- `docs/run_status.json` に各ワークフローの実行結果を書き出し
- ブラウザ（index.html）右下のバナーで通知
  - 🚨 赤バナー: エラー発生（ワークフロー失敗）
  - ⚠️ 黄バナー: 警告（Apifyコスト異常値など）
- 実行ログは `data/logs/YYYY-MM-DD.jsonl`（30日分保持）

---

## 過去の主な問題と対処

| 発生時期 | 問題 | 対処 |
|---|---|---|
| 2026-05 | `collect.yml` でYAML parseエラー → 大量失敗メール | `python -c` の複数行を1行に修正 |
| 2026-05 | 朝便が「evening」タグになる | `time_slot()` の条件を `hour < 14` に修正 |
| 2026-05 | index.htmlが夕便データを表示しない | `_load_recent_analyses` のソートを slot順（morning<evening）に修正 |
| 2026-05 | `money-collect.yml` タイムアウト（20分制限） | timeout-minutes を45分に拡大 + ThreadPoolExecutor で並列化 |
| 2026-05 | 英語マネタイズ事例が増えない | 英語クエリを19本に拡充、バッチ並列で独立したmaxItems割当 |
| 2026-05 | Apifyコストの想定外スパイク | `actor-compare.yml` 削除、`X-research🎭` / `x-ai-viral-collector` のschedule停止 |
| 2026-05 | push競合で複数ワークフローが失敗 | 03:00 / 03:10 / 03:20 にスケジュールをずらす + リトライ付きpushループ実装 |
| 2026-05 | money.htmlの金額バッジがはみ出る | `white-space:normal` + `word-break:break-word` + `max-width:200px` で折り返し |
