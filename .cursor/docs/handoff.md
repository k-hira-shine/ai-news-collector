# ai-news-collector 引き継ぎ資料

最終更新: 2026-05-15

---

## プロジェクト概要

AIニュース・ツール・SNS成功者情報などを自動収集・Gemini分析し、  
GitHub Pages 上のダッシュボードとして毎日自動更新するシステム。

**GitHub リポジトリ**: `k-hira-shine/ai-news-collector`  
**GitHub Pages URL**: `https://k-hira-shine.github.io/ai-news-collector/`

---

## ページ一覧（ナビゲーション順）

| ページ | ファイル | 生成スクリプト | 更新ワークフロー |
|--------|----------|----------------|-----------------|
| 📰 ニュース | `docs/index.html` | `dashboard.py` | `collect.yml` |
| 🎯 施策提案 | `docs/strategy.html` | `dashboard.py` | `collect.yml` |
| 🔥 バズりランキング | `docs/buzz.html` | `build_buzz.py` | `buzz-collect.yml` |
| 🎬 マネタイズ | `docs/money.html` | `money_dashboard.py` | `money-collect.yml` |
| 🧠 SNS成功者 | `docs/sns_success.html` | `sns_dashboard.py` | `money-collect.yml` |
| ✍️ 投稿ストック | `docs/post_generator.html` | `post_generator.py` | `money-collect.yml` |
| 🔧 ツール追跡 | `docs/tools.html` | `build_tools.py` | `collect.yml` |
| 📋 使ってみた | `docs/reviews.html` | `build_reviews.py` | 手動（後述） |

> **HN/arxiv** は独立ページを廃止し、ニュースページ末尾に統合済み（2026-05-15）。

---

## 自動実行スケジュール（GitHub Actions）

| ワークフロー | JST 実行時刻 | 主な処理 |
|--------------|-------------|----------|
| `collect.yml` | **02:00** & **16:00** | AIニュース収集→Gemini分析→図解生成→index/strategy/tools/hn/buzz HTML生成→コミット |
| `money-collect.yml` | **02:20** | マネタイズ・SNS成功者収集→Gemini分析→money/sns/post_generator HTML生成→コミット |
| `buzz-collect.yml` | **02:10** | バズりランキング収集→buzz.html生成→コミット |

---

## データフロー

```
収集 → 分析 → HTML生成 → docs/ コミット → GitHub Pages 自動更新
```

### AIニュース系（collect.yml）
```
collector.py     → data/daily/YYYY-MM-DD.jsonl
                 → data/hn/YYYY-MM-DD.jsonl
analyzer.py      → data/analysis/YYYY-MM-DD_morning/evening.json
diagram.py       → docs/diagrams/YYYY-MM-DD-morning/evening.html/.png
dashboard.py     → docs/index.html, docs/strategy.html
build_hn.py      → docs/hn.html
build_tools.py   → docs/tools.html（tools_collector.py → data/tools/）
```

### マネタイズ系（money-collect.yml）
```
money_collector.py  → data/money/
money_analyzer.py   → 分析JSON
money_dashboard.py  → docs/money.html

sns_collector.py    → data/sns_success/
sns_analyzer.py     → 分析JSON
sns_dashboard.py    → docs/sns_success.html

post_generator.py   → docs/post_generator.html, data/generated_posts/
```

### バズり系（buzz-collect.yml）
```
run_buzz.py      → data/buzz.json
build_buzz.py    → docs/buzz.html
```

---

## 必要なGitHub Secrets

| Secret名 | 用途 | 使用ワークフロー |
|----------|------|-----------------|
| `APIFY_TOKEN` | Apify Actor実行（X収集・バズり） | 全3つ |
| `GEMINI_API_KEY` | Gemini分析・翻訳 | collect / money |
| `X_COOKIES` | Xログイン状態 | money-collect |
| `XQUIK_API_KEY` | Xクイック検索API | money-collect |
| `GH_PAT` | git push権限 | buzz-collect |
| `REDDIT_CLIENT_ID` | Reddit API（未承認・スキップ中） | collect |
| `REDDIT_CLIENT_SECRET` | 同上 | collect |
| `REDDIT_USERNAME` | 同上 | collect |
| `REDDIT_PASSWORD` | 同上 | collect |
| `PAGES_DEPLOY_KEY` | 別リポへのSSHデプロイ（任意） | collect |

---

## 設定ファイル

### `config.yaml` の主要セクション

| セクション | 内容 |
|------------|------|
| `collection` | ニュース鮮度（max_age_days）など |
| `x_twitter` | 検索クエリ・必須フォローアカウント・Apifyアクター名・月間予算 |
| `analysis` | Geminiモデル指定（Primary: 2.5 Pro / Fallback: 2.5 Flash）、各ステージ設定 |
| `money_collection` | Apify max_items: 200/クエリ100に削減済み（2026-05コスト削減） |
| `sns_success` | max_items: 100に削減済み |
| `tools_tracking` | RSS feeds, Reddit subreddits（enabled: true） |
| `buzz_accounts` | バズり収集対象アカウント一覧 |
| `post_templates` | 投稿ジェネレーターの6テンプレート |

