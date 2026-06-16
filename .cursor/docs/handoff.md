# ai-news-collector 引き継ぎ資料

最終更新: 2026-06-17（全項目正常。Apify=施策後窓6/11〜で月$9.60横ばい合格 / Gemini=6/14以降Flash化で月約$7.8 / 2系統計≈$17.4月 / Buzz full=retention95%・overlap100% / 品質=最新便まで劣化なし / 残監視2点クリア。※check_cost.pyの窓に施策前6/10を混ぜると$11.17に誤膨張する点に注意＝下B節）

## 次回アクション（日付つき・最新版）

1. ~~**2026-06-16 朝便後**: 法務ニュース収集機能の初反映を確認。~~ ✅ **完了（6/16）**:
   朝便（run 27567595146、6/16 03:29 JST）で `Legal RSS total: 36 items (last 5d)` →
   stage1(Flash)除外/dedup後 `legal_rss_count: 3` が本収集に通過。流入源は The Verge Policy 10・
   EFF 6・INTERNET Watch 20（IPWatchdog/Copyright Lately/JURIST/Ars/STORIA は5日窓に新着なし=0）。
   レポートも公開済み（pages build success）。**index「規制/政策」のリンク一覧表示は未目視**（要ブラウザ確認）。
2. ~~**2026-06-17**: Apify 7日移動平均の正式判定。~~ ✅ **完了（6/17）／朝の$11.17は集計ミスを訂正**:
   正しい施策後窓 6/11〜6/17 で平均 **月換算$9.60**＝ベースライン$9.50と**ほぼ横ばい**で合格。
   朝に出た$11.17は7日窓に**施策前の6/10（Money/SNS $0.49・合計$0.77、旧SNS広域検索の日）**を1日含めた誤り。
   日々の振れの正体は**Buzz full日（週3、+$0.18〜0.22/日）**＝設計どおりで回帰ではない。法務Xクエリ追加は未着手のためコスト未反映。
3. ~~**2026-06-17**: Buzz が `full` で正常収集か確認。~~ ✅ **完了（6/17）**:
   `profile=full`・top20_retention=**95%**・ranking_overlap=**100%**・cost=$0.17。
   reduced時代の警告値（55%/70%）を大幅に上回り正常。恒久full運用に問題なし。
4. ~~**残監視2点**~~ ✅ **クリア（6/17朝便 run 27639243105）**:
   ① `legal_rss_count=7`（total 116・x_count 109中）→ 法務一色化なし。
   ② `must_follow_count=92` → 連続ゼロ回避。**残: index「規制/政策」リンク一覧の目視確認のみ**（要ブラウザ）。
5. **未了（継続）**: 法務X検索クエリ2本追加（5→7本、想定 月+$1未満）は未着手。実施時は config 反映後にApify増分を確認。
6. **未了（根本対応）**: GH_PAT のサーバー側中継。revoke 済みで止血中、根本対応は未着手（[[gh-pat-public-exposure]]）。

---

## 2026-06-17 日次チェック（全項目正常 / Apify・Gemini・品質すべてクリア）

> このセッションでやったこと: ①日次チェック実施 → ②Apifyコスト判定で集計ミスを発見し訂正 → ③Geminiコストを別途分解 → ④品質劣化チェックを最新便まで再検証。以下に経過を全部残す。

### A. GitHub Actions
全ジョブ success（直近12件）。News朝便（6/17 03:29 JST, **run 27639243105**）/ Buzz / Money / pages すべて正常完了。エラーメールなし。

### B. Apify（スクレイピング）コスト — ✅ 合格 月換算$9.60
- **正式7日判定**: 施策後窓 **6/11〜6/17** 平均 **月換算$9.60**＝ベースライン$9.50と**横ばい**で合格（基準$12以内）。
- 日次（AI News / Money・SNS / Buzz / 合計）:
  | 日 | News | Money/SNS | Buzz | 合計 |
  |---|---|---|---|---|
  | 6/11 | 0.10 | 0.15 | 0 | 0.25 |
  | 6/12 | 0.08 | 0.16 | 0.18 | 0.43 |
  | 6/13 | 0.11 | 0.18 | 0 | 0.28 |
  | 6/14 | 0.07 | 0.15 | 0 | 0.22 |
  | 6/15 | 0.10 | 0.14 | 0.23 | 0.46 |
  | 6/16 | 0.11 | 0.11 | 0 | 0.22 |
  | 6/17 | 0.05 | 0.15 | 0.18 | 0.38 |
- **⚠️ 集計ミスと訂正（重要・再発防止）**: 朝の最初の`check_cost.py`実行で「月$11.17」と報告したが**誤り**。7日窓に**施策前の6/10（Money/SNS $0.49・合計$0.77＝旧SNS広域検索の最終日）**を1日混入させていた。施策後だけの窓（6/11〜）で再計算すると$9.60。**`check_cost.py`の窓は施策適用日（6/11〜）以降に限定して読むこと。6/10以前は旧コスト構造なので混ぜない。**
- **日々の振れの正体**: Buzz full日（週3回・各 +$0.18〜0.22/日）。6/12・6/15・6/17 がそれ。設計どおりで回帰ではない。
- **法務分はまだコスト未反映**: 法務X検索クエリ2本追加（5→7本）は**未着手**のため、現状コストに法務Xは乗っていない（RSSのみ）。

### C. Gemini（LLM）コスト — ✅ 安定 月換算 約$7.8
- 施策後（**6/14以降**＝stage2/3 Flash化が効いた日以降）平均 **約$0.26/日＝月換算 約$7.8**、Pro=$0・ほぼ全量Flash。
- 日次合計: 6/11 $0.81 / 6/12 $0.51 / 6/13 $0.76（←ここまでPro残存）/ **6/14 $0.258 / 6/15 $0.283 / 6/16 $0.275 / 6/17 $0.226**（←Pro=$0）。
- **stage2/3 Flash化の効果が6/14に明確に出た**: Pro使用日（〜6/13, $0.5〜0.8/日）→ Flash専用日（6/14〜, $0.23〜0.28/日）で約1/3。ロールバック不要。
- **Apify と Gemini は別系統**。2系統合計の現状 = **約$17.4/月**（Apify $9.6 + Gemini $7.8）。

### D. Buzz full 健全性 — ✅ 正常
`profile=full`・fetched=1292・new=40・top20_retention=**95%**・ranking_overlap=**100%**・cost=$0.17。reduced時代の警告値(55%/70%)を大幅クリア。恒久full運用に問題なし。

