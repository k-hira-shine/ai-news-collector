# scripts/

**CI が定期実行で叩くエントリは原則リポジトリルート**（`main.py`, `build_*.py`, `run_*.py`）。  
ここは **手動・診断・バックフィル・実験** 用。

## 新規スクリプトを置くとき

| 条件 | 置き場 |
|------|--------|
| `.github/workflows/*.yml` から毎回 `python …` される | **ルート**（または workflow を `scripts/` 向けに変更してから） |
| 障害調査・一度きり・ローカル確認 | **`scripts/`**（このフォルダ） |
| docs を commit する前の検査 | `check_incident_css_leak.py` を実行 |

```bash
# リポジトリルートで
python3 scripts/check_incident_css_leak.py
python3 scripts/probe_x_upstream.py
```

## Gemini活用法の過去バズ調査

定期実行には組み込まない。アーカイブを増やしたいときに、期間と検索群を決めて
一気に取得する単発調査として扱う。

```bash
# 表示ページだけ再生成
python3 scripts/gemini_buzz_research.py --build-only

# 一般語検索
python3 scripts/gemini_buzz_research.py \
  --mode discovery \
  --query-profile broad \
  --start 2024-06-10 \
  --end 2026-06-10 \
  --max-items-per-query 25 \
  --max-charge-usd 0.05

# 機能名検索は query-profile を features または feature-expansion にする
```

結果は `data/gemini_buzz/` にスナップショットとして残り、
`docs/gemini-buzz.html` にいいね順で表示される。
次回の主課題は、品質を維持しながら検索語・期間分割・取得上限を広げ、
55件からさらに件数を増やすこと。

## CI から呼ばれる例外

- `collect_gemini_omni_overseas.py` … `collect.yml` の朝 run のみ（歴史的理由で `scripts/` に配置）

一覧と全体地図: `.cursor/docs/project-layout.md`
