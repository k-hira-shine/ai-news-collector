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

## Legacy スクリプト

AIニュース専用運用では `main.py` と `build_hn.py` 以外の収集系スクリプトは定期実行しない。
Gemini 個別調査や Buzz 系のスクリプトは、必要なときだけ手動実行する旧機能として残す。
課金を伴う Legacy workflow は既定 no-op。実行には workflow_dispatch の `allow_costs=true`
または `ALLOW_LEGACY_COSTS=true ./run_workflow.sh ...` が必要。

## 緊急停止・再開

Secrets やコードを消さずに、日次運用ワークフローだけをまとめて止める。

```bash
# 状態確認
python3 scripts/ops_workflows.py status

# 自動実行を一時停止（デフォルトはAIニュース本線と日次チェックだけ）
python3 scripts/ops_workflows.py pause

# いま実行中のrunも止めてから一時停止
python3 scripts/ops_workflows.py pause --cancel-running

# 再開
python3 scripts/ops_workflows.py resume
```

対象は `collect.yml`, `daily-ops-check.yml`。検証用・単発用 workflow まで含めたい場合だけ
`--all` を付ける。

一覧と全体地図: `.cursor/docs/project-layout.md`