### E. 残監視2点（品質劣化チェックの継続項目） — ✅ クリア（6/17朝便 run 27639243105）
- ① `legal_rss_count=7`（total 116・x_count 109中）→ index「規制/政策」の法務一色化なし。
- ② `must_follow_count=92` → 連続ゼロ回避（6/15夕便0→6/16朝69→6/17朝92で回復継続）。

### F. 品質劣化チェック（コスト削減後）最新便まで再検証 — ✅ 劣化なし
- **構造指標（fallback全便ゼロ＝Pro相当を維持）**:
  | 便 | top | cat | action | fallback | trend長 |
  |---|---|---|---|---|---|
  | 6/17 朝 | 10 | 6 | 5 | [] | 303 |
  | 6/16 夕 | 7 | 3 | 4 | [] | 235 |
  | 6/16 朝 | 10 | 6 | 5 | [] | 288 |
  | 6/15 夕 | 10 | 6 | 5 | [] | 206 |
  | 6/15 朝 | 10 | 6 | 5 | [] | 260 |
- **朝便は常にフル**（10/6/5）でPro時代と同一。**fallbackは全便[]**（むしろPro時代の5/16・5/29で発生していた）。
- 6/16夕の top7/cat3 は**回帰ではなく「News夕方便を軽量化」施策の設計どおり**。
- trend_summary 206〜303字は既知の変動範囲内（Pro時代も247〜269）。
- **6/17朝を実読**: trend要約（Anthropic Fable/Mythos 5アクセス遮断を軸に規制・覇権・マルチベンダー戦略を因果でつなぐ）・importance_reason（論理的）・category要約（key_articles各5件付き）すべて遜色なし。
- ※ 事実関係そのものの真偽検証はパイプライン対象外（収集・要約の品質確認に限る）。

### G. 残作業（次担当へ）
1. index「規制/政策」リンク一覧の**目視確認**（要ブラウザ、未実施）。
2. 法務X検索クエリ2本追加（5→7本、想定 月+$1未満）— **未着手**。実施時は config 反映後にApify増分を確認。
3. GH_PAT サーバー側中継の**根本対応** — revoke済みで止血中、未着手（[[gh-pat-public-exposure]]）。

### H. 検証コマンド（再現用）
- Apify: `python3 check_cost.py`（窓は6/11以降を読む）
- Gemini: `python3 gemini_usage.py`（6/14以降がFlash化後）
- Buzz: `python3 scripts/check_buzz_health.py`
- 監視2点: `gh run view <news_run_id> --repo k-hira-shine/ai-news-collector --log | grep "Collected:"`（legal_rss_count / must_follow_count）
- 品質構造指標: `data/analysis/<date>_<morning|evening>.json` の top_articles/category_summaries/action_items/fallback_used_stages

> **Buzz縮小プロファイルは不採用が確定（2026-06-15）**: 初回実本番で
> prior_top20_retention=55%・ranking_overlap=70%とガードレール警告。
> 根本原因は `merge_account_data` が日付順100件で保持するため、縮小日に
> 新規投稿が流入すると古い高エンゲージ投稿が枠落ちし、いいね順ランキングが崩れる
> **構造的問題**（いいね陳腐化ではない）。節約は月$0.9未満でApifyは既に予算内のため、
> 品質最優先で `config.yaml` の `active_profile` を `reduced`→`full` に変更（恒久）。
> 再度コスト削減するなら per-run縮小ではなく頻度削減（週3→週2、各回フル）が筋。

> **①stage2/3 Flash化は完了**: 6/14・6/15ともPro使用ゼロ、per-runで約1/4
> （stage2 $0.111→$0.029、stage3 $0.026→$0.006）。日次Geminiも
> 6/13 $0.76→6/14 $0.258→6/15 $0.177へ低下。ロールバック不要。

> **①stage2/3 Flash化は完了**: 6/14・6/15ともPro使用ゼロ、per-runで約1/4
> （stage2 $0.111→$0.029、stage3 $0.026→$0.006）。日次Geminiも
> 6/13 $0.76→6/14 $0.258→6/15 $0.177へ低下。ロールバック不要。

---

## 2026-06-16 日次チェック（法務機能 初反映=正常 / コスト予算内 / エラーなし）

- **GitHub Actions**: 全ジョブ success。AI News Collector 朝便（6/16 03:29 JST）正常完了。Buzz/Money/pages も成功。
- **法務ニュース機能 初反映 ✅**: collect ログで `Legal RSS total: 36 items (last 5d)`、
  stage1(Flash)除外/dedup後 `legal_rss_count: 3` が本収集へ。流入は The Verge Policy 10・EFF 6・INTERNET Watch 20。
  広めの法務フィードでも stage1 が AI 無関係記事を自動除外する設計どおりに機能。残: index「規制/政策」のリンク一覧の目視確認。
- **Apify**: 施策後平均 **$9.50/月**（目標$12以内）。6/15単日 $0.4008（Buzz full の日、第3列 $0.2262）。
  **正式7日移動平均判定は6/17**（法務Xクエリ2本追加の増分も併せて確認）。
- **Gemini**: 6/15 **$0.1771**、100% Flash・Pro=$0。stage2/3 Flash化を維持（ロールバック不要）。
- **GH_PAT**: revoke 済みで止血継続。buzz.html に生トークンなし。根本対応（サーバー側中継）は未了。

### 品質劣化チェック（コスト削減後）→ 劣化なしと判定

直近のコスト削減（stage2/3 Flash化・Lite翻訳・Buzz full戻し・法務追加）が出力品質を落としていないかを `data/analysis/*.json` の5月〜6/16比較で検証。

1. **stage2/3 Flash化（最大リスク）→ 劣化なし**。構造指標が Pro 時代と同一を維持:
   `top_articles`=10件・`category_summaries`=5〜6・`action_items`=5・`fallback_used_stages`=[]
   （※フォールバックはむしろPro時代の5/16・5/29で発生、Flash化後はゼロ）。
   文章品質も Pro(6/13) vs Flash(6/16) を実読比較し遜色なし（trend要約・importance_reason の因果記述・
   category要約のkey_articles すべて同等）。唯一 `trend_summary` 文字数がFlashでやや短め＆ばらつき
   （6/15夜206が最短）だが Pro時代も247〜269の日があり**変動の範囲内**（6/16は288に回復）。
