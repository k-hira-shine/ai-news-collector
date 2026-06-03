# プロジェクト構成（ファイル地図）

ルートに Python が並ぶのは **CI が `python ファイル名` で直叩きするため**（import もフラット）。フォルダ移動は workflow 修正が必要なので、まずはこの地図で探す。

## ディレクトリ

| パス | 役割 |
|------|------|
| `data/` | 収集・分析の実データ（JSONL / JSON）。Git に commit される |
| `docs/` | GitHub Pages 公開物（HTML、図解、`run_status.json`） |
| `scripts/` | 手動診断・一回限り・実験（原則 CI からは呼ばない）。例外は下表 |
| `tests/` | pytest |
| `templates/` | HTML テンプレ断片 |
| `workers/` | Cloudflare Worker 等（投稿ストックなど） |
| `.github/workflows/` | 定期実行・手動実行の定義 |
| `.cursor/docs/` | エージェント向けメモ（pitfalls、障害 postmortem、本ファイル） |

## 本流（朝晩 collect）

| ファイル | 役割 | CI |
|----------|------|-----|
| `main.py` | 収集 → 分析 → 図解 → index/strategy 生成 → Discord | `collect.yml` |
| `collector.py` | X（Apify）収集 | ↑ `main.py` 経由 |
| `analyzer.py` | Gemini 分析 | ↑ |
| `diagram.py` | 図解 HTML/PNG | ↑ |
| `dashboard.py` | `docs/index.html`, `strategy.html` | ↑ / `dashboard-only` |
| `notifier.py` | Discord 通知 | ↑ |
| `utils.py` | ログ、`run_status.json` | 横断 |
| `alerts.py` | 健全性アラート検知 | ↑ |
| `incident_status.py` | 障害カード（HTML/JSON） | ↑ / `build_*` |
| `site_nav.py` | 全ページ共通ナビ | `build_*`, `dashboard` |

## ページ生成（`build_*.py` → `docs/*.html`）

| ファイル | 出力 | CI |
|----------|------|-----|
| `build_home.py` | `docs/home.html` | `collect.yml`, `rebuild-reviews.yml` |
| `build_buzz.py` | `docs/buzz.html` | `collect.yml`, `buzz-collect.yml` |
| `build_hn.py` | `docs/hn.html` | `collect.yml` |
| `build_tools.py` | `docs/tools.html` | `collect.yml`, `rebuild-reviews.yml` |
| `build_gemini.py` | `docs/gemini.html` | `collect.yml` |
| `build_gemini_omni.py` | `docs/gemini-omni.html` | `collect.yml` |
| `build_reviews.py` | `docs/reviews.html` | `rebuild-reviews.yml` |

## 縦割りパイプライン（命名: `*_collector` → `*_analyzer` → `*_dashboard` / `run_*`）

| テーマ | 入口 | 収集 | 分析 | ページ |
|--------|------|------|------|--------|
| マネタイズ | `run_money.py` | `money_collector.py` | `money_analyzer.py` | `money_dashboard.py` |
| バズり | `run_buzz.py` | （`run_buzz` 内） | — | `build_buzz.py` |
| SNS成功者 | — | `sns_collector.py` | `sns_analyzer.py` | `sns_dashboard.py` |
| ツール追跡 | — | `tools_collector.py` | `tools_analyzer.py` | `build_tools.py` |
| Gemini 公式 | — | `gemini_collector.py` | — | `build_gemini.py` |

## その他ルート `.py`

| ファイル | 用途 |
|----------|------|
| `post_generator.py` | 投稿ストック生成 |
| `check_cost.py` | Apify コスト確認（手動） |
| `discord_state.py` | Discord 状態 |

## `scripts/` 一覧

**置き場ルール:** 新規は「CI が毎回叩かない」ものをここへ。CI から呼ぶならルートか workflow を先に更新。

| ファイル | 用途 | CI |
|----------|------|-----|
| `probe_x_upstream.py` | X 上流 API の最小プローブ | 手動 |
| `publish_incident.py` | 障害を `run_status.json` に載せて HTML 同期 | 手動 |
| `check_incident_css_leak.py` | docs の CSS 漏れ検査 | 手動（commit 前推奨） |
| `collect_gemini_omni_overseas.py` | Omni 海外ポスト収集 | **`collect.yml`（例外）** |
| `gemini_omni_media.py` | Omni 動画メディア補助 | 手動 |
| `backfill_gemini_omni_videos.py` | 動画バックフィル | 手動 |
| `cursor_sdk_try.py` | SDK 試行（実験） | 使わない |

## GitHub Actions 早見

| workflow | 主なコマンド |
|----------|----------------|
| `collect.yml` | `main.py` → buzz/hn/tools/gemini/omni の build → `build_home.py` |
| `money-collect.yml` | `run_money.py` |
| `buzz-collect.yml` | `run_buzz.py` → `build_buzz.py` |
| `rebuild-reviews.yml` | `build_reviews.py`, `build_tools.py`, `build_home.py` |

手動トリガー補助: `run_workflow.sh`（money / collect / buzz）

## よく触る設定・データ

- 設定: `config.yaml`
- 障害表示: `docs/run_status.json` + `incident_status.py`
- 図解: `docs/diagrams/`
- 分析結果: `data/analysis/`
- 生 X データ: `data/daily/`

## やらないこと（高リスク）

- ルートの `build_*.py` や `main.py` をいきなりサブフォルダへ移動（workflow・import 一括変更が必要）
- `scripts/` に CI 用エントリを増やしすぎる（パスが二系統になる）

## 関連ドキュメント

- 運用の落とし穴: `.cursor/docs/pitfalls.md`
- 障害 CSS 漏れ: `.cursor/docs/incident-display-css-leak.md`
- `scripts/` 置き場: `scripts/README.md`
