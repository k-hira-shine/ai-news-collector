# インシデント表示: CSS がページ本文に漏れた（2026-06-04）

## 症状

- GitHub Pages の **Home 最下部**（フッター付近）に `.incident-mount-wrap { ... }` などの **CSS ソースがそのまま表示** されていた
- 障害カード自体は動いていたが、見た目が壊れて「きたない」状態

## 原因（なぜそうなったか）

1. **障害表示機能追加**（commit `f9488c6`）で `incident_status.py` に `INCIDENT_CSS`（スタイル定義のみ）と `INCIDENT_BODY_HTML`（マウント div + JS）を分けて定義した
2. **`build_home.py` / `dashboard.py` の組み込みミス**
   - 当初 `STATUS_BANNER_HTML`（= `INCIDENT_CSS` + `INCIDENT_BODY_HTML` を `<style>` で包んだ塊）を body 末尾に置く想定だった
   - rebase / 手動マージの過程で **`INCIDENT_CSS` が `<style>` タグなしで `INCIDENT_BODY_HTML` と連結**され、さらに **フッター直前の body 末尾** に出力された
3. ブラウザは `<style>` の外にある `.incident-mount-wrap { ... }` を **スタイルではなくプレーンテキスト** として描画する → 画面下部に CSS が丸ごと見える

## 影響範囲

- `docs/home.html`, `docs/index.html` が生成時に汚染
- `sync_status_scripts_in_docs()` で追記した他ページ（buzz, money 等）にも **同パターンの漏れテキスト** が残っていた（12 ファイル）

## 修正内容

| 対策 | 内容 |
|------|------|
| 定数の使い分け | `build_home.py` / `dashboard.py`: `<head>` 内既存 `<style>` に `INCIDENT_CSS`、ナビ直後に `INCIDENT_BODY_HTML` のみ |
| 一括修復 | `repair_leaked_incident_css_in_docs()` で漏れパターンを削除 |
| 再発検知 | `find_leaked_incident_css_files()`（全 `<style>` を除いた本文に `.incident-mount-wrap` があるか）+ `scripts/check_incident_css_leak.py` |
| 同期時 | `sync_status_scripts_in_docs()` 冒頭で repair を実行 |

## 再発防止チェックリスト（エージェント・人間共通）

HTML を `docs/` に書き出す・commit する前に:

1. **`INCIDENT_CSS` を body / footer の後に連結していないか**
2. **`home.html` / `index.html` を開き、フッター下に `.incident-` で始まる生テキストがないか**
3. コマンド: `python3 scripts/check_incident_css_leak.py` が **exit 0** であること

### 正しい埋め込みパターン

```python
# build_home.py / dashboard.py（テンプレート生成）
# <head> 内の </style> の直前:
{INCIDENT_CSS}

# <body> 内、ナビ直後:
{INCIDENT_BODY_HTML}
```

```python
# 静的 HTML に後から足すだけ（sync_status_scripts）
# </body> 直前 — INCIDENT_CLIENT_HTML のみ（内部で <style> 付き）
content.replace("</body>", INCIDENT_CLIENT_HTML + "\n</body>", 1)
```

### してはいけないこと

- `INCIDENT_CSS` を f-string で footer や `</body>` の直前にそのまま入れる
- `STATUS_BANNER_HTML` と `INCIDENT_CSS` を二重に足す
- 漏れ修復なしで `docs/*.html` だけ手編集して commit する

## 関連コミット

- 導入: `f9488c6` feat: 収集障害の自動検知と全ページへの状況・原因・影響表示
- 修正: （本 fix commit）`fix: 障害表示 CSS の本文漏れを修正`

## 参照コード

- `incident_status.py`: `INCIDENT_CSS`, `INCIDENT_BODY_HTML`, `INCIDENT_CLIENT_HTML`, `_LEAKED_CSS_RE`
- `build_home.py`, `dashboard.py`: head / body への分割挿入