2. **Lite翻訳 → 問題なし**（arxiv/hn/buzz_discovery のLite翻訳はエラー・リトライなし）。
3. **法務追加のノイズ → 抑制されている**（stage1 Flash が AI無関係を除外。6/16トップは法務でなくClaudeエージェント機能）。

**結論**: コスト59%削減（$22.93→$9.50/月相当）に対し出力品質は維持。ロールバック不要。

#### 残す監視ポイント（劣化ではないが要観察）
- **法務RSS流入量のばらつき**: 6/15夕便は `legal_rss_count: 48`（収集137件の35%）と多い回あり。
  stage1で除外されるが、index「規制/政策」が法務一色にならないか数日は目視確認。
- **`must_follow_count` のゼロ回**: 6/15夕便で `must_follow_count: 0`（6/16朝は69で正常）。
  収集サイクル差分の可能性大だが、連続ゼロなら要調査。

---

## 2026-06-15 法務ニュース収集機能の追加＋GH_PAT漏洩対応＋カテゴリ別表示改善

ユーザー要望「AIの著作権・法律・規約・裁判/係争のニュースを集めたい」への対応。
**新ページは作らず既存パイプライン（index.html の「規制/政策」カテゴリ）に合流**する方針を採用
（ユーザー選択）。作業中に GH_PAT トークン漏洩を発見し対応。

### 1. 法務ニュース収集の追加（commit `46572c7`、push済み）

- **X検索クエリ2本追加**（`config.yaml` `x_twitter.search_queries`、5→7本）:
  - 英語: `"AI copyright" OR "AI lawsuit" OR "AI litigation" OR "fair use" OR "training data" OR "EU AI Act" OR "AI regulation" OR "terms of service" AI`（`min_faves:30`）→ 米EU・利用規約
  - 日本語: `AI著作権 OR 生成AI 著作権 OR AI規制 OR AI 法律 OR AI 訴訟 OR AI 裁判 OR AI 係争 OR AI 利用規約 OR AI ガイドライン`
- **法務RSS 8フィードを追加**（`config.yaml` 新設 `legal_news`、`max_age_days:5`、課金ゼロ）:
  米EU=IPWatchdog / Copyright Lately / JURIST / The Verge Policy / Ars Technica Policy / EFF、
  日本=STORIA法律事務所 / INTERNET Watch。
- **`collector.py`**: `collect_legal_rss()` を新規追加し `collect_all()` に合流。
  アイテムは `source="rss"` のアナライザ互換形。X用の2日フィルタは通さず legal 独自の age 窓で絞る。
  dedup は共有 `SeenURLsCache`。**stage1（Flash）が AI 無関係記事を自動除外**するため広めの法務フィードでも安全。
- **`main.py`**: `x_count` から法務RSS分を差し引き、`legal_rss_count` を別計上。
- スモークテスト: `collect_legal_rss` 単体で45件取得を確認（INTERNET Watch 20・The Verge 10・EFF 8・IPWatchdog 7。
  Copyright Lately/JURIST/Ars/STORIA は5日窓に新着なしで0、新着時に寄与）。
- **コスト**: RSS=$0、Gemini=Flash無料枠。X クエリ分のみで**月+$1未満**見込み。6/17の `check_cost` で増分確認。
- **アラート安全性**: アラートは `x_meta` 基準で `stats.total/x_count` を見ないため、RSS合流でX障害検知は壊れない。

### 2. カテゴリ別表示の改善（commit `b94dc68`、push済み）

- ユーザーが「index に法令ニュースのまとまりが無い」と指摘。原因は2つ:
  (1) push が当日朝ランの後で**まだ未反映**、(2) **`dashboard.py` の「📁 カテゴリ別」が
  `category_summaries` の要約文だけ表示し、`key_articles`（リンク付き記事5件）を捨てていた**。
- `dashboard.py` のカテゴリカードに `key_articles` のリンク一覧（タイトル＋要約）を表示するよう修正。
  CSS（`.cat-articles` 等）も追加。ローカル再生成で「規制/政策」にリンク一覧が出ることを確認済み。Gemini追加コストなし。
- → 「📁 カテゴリ別 → 規制/政策」が法務ニュースの一覧場所になる。法務収集＋この表示は同じ collect ランで反映。

### 3. GH_PATトークン漏洩の発見と対応（**要フォロー**）

- 同一の classic PAT `ghp_mLJz…` が **3か所で共用**されていた:
  (1) ローカル git remote URL、(2) GitHub Actions シークレット `GH_PAT`、
  (3) **公開ページ `docs/buzz.html` に2分割で埋め込み**（`build_buzz.py` L240、シークレットスキャン回避目的）。
  → GitHub Pages 上で誰でも復元可能な状態だった。用途は buzz.html の「ハンドル入力→収集起動」ボタン
  （`api.github.com .../buzz-collect.yml/dispatches` を叩く、build_buzz.py L428-445）。
- **対応済み**:
  - ローカル remote から token 除去、`credential.helper=osxkeychain` に変更（コミット不要・ローカル設定）。
  - **ユーザーが GitHub で classic PAT `ai-news-collector-2`（repo,workflow）を Delete＝revoke（止血完了）**。
- **残（未了）**: buzz ボタンの復旧（新トークン発行→`GH_PAT`シークレット更新→buzz再ビルド）。
  ただし**ユーザーは buzz ボタンを使っていないため当面放置でOK**（埋め込みトークンは死んでいるので害なし）。
- **根本問題（将来 buzz ボタンを使う時）**: 新トークンを再発行してもまた公開ページに埋め込まれる構造。
  正しくは `workers/`（Cloudflare Worker）等のサーバー側中継経由で起動し、PATをブラウザに出さないこと。
  最小権限化（fine-grained / `workflow`スコープのみ）も推奨。buzz改修時はこの埋め込み方式を温存しない。
- 別トークン `ai-news-collector`（repo のみ・無期限・用途不明・5週間前使用）が残存。未使用なら掃除推奨（任意）。

### 未追跡ファイル（今回も未関与）

`requirements-sdk.txt` / `scripts/cursor_sdk_try.py` には触れていない（従来どおり）。

---

## 2026-06-15 日次チェック（エラー＋コスト＋Buzz初回縮小）

- **エラー**: GitHub Actions（ai-news-collector）直近すべて success
  （AI News 朝/夕、AI Money、Buzz Ranking、pages build）。失敗・キャンセルなし。
  jp-voyeur のエラーメールもなし。
