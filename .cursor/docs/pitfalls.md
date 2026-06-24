# Pitfalls

- 2026-05-15: 「優先表示して」を「それ以外は除外して」と誤解し only_major_llm_families フラグで全件非表示にしてしまった。「優先」＝ソート上位、「除外」はユーザーが明示しない限り実装しない
- 2026-05-19: 明日確認用のログ追記は、ローカル編集だけで止めず、ユーザーが共有・継続確認できるよう commit/push の要否まで確認する
- 2026-05-23: collect.yml の 15 分タイムアウトで夜間実行が push 前に中断されサイト更新が止まる。Gemini収集追加後は 45 分以上を確保する
- 2026-05-21: `apify-client>=1.8.0` だけだと CI で 3.0 が入り `timeout_secs` が使えず X 収集が全滅する（`<3.0.0` で pin する）
- 2026-06-04: `INCIDENT_CSS` を `<style>` なしで body/footer 末尾に出すと Home 下部に CSS が生テキスト表示される。`INCIDENT_CSS` は head の `<style>` 内、`INCIDENT_BODY_HTML` はナビ直後。commit 前に `python3 scripts/check_incident_css_leak.py`（詳細: `.cursor/docs/incident-display-css-leak.md`）
- 2026-06-10: ナビは各HTMLにビルド時焼き込みのため、`site_nav.py` にページ追加しても再生成しないページはリンクが欠ける。新ページ追加時は必ず `python3 sync_nav.py` で全 `docs/*.html` を同期し、`docs/` 全体を push する（各収集ワークフローのデプロイ前にも組込済み）
- 2026-06-12: 収集コスト削減は取得件数だけで判断しない。新着保持率、ランキング一致率、欠落リスク、採用件数をbefore/afterで記録し、日次監視と即時復旧手段を用意してから本番設定を縮小する。Buzzでは毎回7日・50件だけにすると古い投稿の反応数が更新されず上位20件一致率が80%まで落ちたため、金曜フル再同期を残した
- 2026-06-25: GitHub Actionsの環境準備stepも本処理と同じ障害源になる。`collect.yml` は `fonts-noto-cjk-extra` 145MB取得が遅く45分timeoutでcancelledになり、収集前に朝便が止まった。大きいapt/Playwright依存stepには個別 `timeout-minutes` を置き、`daily_check.py` では `failure` 固定ではなく実際の `conclusion`（cancelled/failure等）を見る
