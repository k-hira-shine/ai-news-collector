# ai-news-collector 引き継ぎ資料

最終更新: 2026-06-10

---

## 次回最初に確認: Gemini活用法バズ調査

次回この調査を再開するときは、コード変更や再検索の前に必ず以下を読む。

1. `.cursor/docs/gemini-buzz-research-log.md`
2. `data/gemini_buzz/search_manifest.json`
3. `data/gemini_buzz/ranking.json`

現在は小規模テスト1回目まで完了。次は本番拡張ではなく、検索クエリを
単純化した小規模再テストを行う。詳細と判断理由は専用ログに記録済み。

---

## 2026-06-10 全体レビュー結果と経過観察項目

- レビュー範囲: 6/9〜6/10 朝の全コミット（health check 強化、Apify削減、gemini-buzz ページ改善、ナビ恒久対策）
- 結果: テスト65件通過、未コミットなし、全13ページのナビ同期確認、公開ページ反映確認。問題なし。
- 経過観察:
  1. `collect.yml` の朝軽量モードは `github.event.schedule == "0 7 * * *"` の完全一致判定。**cron 時刻を変更したら、この条件も必ず同時に更新する**（放置すると黙ってフルモードに戻りコスト増）。
  2. Apify 削減の実効果は 2026-06-13 頃に `data/cost_tracking.json` の日次推移で確認する。判定: 朝実行分のコストが従来比で下がっていればOK。

---

## 2026-06-10 ナビ欠落の恒久対策（sync_nav.py）

- 問題: ナビは各HTMLにビルド時に焼き込む方式。`site_nav.py` にページを足しても、その後に再生成されないページは旧ナビのままでリンクが欠ける（毎回どこかで漏れる）。
- 対策:
  - `sync_nav.py` を新規作成。`docs/*.html` の `<nav class="topnav">...</nav>` を最新ナビへ一括置換（active はファイル名で判定）。
  - 全収集系ワークフロー（collect / money-collect / buzz-collect / gemini-buzz-research / rebuild-reviews）のコミット前に `python sync_nav.py` を追加。ターゲット型 workflow の push 対象を個別HTML→`docs/` へ拡大し、同期結果が確実に push されるようにした。
  - 既存11ページを今回のコミットで同期済み。
- 関連コミット: 本ターンでコミット
- 合格条件: どのページからでもナビに全リンク（特に🏆Gemini活用）が出る。新ページ追加時は `python3 sync_nav.py` 実行→`docs/` を push。
- 注意: `render_nav` の NAV_LINKS が唯一のソース。CSS(`NAV_CSS`)は各ビルダー側で head に入る前提なので sync_nav は CSS を触らない。
- 残課題: なし

## 2026-06-10 Gemini活用法バズ調査ページ 並べ替え機能を追加