- **Apify**（check_cost.py）: 6/15 $0.4008/日（うち Buzz縮小$0.0561＋手動フル$0.1701）。
  施策後（5/15〜）平均 $9.50/月換算（59%削減）。7日移動平均の正式判定は6/17。
- **Gemini ①効果（日次測定・6/14繰越）→ 確認OK・完了**:
  6/14 $0.258 / 6/15 $0.177 ともPro使用ゼロ。per-runでstage2 Flash $0.029
  （Pro $0.111）、stage3 Flash $0.006（Pro $0.026）= 合計約1/4。ロールバック不要。
- **Buzz 初回縮小収集（本日が最初の観測日）→ ガードレール警告→手動フルで即復旧**:
  - 縮小(reduced)初回: fetched=476, new=214, retained=1262,
    `prior_top20_retention=55.0%`（基準95%未達）、
    `ranking_top20_overlap=70.0%`（基準75%未達）、`guardrail_status=warning`、
    cost $0.0561。`gap_risk_accounts`は空・`fallback_triggered=false`で
    **データ欠落ではなく「古い投稿のいいね数が未更新→順位ずれ」**（既知の失敗モード）。
  - ユーザー判断で**今すぐ手動 profile=full 収集**を実施（run `27509414816`、成功）。
    結果: retention=95.0% / overlap=100.0% / `guardrail_status=pass` で即復旧。
    cost $0.1701（フル日想定$0.17〜0.20内）。
  - **重要な実測知見**: バックテストは縮小日でも保持率99%予測だったが、
    実本番の初回縮小は1日で基準割れ。縮小方式(月/水)はランキング鮮度を
    維持できない可能性が高い。6/17の2回目で再度warningなら
    `active_profile: full` へ戻す（次回アクション①参照）。

---

## 2026-06-14 日次チェック（エラー＋コスト）

- **エラー**: GitHub Actions（ai-news-collector）直近の定期実行はすべて success
  （AI News 6/13夕、AI Money 6/13、pages build）。失敗・キャンセルは pages の
  重複トリガ1件のみで無害。jp-voyeur もエラーメールなし。
- **Apify**（check_cost.py）: 6/13 $0.2525/日。施策後平均 $9.33/月換算
  （〜6/10の$21.01比 56%削減）。7日移動平均の正式判定は予定どおり6/17。
- **Gemini**（gemini_usage.py）: 6/13 $0.68/日。stage2/3 Flash化はper-runで
  効果確認（stage2 Pro $0.111→Flash $0.040、stage3 Pro $0.0261→Flash $0.0066）。
- **①効果の日次測定は6/15へ繰越**: 日次チェック実施が JST04:30 で、6/14朝8:34の
  本番Flash実行前だったため、日次集計ベースの1/4化はまだ未確定。per-run経済性が
  期待どおりのため、本番品質に問題が出ない限りロールバック不要の見込み。

---

## 2026-06-13 コスト削減①: stage2/3をPro→Flash化

- Geminiコストの42%（月換算約$6.2）を占める analyzer stage2/3 を
  検証付きでFlashへ移行。期待削減は約$4.6/月（Pro比1/4）。
- 検証: `verify-stage2-flash.yml` / `scripts/verify_stage2_flash.py`（新規作成）。
  同一のstage1結果を両モデルのstage2に与えて比較（run `27440125545`）。
  - 選定jaccard `0.818`（基準0.8）/ カテゴリ一致 `100%`（基準0.85）/
    順位相関 `0.842`（基準0.7）→ 全基準合格。
  - 定性: trend_summary/x_trendsは遜色なし（Flashは批判的トピックも拾う）。
    stage3のタイトルがやや誇張気味だが許容範囲。
  - 詳細: `data/stage2_verification_gemini-2.5-pro_vs_gemini-2.5-flash.json`
- **次回確認（6/14の日次チェック）**:
  - `gemini_usage.py` で `analyzer:stage2/3` が約1/4に下がったか。
  - 6/13朝・夕の本番レポート品質に劣化がないか目視。
  - 劣化があれば config.yaml の `stage2_analysis` を `gemini-2.5-pro` に戻す。
- 残りの候補の検証結果（2026-06-13 同日実施）:
  - **④ post_generator・buzz/omni翻訳のLite化 → スキップ（根拠あり）**。
    対象はすべてX投稿のトーン再現タスクで、6/10の翻訳モデル検証で
    x_postカテゴリはFlashがLiteに5勝0敗（`data/translation_model_verification.json`）。
    Lite化は検証済みの判断に逆行するため見送り。
  - **③ sns/tools analyzerのLite化 → 検証の結果、不合格で見送り**。
    `verify-sns-tools-lite.yml` / `scripts/verify_sns_tools_lite.py`（新規作成、
    run `27440994588`）。SNS: jaccard `0.61`・カテゴリ一致 `20%`（Liteは過剰選定
    41件 vs 25件）。Tools: jaccard `0.714`・カテゴリ一致 `100%`（基準jaccard 0.8未達）。
    判定タスクでもLiteは品質不足。Flash維持が確定。
    - 付随修正: `tools_analyzer.py` のthinking_budgetをハードコード128から
      config（`analysis.thinking_budget.tools`、デフォルト128で本番挙動不変）に変更。
    - 初回検証はLiteがthinking_budget=128を拒否して全バッチ400エラー→
      Liteはthinking無効(0)で測るよう修正済み。Lite採用時はこの制約に注意。
  - **② Batch API化 → 見送り決定（2026-06-13、ユーザー判断）**。
    削減は約$5/月にとどまる一方、全パイプラインの投入/回収分割と
    完了時刻が読めない制約（朝レポートの定時性と相性が悪い）が重い。
    再検討条件: 収集量拡大でGemini費用が月$30〜50規模になったとき。

  コスト削減シリーズはここで完了。最終到達点: Apify `$9.99/月` +
  Gemini 約`$10/月`（①効果確認前の見込み）= **合計約$20/月**。
  残る確認は6/14日次チェックでの①の効果測定のみ。

---

## 2026-06-13 日次チェック結果

### 定期実行

- AI News（朝・夕）/ Money / Buzz / Pages すべて成功。
- `Buzz Daily Health Check` の初回スケジュール実行は予定4:15に対し
  4:55 JSTに発火し成功（GitHub cron遅延、run `27439496147`）。
  出力は「品質メトリクスは次回Buzz収集から記録」で正常。

### Apify費用判定

