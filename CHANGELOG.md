# Changelog

## 2026-04-20 — Discord 配信に図解 PNG を追加

朝便/夕便の Discord 通知の**先頭**に、その日の AI ニュースを 1 枚にまとめた PNG
画像を添付するようにした。追加 LLM コスト: **0 円**（既存の `analysis` dict を
テンプレートに流し込むだけ）。

### 新機能

- [diagram.py](diagram.py): `DiagramBuilder` クラス。`analysis` dict を受け取り
  HTML を生成し、Playwright (Chromium) で PNG にレンダリング。
- [templates/diagram.html.j2](templates/diagram.html.j2): Jinja2 テンプレート。
  単一 HTML にインライン CSS。セクション構成は:
  - `01 今日の TOP ニュース` — 1 位が大きなゴールドカード、2〜5 位が 2x2 グリッド
    （縦スペースの ~45%）
  - `02 今日のトレンド` — ダークボックスのトレンド要約 + トピックチップ
    （NEW/RISING/SUSTAINED などのステータスバッジ色分け）
  - `03 カテゴリ分布` — 3 列グリッドで件数バッジ + 短い要約
  - `04 X で話題` — 3 列の小カード

### 変更

- [notifier.py](notifier.py): `multipart/form-data` でファイル添付対応
  (`_send_payload_with_file`)。`notify(..., diagram_png=...)` で PNG を受け取り、
  先頭メッセージとして Embed + 画像添付で送信。
- [main.py](main.py): Step 2.5 として図解生成を追加。`docs/diagrams/YYYY-MM-DD-slot.html`
  にも保存（将来の参照用）。
- [dashboard.py](dashboard.py): ダッシュボード TOP に「🖼️ 図解版アーカイブ」カードを
  追加（`docs/diagrams/*.html` 一覧）。
- [requirements.txt](requirements.txt): `jinja2`, `playwright` 追加。
- [.github/workflows/collect.yml](.github/workflows/collect.yml):
  - `fonts-noto-cjk`, `fonts-noto-cjk-extra`, `fonts-noto-color-emoji` を apt でインストール
  - `python -m playwright install --with-deps chromium` ステップを追加

### デザイン上の判断

- **配信順序**: 図解 PNG を**先頭メッセージ**として送る（Discord 上で一番上に
  表示され、目を引く）。以降は従来通りのヘッダー → X → TOP10 → カテゴリ別 →
  統計の順。
- **TOP ニュースを主役**: 縦スペースの約 45% を TOP ニュースセクションに割り当て、
  1 位を特大カードで視線を集める。残り 55% をトレンド・カテゴリ・X の補助
  セクションで分ける。
- **フル HTML 版リンクは配信に含めない**: リポジトリが Private で GitHub Pages
  は公開できないため（GitHub 無料プランの制約）。PNG だけでも Discord で
  クリック → 拡大表示で読めるので実害少なめ。HTML は `docs/diagrams/` に保存
  しているので、著者は GitHub 上で `blob/main/docs/diagrams/*.html` から
  直接確認可能。

### 既知の課題 / 将来の改善候補

- フル HTML 版を公開したい場合は、リポジトリを Public 化するか、Surge.sh 等
  へ別途デプロイする方針に変更する。
- 図解テンプレートは固定レイアウト。日ごとのニュース量や X トピックの有無で
  セクションの空きが目立つ日があるかもしれない。運用して違和感があれば
  動的レイアウト（セクション非表示化など）を検討。
- 文字量が多い日は TOP カード内の summary が 4〜5 行になり情報密度が高くなる。
  `summary` のクリップ閾値（現状 180 字）を調整する余地あり。

### 実行・テスト

- 手動配信: `gh workflow run collect.yml --repo k-hira-shine/ai-news-collector`
- ローカルで図解だけ生成:
  ```python
  from diagram import DiagramBuilder
  import json
  with open('data/analysis/2026-04-20_morning.json') as f:
      a = json.load(f)
  html, png = DiagramBuilder().build(a, slot='morning', date='2026-04-20')
  open('/tmp/d.html','w').write(html); open('/tmp/d.png','wb').write(png)
  ```

### 関連プラン

- `.cursor/plans/ai-news_diagram_delivery_dc9dfeac.plan.md`

### コミット

- `bfd7041` feat: add diagram delivery for daily AI news
- `c75faab` fix: Japanese font rendering in CI-generated diagrams
