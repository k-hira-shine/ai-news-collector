# Gemini Omni — 海外ユーザーの実使用ポスト（動画付き）

収集日: 2026-05-27  
方法: 既存 `data/**/*.jsonl` の抽出 + Apify（`xquik/x-tweet-scraper`）で英語検索 3 クエリ  
コスト: 約 **$0.03**（225 件取得 → 動画付き 139 件 → 実使用っぽい 71 件に絞り込み）

## 条件

| 項目 | 基準 |
|------|------|
| 海外 | 本文に日本語（ひらがな・カタカナ・漢字）なし |
| 動画付き | Apify の `media.type == video`、または投稿にメディアリンク |
| 実使用 | 一人称の生成・編集・検証（`I tested`, `generated`, `referenced`, `spent` 等） |
| 除外 | Google 公式・ニュースまとめ系（testingcatalog 等）・明らかなリード獲得投稿 |

※ X の仕様上、動画は投稿内プレビューまたは `t.co` 経由。一覧の「🎬」は Apify が video と判定したもの。

---

## おすすめ（検証・比較がはっきりしている）

### Ethan Mollick (@emollick) — 学術系、編集デモが明確

- ❤2,889 — [投稿](https://x.com/emollick/status/2057874739817808223)  
  1896 年「列車入站」映像を bullet train / LEGO 等に**ネイティブ編集**した例。他社動画 AI との差は「編集もマルチモーダル」と説明。
- ❤432 — [投稿](https://x.com/emollick/status/2056788122369712148)  
  早期アクセスでの生成例（sea otter × Spirit Airlines ネタ）。

### @aimikoda — Seedance 2.0 との同条件比較

- ❤400 — [投稿](https://x.com/aimikoda/status/2056840097455014017)  
  同じストーリーボード・プロンプトを Seedance 2.0 と Gemini Omni に渡して比較。

### @mikefutia — UGC 広告ワークフロー（24 時間検証）

- ❤390 — [投稿](https://x.com/mikefutia/status/2057492694650515878)  
  「24 hours putting it through its paces」、マルチショット UGC・クリエイター一貫性。末尾にリプ欄誘導あり（プロモ要素あり）。

### @jerrod_lew — Google Flow + Agent での実験

- ❤186 — [投稿](https://x.com/jerrod_lew/status/2057838324140953773)  
  参照クリップを Flow Agent に渡し、別アングルのリプレイ生成。
- ❤163 — [投稿](https://x.com/jerrod_lew/status/2057944349846249975)  
  参照動画から split screen、エージェントは優秀だが動画モデルに課題も。
- ❤86+ — [スタイル変更](https://x.com/jerrod_lew/status/2057100280672739525) ほか複数。

### @denneydara — ワンショット広告テスト

- ❤95 — [投稿](https://x.com/DenneyDara/status/2057844409639551380)  
  「Tested out yesterday」、アニメーション広告向き・雑プロンプトでも一発で良い、と評価。

### @jsfilmz0412 — 否定的レビュー（実使用）

- ❤169 — [投稿](https://x.com/JSFILMZ0412/status/2057926749598736635)  
  Seedance 2.0 Fast vs Omni Flash の最終評価。10 秒制限・検閲・スタイル転送でワークフローに不向き、と結論。

### @thewhizzai — 物理表現の限界テスト

- ❤346 — [投稿](https://x.com/TheWhizzAI/status/2056976857611006319)  
  バックフリップ生成を 3 回試して失敗、と報告。

### @ai_artworkgen — Flow でのシーン編集

- ❤89 — [投稿](https://x.com/ai_artworkgen/status/2057144321653289288)  
  キャラシートからシーン作成後、時間帯・レンダー・天気を会話で変更。

---

## 参考: プラットフォーム連携・プロモ多め（動画はあるが「紹介」色）

`@muvi_ai` 経由の投稿が多数（@romi2656, @caliraval, @ruzainameer 等）。Omni Flash の実出力例としては有用だが、無料枠宣伝が混ざる。

- @inshrah_ali_, @sripathiteja4 — Buzzy 上で会話編集
- @hitpawofficial — Seedance 2.0 との比較動画

---

## 生データ

- 全件（動画付き・海外）: `gemini_omni_overseas_video_posts.json`
- 絞り込み 71 件: `gemini_omni_overseas_hands_on_video.json`

再収集する場合は同じ Apify クエリを `since` を延ばして再実行可能。