- `check_cost.py` 実行。施策後（6/11〜6/12）の平均 `$0.3329/日`、
  月換算 `$9.99` で基準の `$12` 以下 → **暫定合格**。
- ただし施策後データはまだ2日分。施策後7日が揃う
  **6/17に再判定**するのが正式（既存の6/17 Buzzチェックと同日）。

### Money分析0件問題 → 解消

- 6/12夜の実行（run `27433703521`）で
  prefilter 182→110、採用10件（postfilter 10→10）。
- 0件は6/12朝の単発事象と判断。フィルター修正は不要。

### jp-voyeur-news-collector 通知障害（エラーメール対応）

- `Collect JP Voyeur News` が6/11 21:23 JSTから3連続失敗。
- 原因: Discord Webhookが404（削除/無効化）。収集・Gemini分析は成功。
- 副作用: notify失敗→exit 1でcommitステップが飛び、
  **6/12分の収集データ18件が未保存のまま消失**（リポジトリは6/11まで）。
- 対応済み: commitステップに `if: ${{ !cancelled() }}` を追加し、
  通知失敗でもデータを保存するよう修正（commit `6f727c0`、push済み）。
- **解決済み**: Discordサーバー自体を削除済みとのことで、通知機能を撤去。
  ワークフローからwebhook envを削除（commit `c9e1d42`）、
  リポジトリSecret `JP_VOYEUR_DISCORD_WEBHOOK_URL` も削除。
  手動run `27439196583` で正常終了を確認（16件収集、notify skip、データcommit済み）。
  以後は収集とリポジトリへの蓄積のみ動作する。
  収集結果を見たいときは同リポジトリの `data/daily/` を直接参照。

### GitHub Actions Node 24強制（6/16）対応

- GitHubが2026-06-16からactionsをNode.js 24で強制実行する。
- jp-voyeurの `collect.yml` が古いaction（checkout@v4 / setup-python@v5）
  だったため v5 / v6 に更新（commit `8ba64ca`、push済み）。
- ai-news-collector側は全11ワークフローとも対応済みを確認。対応不要。

---

## 2026-06-12 最終確認と次回アクション

本日の実装・テスト・本番反映は完了。追加の緊急作業はない。

### 本日の確認結果

- AI News / Money・SNS / Buzz / Pagesの定期実行は成功。
- Buzz品質維持型コスト削減と日次監視を本番反映済み。
- `Buzz Daily Health Check`初回手動run `27372539735`成功。
- Gemini推定費用:
  - 2026-06-11: `$0.8083`
  - 2026-06-12: `$0.3570`
  - 6月12日は前日比で改善。
- Apify 6月12日合計: `$0.4128`
- ローカルの既存未追跡ファイル
  `requirements-sdk.txt` / `scripts/cursor_sdk_try.py`には触れていない。

### 要注意: Money分析0件

- 2026-06-12: Money 116件収集、事前候補96件、Gemini採用0件。
- APIエラーではなく、Geminiが全候補を非該当判定した。
- 入力には具体的な収益事例も含まれていたため、品質フィルターまたは
  プロンプトが過剰な可能性を残す。
- **次回Money実行でも0件、または具体的事例を継続して落とす場合は修正する。**
- 最初に確認するもの:
  - 最新`AI Money Cases Collector`ログの
    `Money prefilter` / `Money analysis batch` / `Money postfilter`
  - `data/money/YYYY-MM-DD.jsonl`
  - `money_analyzer.py`のプロンプト
  - `analysis_quality.py`の事前・事後フィルター

### 日付付きの次回確認

1. **2026-06-13**
   - `python3 check_cost.py`
   - Apify 7日移動平均を正式判定。合格は月換算`$12`以下。
   - Moneyの次回結果を確認。0件継続ならフィルター過剰を調査する。
2. **2026-06-15**
   - Buzz最初の7日・50件縮小実行を確認。
   - 費用、新着件数、`gap_risk_accounts`、`guardrail_status`を見る。
3. **2026-06-17**
   - Buzz縮小実行の2回目。初回と比較して安定性を確認する。
4. **2026-06-19**
   - Buzz最初の30日・100件フル再同期。
   - `ranking_top20_overlap_pct >= 75%`を確認する。

---

## 次回最初に確認: Buzzコスト削減テストの経過観察

> **これは確定削減ではなく、品質を毎日監視しながら進める段階的テスト。**
> コストだけを見て成功扱いにしない。新着取得、ランキング品質、欠落リスクを
> 同時に確認し、悪化時はフル収集へ戻す。

### 2026-06-12に実施した変更

- 実装コミット: `47ceb10` (`feat: reduce buzz cost with quality guardrails`)
- Buzz収集をハイブリッド化:
  - 月曜・水曜: 直近7日、1アカウント最大50件
  - 金曜: 直近30日、1アカウント最大100件で全体再同期
- 縮小取得した投稿を既存データへURL単位でマージし、30日・各100件の
  ランキング母集団を維持する。
- 50件上限に達し、取得した最古投稿が前回最新投稿より新しい場合は、
  欠落リスクと判定して同じ実行内で30日・100件へ自動フォールバックする。
- 各実行の品質・費用を`data/buzz_collection_metrics.jsonl`へ追記する。
- `.github/workflows/buzz-health-check.yml`を追加。
  毎日JST 04:15に有料APIを呼ばず、鮮度と品質指標を確認する。
- 手動実行時は`profile=full`で即座にフル収集へ戻せる。
  恒久的に戻す場合は`config.yaml`の
  `buzz_collection.active_profile`を`full`へ変更する。

### 実データによる事前バックテスト

比較対象:

- 開始データ: 2026-06-10のBuzzスナップショット
- 正解データ: 2026-06-12の30日・100件フル収集
- テスト条件: 7日・50件を取得したと仮定し、開始データへ差分マージ

結果:

| 指標 | 結果 | 判定 |
|---|---:|---|
| フル取得件数 | 1,309件 | 基準 |
| 縮小取得件数 | 410件 | 68.7%減 |
| 新着200件の保持率 | 99.0% | 合格 |
| 30日URL母集団の保持率 | 99.0% | 合格 |
| 全体ランキング上位20件一致率 | 100.0% | 合格 |
| 欠落リスクアカウント | 0件 | 合格 |
| Buzz月額見込み | `$2.36 → $1.28` | 約46%減 |

最初に「毎回7日・50件」だけで試算した際は、過去投稿のいいね数が
更新されず上位20件一致率が80%まで落ちた。このため、毎週金曜の
フル再同期を残すハイブリッド方式へ修正した。

