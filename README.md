# AI News Collector

X から AI 関連ポストを 1 日 2 回自動収集し、Gemini 2.5 Pro で分析して GitHub Pages に公開するシステム。

## スコープ

通常運用は **AIニュース収集・分析・公開** に限定する。
Money/SNS/Buzz/Gemini個別追跡/ツール追跡などの旧機能は、必要なときだけ手動実行する Legacy 扱い。
旧機能のコード・データ・workflow は残すが、cron では起動せず、ポータルにも表示しない。
`collect.yml` 内の旧ページ生成・収集は `ENABLE_LEGACY_PORTAL_JOBS=true` と
`ALLOW_LEGACY_COSTS=true` の両方を設定した場合だけ動く。
Legacy workflow は手動実行時も `allow_costs=true` を選ばない限り no-op にする。

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
  ├── docs/hn.html — Hacker News / arxiv のAI関連一覧
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

## プロジェクト構成

ルートに `.py` が多いのは GitHub Actions が `python main.py` のように **ファイル名直指定** しているためです（フォルダ移動は workflow 修正が必要）。

- **ファイル地図（何がどこにあるか）:** [.cursor/docs/project-layout.md](.cursor/docs/project-layout.md)
- **手動・診断スクリプトの置き場:** [scripts/README.md](scripts/README.md)

## データ

```
data/
  daily/          ← 生データ (JSONL、1行1記事)
  hn/             ← Hacker News / arxiv のAI関連データ
  analysis/       ← 分析結果 (JSON)
  cache/          ← 重複排除キャッシュ (48時間ローテーション)
  stats/          ← 月次統計
```

## コスト

現在の設定では Apify の従量課金が主なコストです。

- Gemini API: 2.5 Pro 無料枠内想定
- Apify: 1回あたりおおよそ $0.10 前後（取得件数により変動）
- GitHub Actions / GitHub Pages: パブリックリポジトリの無料枠内
