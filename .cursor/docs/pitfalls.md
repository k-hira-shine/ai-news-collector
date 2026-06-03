# Pitfalls

- 2026-05-15: 「優先表示して」を「それ以外は除外して」と誤解し only_major_llm_families フラグで全件非表示にしてしまった。「優先」＝ソート上位、「除外」はユーザーが明示しない限り実装しない
- 2026-05-19: 明日確認用のログ追記は、ローカル編集だけで止めず、ユーザーが共有・継続確認できるよう commit/push の要否まで確認する
- 2026-05-23: collect.yml の 15 分タイムアウトで夜間実行が push 前に中断されサイト更新が止まる。Gemini収集追加後は 45 分以上を確保する
- 2026-05-21: `apify-client>=1.8.0` だけだと CI で 3.0 が入り `timeout_secs` が使えず X 収集が全滅する（`<3.0.0` で pin する）
- 2026-06-04: `INCIDENT_CSS` を `<style>` なしで body/footer 末尾に出すと Home 下部に CSS が生テキスト表示される。`INCIDENT_CSS` は head の `<style>` 内、`INCIDENT_BODY_HTML` はナビ直後。commit 前に `python3 scripts/check_incident_css_leak.py`（詳細: `.cursor/docs/incident-display-css-leak.md`）