### 毎日の確認項目

```bash
gh run list --workflow "Buzz Daily Health Check" --limit 5
gh run list --workflow "Buzz Ranking Collector" --limit 5
python3 scripts/check_buzz_health.py
tail -5 data/buzz_collection_metrics.jsonl
python3 check_cost.py
```

見る項目:

1. `guardrail_status`が`pass`または自動復旧済みの`fallback`
2. `gap_risk_accounts`が空
3. `fallback_triggered`が通常は`false`
4. `new_items`が前回までの傾向から急減していない
5. `prior_top20_retention_pct`が95%以上
6. 金曜フル再同期の`ranking_top20_overlap_pct`が75%以上
7. 縮小日のApifyコストが概ね`$0.05〜0.08/回`
8. 金曜フル日のApifyコストが概ね`$0.17〜0.20/回`

### 最初の観測日

- **2026-06-15（月）**: 最初の縮小収集。取得件数、費用、新着、欠落リスク確認。
- **2026-06-17（水）**: 2回目の縮小収集。同じ指標が安定しているか確認。
- **2026-06-19（金）**: 最初のフル再同期。
  `ranking_top20_overlap_pct`で縮小期間中のランキング劣化を判定。
- 少なくとも2026-06-26まで毎日ヘルスチェックを確認し、2週間分の実績で
  設定を維持するか判断する。

### 合格条件

- 新着保持率の実測が概ね98%以上。
- 欠落リスクが継続発生しない。
- 週次フル再同期時の上位20件一致率が75%以上。
- 公開ページのランキング件数と主要上位投稿に明らかな欠落がない。
- Buzz月額換算が従来比30%以上削減。

### 異常判定と復旧

- `gap_risk_accounts`あり:
  同じ実行内で自動フル再取得される。`fallback_triggered=true`を確認する。
- `guardrail_status=warning`、上位20件一致率75%未満、または新着急減:
  次回を手動`profile=full`で実行する。
- 問題が2回続く:
  `config.yaml`の`buzz_collection.active_profile: "full"`へ戻す。
- 調査開始箇所:
  `data/buzz_collection_metrics.jsonl`、`run_buzz.py`の
  `collection_gap_risk()` / `merge_account_data()`、
  GitHub Actionsの`Buzz Ranking Collector`ログ。

### テスト

- `python3 -m unittest discover -s tests -p 'test_*.py' -v`
- 87テスト成功
- `python3 -m py_compile run_buzz.py scripts/check_buzz_health.py`
- `config.yaml`、Buzz関連workflowのYAML parse成功
- `Buzz Daily Health Check`初回手動run `27372539735` 成功。
  初回はメトリクス未生成の互換モードで、2026-06-15のBuzz収集後から
  `data/buzz_collection_metrics.jsonl`を使う実測監視へ切り替わる。

---

## 次回最初に確認: Money/SNS品質・Geminiコスト改善

> **エージェントへ**: 2026-06-12朝の`AI Money Cases Collector`完了後に
> 以下を確認する。6月13日のApify判定も期日が来たら冒頭でリマインドする。

### 2026-06-11に実施した変更

- コミット: `2686829` (`fix: improve money and sns analysis quality`)
- `main`へpush済み。GitHub Pages run `27302356972`も成功。
- `analysis_quality.py`を追加し、Money/SNS共通で以下を実施:
  - Gemini投入前: 最低フォロワー未満、短い返信、明白な販促、
    権利侵害を収益手法として勧める投稿を除外
  - Gemini判定後: 販促、権利侵害推奨、近似重複を再除外
  - 権利侵害への批判・注意喚起は保持
- Money/SNSプロンプトにも販促・権利侵害推奨の除外条件を明記。
- SNSの通常実行時バックログ追加を`500件`から`0件`へ変更。
  不採用投稿は処理済みIDに残らず毎日再分析されていたため、空回りを停止した。
- 2026-06-11朝の既存結果を再処理:
  - Money: 9件 → 5件
  - SNS: 90件 → 89件
  - `docs/money.html` / `docs/sns_success.html`再生成済み
- 最終テスト: `95 passed, 17 subtests passed`

### 次回実行後の確認手順（2026-06-12朝）

```bash
git fetch origin main
git pull --ff-only
gh run list --repo k-hira-shine/ai-news-collector --limit 10
python3 gemini_usage.py
python3 check_cost.py
```

最新のMoney/SNS分析とログも確認する。

```bash
ls -lt data/money/*_analysis.json data/sns_success/*_analysis.json | head
tail -20 data/logs/2026-06-12.jsonl
```

### 合格条件

1. `AI Money Cases Collector`が成功。
2. Money/SNS上位に、無料勉強会・特典配布などの販促主体投稿がない。
3. 無断転載・違法アップロードを稼ぎ方として勧める投稿がない。
4. 同一本文の微修正版が複数採用されていない。
5. 権利侵害への批判・注意喚起は誤って消えていない。
6. `gemini_usage.py`で`sns_analyzer`の呼び出し回数・費用が6/11より減少。

### 比較基準と見込み

- 6/11実測: Gemini合計 `$0.6180/日`
- 6/11の`sns_analyzer`: 21回、約`$0.2658`
- 修正前データでの事前フィルター試算:
  - Money候補 229件 → 144件（37.1%減）
  - SNS候補 512件 → 262件（48.8%減）
- バックログ再分析停止も含め、Gemini全体で約30〜35%削減を見込む。
  ただし確定値ではないため、6/12実測を優先する。

### 異常時の調査・復旧

- 誤除外が多い:
  - `analysis_quality.py`のマーカーと類似判定閾値を確認
  - `tests/test_analysis_quality.py`へ再現ケースを追加してから修正
- 販促や権利侵害推奨が残る:
  - `analysis_quality.py`のマーカーを追加
  - Money/SNS両方に影響するため全テストを実行
- SNSの情報量が不足:
  - `config.yaml`の`sns_success.backlog_limit_per_run`を小さな値で試す
  - ただし不採用投稿の再分析が再発するため、安易に500へ戻さない
- Flash自体の品質劣化が明確な場合のみ、
  `config.yaml`の`analysis.models.stage1_filter`を
  `gemini-2.5-pro`へ戻す。今回の問題は主にプロンプト・後処理側だった。

### 2026-06-13頃の確認

- `python3 check_cost.py`でApify 7日移動平均を確認。
- 合格: 月換算`$12`以下。
- Geminiも3日分の実測から月額を再計算する。