---

## レビューページの更新方法（手動）

`data/reviews.json` を編集 → `python3 build_reviews.py` → コミット・プッシュ

### reviews.jsonのフィールド

| フィールド | 値の例 |
|------------|--------|
| `status` | `using` / `trying` / `untried` / `rejected` |
| `verdict` | `use` / `no` / `maybe` |
| `use_for` | `["x", "youtube", "school", "line", "work"]` |
| `reason` | 使う/使わない理由 |
| `purpose` | 目的・用途 |
| `method` | 使い方・方法 |
| `caution` | 注意点 |
| `action_plan` | 次のアクション |
| `memo` | 自由メモ |

---

## コスト管理

### 現在のApify設定（2026-05削減後）
- `money_collection.max_items_per_account`: 200（削減前500）
- `money_collection.max_items_per_query`: 100（削減前200）
- `sns_success.max_items_per_query`: 100（削減前150）

### コスト確認
```bash
python3 check_cost.py
```
`data/logs/YYYY-MM-DD.jsonl` に各ワークフローのApifyコストが記録されている。
`data/cost_changes.jsonl` に設定変更の記録と効果測定あり。

---

## ローカル実行方法

```bash
# 環境設定
cp .env.example .env   # GEMINI_API_KEY, APIFY_TOKEN 等を記入

# AIニュース収集・分析
python3 main.py

# マネタイズ・SNS成功者
python3 run_money.py

# バズりランキング
python3 run_buzz.py

# HTML生成のみ（各ページ個別）
python3 dashboard.py      # index.html, strategy.html
python3 build_tools.py    # tools.html
python3 build_reviews.py  # reviews.html
python3 build_buzz.py     # buzz.html
python3 build_hn.py       # hn.html

# コスト確認
python3 check_cost.py
```

---

## 未完了・保留中のタスク

| タスク | 状況 |
|--------|------|
| Reddit API連携 | 承認待ち。承認後にGitHub Secretsへ4つの値を設定するだけで自動有効化 |
| `reviews.html` の内容充実 | 現在4ツールのみ（Claude Code, Cursor, ChatGPT, Gemini）。`data/reviews.json` に追記 |

---

## ディレクトリ構造（簡略）

```
ai-news-collector/
├── main.py                 # AIニュース収集・分析オーケストレータ
├── run_money.py            # マネタイズ・SNS系オーケストレータ
├── run_buzz.py             # バズりランキング収集
├── config.yaml             # 全ワークフロー共通設定
├── collector.py            # X/HN/arxiv収集
├── analyzer.py             # Gemini 3段分析
├── dashboard.py            # index.html + strategy.html生成
├── money_collector.py      # マネタイズ事例収集
├── money_dashboard.py      # money.html生成
├── sns_collector.py        # SNS成功者収集
├── sns_dashboard.py        # sns_success.html生成
├── post_generator.py       # 投稿文生成
├── tools_collector.py      # ツール追跡収集（RSS+Reddit）
├── tools_analyzer.py       # ツール分析
├── build_tools.py          # tools.html生成
├── build_buzz.py           # buzz.html生成
├── build_hn.py             # hn.html生成（参照用・ナビ非表示）
├── build_reviews.py        # reviews.html生成
├── check_cost.py           # Apifyコスト確認
├── utils.py                # 共通ユーティリティ
├── .github/workflows/
│   ├── collect.yml         # JST 02:00 & 16:00
│   ├── money-collect.yml   # JST 02:20
│   └── buzz-collect.yml    # JST 02:10
├── data/
│   ├── daily/              # 収集済みニュースJSONL
│   ├── analysis/           # Gemini分析JSON（朝夕）
│   ├── hn/                 # HN+arxiv JSONL
│   ├── money/              # マネタイズ事例
│   ├── sns_success/        # SNS成功者ポスト
│   ├── tools/              # ツール追跡JSONL
│   ├── cache/              # seen_urls等キャッシュ
│   ├── logs/               # 実行ログJSONL
│   ├── generated_posts/    # 投稿生成結果
│   ├── buzz.json           # バズりランキング
│   ├── reviews.json        # レビューデータ（手動更新）
│   └── cost_changes.jsonl  # コスト変更履歴
└── docs/                   # GitHub Pages公開HTML
    ├── index.html
    ├── strategy.html
    ├── buzz.html
    ├── money.html
    ├── sns_success.html
    ├── post_generator.html
    ├── tools.html
    ├── reviews.html
    ├── hn.html             # 参照用（ナビ非表示）
    └── diagrams/           # 図解HTML+PNG
```
