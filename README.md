# AI News Collector

X から AI 関連ポストを 1 日 2 回自動収集し、Gemini 2.5 Pro で分析して GitHub Pages に公開するシステム。

## アーキテクチャ

```
収集 (collector.py)
  └── X (Apify) — 検索 + 必須アカウント

  ↓ 重複排除 → data/daily/*.jsonl に追記

分析 (analyzer.py)
  ├── Stage 1: Gemini 2.5 Pro — フィルタ & スコアリング (鮮度ボーナス付き)
  ├── Stage 2: Gemini 2.5 Pro — 深層分析 & トレンド (前日コンテキスト参照)
  └── Stage 3: Gemini 2.5 Pro — YouTube / X / ビジネス施策提案

  ↓ data/analysis/*.json に保存

ダッシュボード (dashboard.py)
  ├── docs/index.html — ニュースダッシュボード
  └── docs/strategy.html — 施策提案ページ
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
| `APIFY_TOKEN` | ✅ | Apify API Token (X 収集用) |

### 3. ローカル実行

```bash
# 通常実行
python main.py

# 収集のみ (分析・配信スキップ)
python main.py --dry-run
```

### 4. GitHub Actions

リポジトリの Settings → Secrets and variables → Actions に環境変数を登録。
毎日 JST 02:00 / 20:00 に自動実行。Actions タブから手動実行も可能。

## 設定 (config.yaml)

- **検索クエリ・必須アカウント**: `x_twitter` セクション
- **分析モデル**: `analysis.models` で各ステージのモデルを変更可能
- **スコアリング**: `scoring.freshness_bonus` で鮮度ボーナスを調整
- **カテゴリ**: `analysis.categories` で分類カテゴリを変更可能

## データ

```
data/
  daily/          ← 生データ (JSONL、1行1記事)
  analysis/       ← 分析結果 (JSON)
  cache/          ← 重複排除キャッシュ (48時間ローテーション)
  stats/          ← 月次統計
```

## コスト

現在の設定では Apify の従量課金が主なコストです。

- Gemini API: 2.5 Pro 無料枠内想定
- Apify: 1回あたりおおよそ $0.10 前後（取得件数により変動）
- GitHub Actions / GitHub Pages: パブリックリポジトリの無料枠内