### 既知の警告

- GitHub Pages runでNode.js 20廃止予定の警告が出た。
- `pages-build-deployment`内部の`actions/checkout@v4` /
  `actions/upload-artifact@v4`由来で、今回のリポジトリ変更には影響なし。
- GitHub側の移行状況を見て対応する。現時点では作業不要。

---

## 2026-06-10 Gemini新機能バズ初期アーカイブ完了

### 運用方針

- 定期実行しない。
- 必要なタイミングで検索条件を設計し、一気に追加収集する単発アーカイブ。
- GitHub Actionsの`Gemini Buzz One-off Research`は手動実行専用。
- 今後もworkflowへ`schedule`を追加しない。

### 今回の結果

- 対象期間: 2024-06-10〜2026-06-10
- ランキング: 26件から55件へ増加
- 内訳: 驚き22件、新機能33件
- Apify合計: 約`$0.0568`
- 対応するAI二次判定・翻訳: 約`$0.0153`
- 合計: 約`$0.0721`
- 最終テスト: `91 passed, 17 subtests passed`

検索プロファイル`broad`、`features`、`feature-expansion`を追加し、
別製品、販促、反応誘導、将来予測だけの投稿を除外した。

### 次回の最優先課題

品質基準を維持しながら、取得件数を55件からさらに増やす。
定期化ではなく、次回も目標件数と費用上限を決めて単発実行する。

有力な手段は、機能名辞書の追加、日本語表記揺れ、期間分割、
`max-items-per-query`増加、`min_faves`帯の分割。本文類似による
転載整理も必要。

### 次回の開始手順

1. `.cursor/docs/gemini-buzz-research-log.md`を読む。
2. `data/gemini_buzz/RESEARCH_SUMMARY.md`で今回の費用と件数を確認する。
3. `ranking.json`の55件を基準集合として保持する。
4. 目標純増、追加クエリ、期間分割、取得上限、総費用上限を決める。
5. 手動Actionsで小さく比較し、効率の良い検索群をまとめて実行する。
6. 終了後に純増件数、費用、除外理由、品質を記録する。

### 合格条件と異常判定

- 合格: 品質を落とさず、まとまった純増を得られる。
- 異常: 別製品・販促・推測投稿が増える、純増がほぼない、
  または費用上限を超える。
- 問題時は`search_manifest.json`のクエリ別取得数・費用と、
  `discovery_reviews.json`の判定理由を最初に確認する。

関連コミット:

- `38c8cbe`: 主要機能名検索
- `a8e6aa7`: 品質フィルタ強化
- `97e01ab`: 追加機能検索
- `303689e`: 将来予測の除外
- `06136f2`: 調査結果記録
- `dd42444`: 単発運用方針・件数拡大課題・引き継ぎ確定

---

## 2026-06-10 朝セッションの総括と経過観察

> 6/11確認は完了。残る6/13の確認は、文書先頭の次回アクション節を参照する。

### コスト状況（このセッションで判明・対策済み）

| 項目 | 実測 | 対策後の見込み |
|---|---|---|
| Apify | 月$20.42（基準 $23.47） | 月$8〜12（6/10 実装済み、測定中） |
| Gemini API | 月約¥2,900ペース（Pro が92%） | Pro→Flash 切替で大幅減（6/10 実装済み、測定中） |

- Gemini は **有料 Tier 1**（プロジェクト名 Sedori、本プロジェクト専用とユーザー確認済み）。無料枠は別プロジェクトのキーでのみ使える（公式確認済み、詳細は `.cursor/docs/gemini-cost-reduction-plan.md`）。

### 6/11確認結果（完了）

1. Flash化: News Stage1 / Money / SNSはFlash、News Stage2/3のみProで意図どおり。
2. 品質: Newsは問題なし。Money/SNSは販促・重複・権利侵害推奨の混入を確認し、
   モデルをProへ戻さず共通品質フィルターで修正。
3. Gemini: 6/11合計`$0.6180`。最大費用源は`sns_analyzer`の約`$0.2658`。
4. Apify: 6/11合計`$0.2196/日`、単日月換算`$6.59`。
   7日移動平均の正式判定は6/13に実施。

### 6/13頃にやること

- Apify 7日移動平均の判定（合格: 月換算$12以下）。`python3 check_cost.py`。
- Gemini 実測3日分で月額を再計算し、無料キー切替（月¥0化）を検討する価値があるか判断。

### 未実施の残タスク（優先度順）

1. G4: 全 Gemini 呼び出しに max_output_tokens 設定（暴走出力の保険、軽作業）
2. G6: dashboard.py の HN 二重翻訳解消（効果数円、低優先）
3. 無料キー切替の試行（実測を見てから判断。リスク: Pro無料枠50〜100回/日、データがGoogle製品改善に利用される）
4. Gemini新機能バズの件数拡大（単発実行。定期化しない）

### 翻訳モデルの用途別切替（2026-06-10実測）

- 比較: `gemini-2.5-flash` vs `gemini-2.5-flash-lite`
- サンプル: HNタイトル、arXiv、Gemini公式短要約、X投稿を各5件（計20件）
- 費用: Flash `$0.004587` / Flash-Lite `$0.000868`（同一入力で約81%削減）
- 全体品質: Flash `4.787` / Flash-Lite `4.700`
- 採用判断:
  - HNタイトル、arXiv、Gemini公式の再翻訳: Flash-Lite
  - Geminiバズ、Gemini OmniなどX投稿全文: Flash維持
  - ニュース分析、重要度判定、Money/SNS分析: 変更なし
- 理由: X投稿は正確性は同等だが、熱量・口調の再現で5件すべてFlashが勝利。
- 共通設定: `config.yaml` の `analysis.models.translation` と
  `analysis.models.social_translation`
- 比較結果: `data/translation_model_verification.json`
- 復旧: 品質問題時は `translation` を `gemini-2.5-flash` に戻す。
- 次回確認: 定期実行後に `python3 gemini_usage.py` で
  `hn_translate` / `arxiv_translate` のモデルと実測費用を確認する。
- Geminiバズの英語投稿63件はFlashで初回翻訳・URLキャッシュ済み。
  今後は新規英語投稿だけ翻訳される。

### このセッションで実装したもの（詳細は各日付の節）