- 何を変更したか: `build_gemini_buzz.py` にクライアントサイド並べ替えを実装。
  - 各カードに `data-likes/retweets/bookmarks/er/buzz` を埋め込み、上部に並べ替えボタン（バズスコア=既定/いいね/リポスト/ブックマーク/エンゲージメント率）を追加。
  - 末尾の `<script>` でカードをDOM並べ替えし、`.rank` の番号(#n)を振り直す。
- 関連コミット: 本ターンでコミット
- 合格条件: ページ上部のボタンを押すと並び替わり、#番号が1から振り直される。`grep -c sortbtn docs/gemini-buzz.html` が0より大。
- 注意: 静的ページなのでJSはインライン。再生成は `python3 build_gemini_buzz.py`。
- 残課題: なし

## 2026-06-10 Gemini活用法バズ調査ページ エンゲージメント率(ER)を追加

- 何を変更したか: `build_gemini_buzz.py` に `_engagement_rate()` を追加。
  - 定義: ER = (likes+retweets+bookmarks+quotes+replies) ÷ author_followers ×100、パーセント表記。
  - 100%以上は整数、未満は小数1桁。フォロワー0件は非表示。
  - カードの stats 行に緑バッジ「ER xxx%」とフォロワー数「👤 n」を追加。
- 関連コミット: 本ターンでコミット
- 合格条件: 各カードに「ER ◯%」表示。`grep -o 'ER [0-9.,]*%' docs/gemini-buzz.html` でヒット。
- 注意: バイラル投稿はフォロワー超えの拡散でERが数百%になる（仕様通り、フォロワー比の反響を示す）。
- 残課題: なし

## 2026-06-10 Gemini活用法バズ調査ページ 日付の日本語化＋表示名追加

- 何を変更したか:
  - `build_gemini_buzz.py` の投稿日表示を「Thu Apr 30」→「2026年4月30日」へ。`_format_date()` を追加し、X形式 `%a %b %d %H:%M:%S %z %Y` をパースして変換。
  - カードのメタ行に `author_display`（アカウント表示名）を太字で追加。`@ハンドル` は `.handle` クラスで控えめ表示。
  - `docs/gemini-buzz.html` を再生成。
- 関連コミット: `e751e38`（日付）+ 表示名分は本ターンでコミット
- 合格条件: 各カードに「表示名 + @ハンドル + YYYY年M月D日」が並ぶ。`grep '年.*月.*日' docs/gemini-buzz.html` でヒットすればOK。
- 注意: 旧コードの `[:10]` スライスはX形式日付では英語のまま切り出すバグだった。再生成は `python3 build_gemini_buzz.py`。
- 残課題: なし

---

## 2026-06-10 Gemini活用法バズ調査

- 単発手動ワークフロー `gemini-buzz-research.yml` を追加
- 定期スケジュールは追加していない
- 対象期間: 2025-06-10〜2026-06-10
- 4クエリ、最大400件、課金上限 `$0.08`
- 実績: 97件取得、42件採用、要確認5件、実費 `$0.0145`
- 結果ページ: `docs/gemini-buzz.html`
- 実行: Actions run `27235055487`
- 結果コミット: `44bfee9`
- 評価: 約70点。仕組み・費用・保存は合格、検索範囲と精度は要改善

重要: 4クエリを渡したが、返却された97件はすべて日本語の
`Gemini (使い方 OR 活用法 OR プロンプト)` クエリ由来だった。
英語2クエリと業務効率化クエリは0件。次回はクエリを短くし、
日本語・英語を分けて少量ずつ再テストする。

---

## 2026-06-10 日次確認

朝の3ワークフローと昨日のヘルスチェック修正を確認した。

- `AI News Collector`、`Buzz Ranking Collector`、`AI Money Cases Collector` はすべて成功
- Gemini RSSは9件すべて成功し、`rss_feeds_failed=0`
- collectは`health_check_version=2`、収集前後の異常検知はいずれも0
- push競合後に`status_merge`が動作し、2回目のpushで成功
- 本日生成されたJSON/JSONLに構文エラーなし
- テストは`53 passed, 12 subtests passed`
- Python 3.14の警告を解消するため、`build_buzz.py`内のJavaScript正規表現を二重エスケープ

---

## 2026-06-09 ローカル main 同期

510コミット古かったローカル `main` を `origin/main` へ同期した。同期前の未コミット内容は削除せず、以下の3系統で保全済み。

- ローカル保全ブランチ: `backup/local-pre-sync-20260609`
- 保全コミット: `221df54` (`backup: preserve local work before main sync`)
- 外部アーカイブ: `/Users/kz5/ai-news-collector-backups/2026-06-09-pre-sync/working-files.tar.gz`
- Git bundle: `/Users/kz5/ai-news-collector-backups/2026-06-09-pre-sync/local-pre-sync.bundle`

同期後:

- ローカル `main` と `origin/main` は同一
- 作業ツリーはクリーン
- テストは `53 passed, 12 subtests passed`
- 保全データは最新版へ自動で混ぜ戻していない

保全内容を確認する場合:

```bash
git show --stat backup/local-pre-sync-20260609
git diff main...backup/local-pre-sync-20260609
```

特定ファイルだけ復元する場合:

```bash
git restore --source backup/local-pre-sync-20260609 -- <path>
```

ブランチが失われた場合はbundleから復元できる。

```bash
git bundle verify /Users/kz5/ai-news-collector-backups/2026-06-09-pre-sync/local-pre-sync.bundle
git fetch /Users/kz5/ai-news-collector-backups/2026-06-09-pre-sync/local-pre-sync.bundle \
  backup/local-pre-sync-20260609:backup/local-pre-sync-20260609
```

---

## 2026-06-10 朝の確認事項

2026-06-09 に日次ヘルスチェックの修正を `main` へ反映した。

- 修正コミット: `e592abd` (`fix: harden daily health checks and status merge`)
- `docs/run_status.json` の競合時に、ワークフローごとの新しい `ts` を維持する
- Gemini RSSの日付をUTC aware datetimeへ正規化する
- 分析前に `top_articles=0` / 図解未生成の誤警報を出さない
- 判定用の詳細を `data/logs/YYYY-MM-DD.jsonl` に永続化する

### 合格条件

2026-06-10 朝の全ワークフロー完了後に以下を確認する。

1. `AI News Collector`、`Buzz Ranking Collector`、`AI Money Cases Collector` が成功
2. `workflow=gemini` のログで `rss_feeds_failed=0`
3. `workflow=collect` のログで `health_check_version=2`
4. 正常実行なら `collection_anomalies=0` かつ `post_analysis_anomalies=0`
5. `docs/run_status.json` の `collect` / `buzz` / `money` がすべて2026-06-10の時刻
6. push競合が起きた場合、`workflow=status_merge` のログがあり、各ワークフローの最新時刻が維持されている
7. Actionsログに `offset-naive and offset-aware datetimes` がない
8. 分析前に `分析の top_articles が 0 件` または `図解が生成されなかった（記事 0 件）` が出ていない

### 確認コマンド

```bash
git fetch origin main
git show origin/main:data/logs/2026-06-10.jsonl
git show origin/main:docs/run_status.json
gh run list --limit 15
```

必要ならActionsログを追加確認する。

```bash
gh run view <AI_NEWS_RUN_ID> --log \
  | grep -E 'offset-naive|top_articles が 0|図解が生成されなかった|Gemini RSS failed'
```

出力が空なら、今回対象にしたエラーと誤警報は再発していない。

---

## 引き継ぎ運用ルール

2026-06-09 より、コード・設定・Actions・運用変更を行った作業は、この資料の更新と `main` へのpushまでを完了条件とする。

詳細: `.cursor/rules/handoff-required.mdc`

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

### 現在のApify設定（2026-06-10削減後）
- Money/SNSアカウントは共通コレクターで1回だけ取得
- 前回成功日の2日前から差分取得、上限200件/アカウント
- Money広域検索: 2日に1回、10クエリ、上限50件/クエリ
- SNS広域検索: 3日に1回、18クエリ、上限100件/クエリ
- Buzz: 月・水・金の週3回
- News夕方便: 検索上限75件、重要公式8アカウントのみ
- 実装後見込み: `$9.96/月`（確認レンジ `$8〜12`）

### コスト確認
```bash
python3 check_cost.py
```
`data/logs/YYYY-MM-DD.jsonl` に各ワークフローのApifyコストが記録されている。
`data/cost_changes.jsonl` に設定変更の記録と効果測定あり。
`data/cost_tracking.json` に実装後の日次費用・取得件数・移動平均を記録する。

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
| **Gemini追跡: 地域可用性バッジ** | **要検討。** 日本で使える / 米国限定 / 全世界 / 不明 を公式文面からAI分類で推定しカード表示。`starting in the US` 等は拾えるが、記載なし・段階ロールアウトは `unknown` 扱い。精度向上には日本語リリースノート（`gemini.google/release-notes`）の活用が有効。実装時は `region` + `region_note_ja` を `classify_items` に追加 |

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
