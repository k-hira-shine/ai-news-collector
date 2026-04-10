# AI News Collector

X/Twitter・RSS・YouTube から AI 関連ニュースを 1 日 2 回自動収集し、Gemini 2.5 Pro で分析して Discord に配信するシステム。

## アーキテクチャ

```
収集 (collector.py)
  ├── X/Twitter (Apify) — 検索 + 必須アカウント
  ├── RSS (feedparser) — 17 フィード (公式ブログ + メディア)
  └── YouTube (Data API) — AI 解説動画

  ↓ 重複排除 → data/daily/*.jsonl に追記

分析 (analyzer.py)
  ├── Stage 1: Gemini 2.5 Pro — フィルタ & スコアリング (鮮度ボーナス付き)
  └── Stage 2: Gemini 2.5 Pro — 深層分析 & トレンド (前日コンテキスト参照)

  ↓ data/analysis/*.json に保存

配信 (notifier.py)
  └── Discord Webhook — Embed 形式 (複数メッセージ分割)

ダッシュボード (dashboard.py)
  └── docs/index.html — GitHub Pages で公開
```

## セットアップ

### 1. 依存インストール

```bash
pip install -r requirements.txt
```

### 2. 環境変数

| 変数 | 必須 | 説明 |
|---|---|---|
| `GEMINI_API_KEY` | ✅ | Google AI Studio の API キー (無料枠) |
| `YOUTUBE_API_KEY` | ✅ | YouTube Data API v3 キー (無料枠) |
| `DISCORD_WEBHOOK_URL` | ✅ | Discord Webhook URL |
| `APIFY_TOKEN` | △ | Apify API Token (X 収集用、無料枠) |
| `X_COOKIES` | △ | X ログイン Cookie (`auth_token=xxx; ct0=yyy`) |
| `ANTHROPIC_API_KEY` | ✗ | Claude に切り替える場合のみ |

### 3. ローカル実行

```bash
# 通常実行
python main.py

# 収集のみ (分析・配信スキップ)
python main.py --dry-run
```

### 4. GitHub Actions

リポジトリの Settings → Secrets and variables → Actions に環境変数を登録。
毎日 JST 07:17 / 18:23 に自動実行。Actions タブから手動実行も可能。

## 設定 (config.yaml)

- **検索クエリ・RSS フィード**: `x_twitter`, `rss_feeds` セクション
- **分析モデル**: `analysis.models` で各ステージのモデルを変更可能
- **スコアリング**: `scoring.freshness_bonus` で鮮度ボーナスを調整
- **カテゴリ**: `analysis.categories` で分類カテゴリを変更可能

## データ

```
data/
  daily/          ← 生データ (JSONL、1行1記事)
  analysis/       ← 分析結果 (JSON)
  cache/          ← 重複排除キャッシュ (7日ローテーション)
  stats/          ← 月次統計
```

## コスト

すべて無料枠内で運用: **月額 $0**

- Gemini API: 2.5 Pro 無料枠 (100 RPD)
- Apify: 無料枠 $5/月
- YouTube Data API: 無料枠 10,000 units/日
- GitHub Actions: 無料枠 2,000 分/月