- gemini-buzz ページ: 日付の日本語化、表示名、ER表示、並べ替え（`e751e38`〜`d0da798`）
- ナビ欠落の恒久対策 `sync_nav.py`（`1a46c63`）
- Gemini トークン計測 `gemini_usage.py` + 全10箇所組込み、post_generator の Pro 誤参照修正（`0c4f7a5`）
- stage1検証WF `verify-stage1-flash.yml`（Pro vs Flash / Pro vs Pro 実施済み）
- stage1系（ニュース/Money/SNS）の Flash 切替（`8b577ba`）

---

## 次回最初に確認: Gemini活用法バズ調査

次回この調査を再開するときは、コード変更や再検索の前に必ず以下を読む。

1. `.cursor/docs/gemini-buzz-research-log.md`
2. `data/gemini_buzz/search_manifest.json`
3. `data/gemini_buzz/ranking.json`

Gemini自身の新機能・新モデル・具体デモを検索する`discovery`モードを完成。
過去2年を一般語と機能名で単発検索し、55件を累積ランキング化した。
厳格ルールとFlash-Lite二次判定の両方を通過した投稿だけ採用する。
英語投稿は日本語表示。次回は定期化ではなく、検索語・期間分割・取得上限を
拡張し、品質を維持したまま件数を大きく増やす。

---

## 2026-06-10 stage1系をFlash化（G3実行）+ toolsバックフィル調査

- 実行内容（ユーザー承認済み）: config.yaml `models.stage1_filter` を `gemini-2.5-pro` → `gemini-2.5-flash` に変更。
  - 影響範囲: analyzer.py Stage1（ニュース1次フィルタ）、money_analyzer.py、sns_analyzer.py の3箇所。Stage2/3 は Pro 維持。
  - 根拠: 採用判定の Pro 一致率 97.6%（Pro自身の揺らぎ 82.9% より高い）。Money/SNS は未検証のままの切替（ユーザー判断）。
  - 期待効果: Pro費用（月¥2,450、全体の92%）の大幅削減。実測は `python3 gemini_usage.py` で確認。
- **品質の経過観察（明日6/11）**: data/analysis の新規分析、money/sns ページの要約品質に劣化がないか目視確認。劣化が大きければ config の stage1_filter を Pro に戻すだけで復旧。
- toolsバックフィル調査結果: **空回りしていない**。8,541件中、未分類6,160件の内訳は「tool_name無し=6,159件（設計上の対象外）」+「処理待ち=1件」。バックフィルは実質完了済みで、毎回の処理対象は約1件 → コスト影響ほぼゼロ。自己修復機能として enabled のまま維持。
- 関連コミット: 本ターンでコミット

## 2026-06-10 G3追加検証: Pro vs Pro 揺らぎ基準を測定

- 結果（`data/stage1_verification_gemini-2.5-pro_vs_gemini-2.5-pro.json`）:
  - Pro自身の実行揺らぎ: 採用一致 0.829 / スコア差 0.68 / カテゴリ一致 0.941 / Top30重複 0.875
  - 比較すると Flash は「採用判定」は揺らぎ以下（=安全）、「スコア・カテゴリ」は揺らぎ超の実差あり
- 結論（未実行）: ニュース stage1 のみ Flash 化を推奨（Stage2=Pro が最終順位を補正するため）。Money/SNS は2段目補正がなく未検証のため Pro 維持で設定キー分離を提案。**ユーザーの実行判断待ち**。
- 実装する場合: config.yaml `models.stage1_filter` を flash に変更し、money_analyzer.py / sns_analyzer.py の参照キーを新設の Pro キーへ分離する。
- 検証WFは `verify-stage1-flash.yml`（model_a/model_b 指定可、同一指定で揺らぎ測定）。

## 2026-06-10 Gemini コスト削減 G1+G2 実装、G3 検証完了

- 実費確認結果: **有料 Tier 1**。6/1〜9 実費 ¥2,892（月ペース約¥9,600）。**Pro が費用の92%**（28日間 Pro ¥2,450 / Flash ¥206）。Apify（月$20）より大きい。キーは本プロジェクト専用（プロジェクト名 Sedori、ユーザー確認済み）。
- G1 実装: `gemini_usage.py` 新規作成。全10呼び出し箇所（analyzer×stage1-3, money, sns, tools, gemini_collector, post_generator, dashboard, collector×2, gemini_omni）に `log_usage()` を組込み。`data/gemini_usage/YYYY-MM-DD.jsonl` に記録。集計は `python3 gemini_usage.py`。
- G2 実装: post_generator が config の `stage1_filter`(=Pro) を意図せず参照していたのを `fallback`(=Flash) に修正。
- G3 検証結果（42件、HN/arxiv のみ、`data/stage1_flash_verification.json`）:
  - 採用判定の一致率（Jaccard）**0.976** = ほぼ同じ記事を選ぶ
  - 重要度スコア平均差 1.4点（10点中）、カテゴリ一致 0.775、Top30重複 0.667
  - 同一入力の実測: Pro $0.0176 / Flash $0.0043 = **4.1倍差**
  - 未確定: Pro自身の実行ブレ（Pro vs Pro基準）が未測定のため、スコア/カテゴリ差がFlash起因か不明
- 関連コミット: `0c4f7a5`（G1+G2+検証WF）、検証結果は Actions が自動コミット
- 次回確認: G1ログが明日の定期実行から蓄積される。`python3 gemini_usage.py` で日次推定額を確認。stage1のFlash切替はユーザー判断待ち。
- 異常時: 計測が増えない場合は各呼び出し箇所の log_usage 呼び出しと data/gemini_usage/ の push 対象を確認。

## 2026-06-10 Gemini API コスト削減計画を作成（未実装）

- 何をしたか: Gemini API の全利用箇所（9ファイル）を棚卸しし、`.cursor/docs/gemini-cost-reduction-plan.md` に削減計画を作成。施策は**未実装**。
- 最初にやること: ユーザーが Google AI Studio / Cloud 請求で「無料ティアか有料か」「直近30日の実費」を確認する。**無料なら大半の施策は不要**。
- 計画の要点: G1=usage_metadata でトークン計測（前提）、G2=post_generator の意図しない Pro 参照修正、G3=1次フィルタ系を Pro→Flash（検証後）、G4=max_output_tokens 設定。
- 関連コミット: 本ターンでコミット
- 次回確認: ユーザーのプラン確認結果を聞いてから G1/G2 に着手。
- 問題発生時はまず `.cursor/docs/gemini-cost-reduction-plan.md` の利用マップを見る。

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
