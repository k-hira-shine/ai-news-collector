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

## CI から呼ばれる例外

- `collect_gemini_omni_overseas.py` … `collect.yml` の朝 run のみ（歴史的理由で `scripts/` に配置）

一覧と全体地図: `.cursor/docs/project-layout.md`
