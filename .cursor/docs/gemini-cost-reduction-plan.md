# Gemini API コスト削減計画

作成日: 2026-06-10
状態: 計画段階（施策は未実装。ユーザー承認後に着手）

## 0. 最重要: まず実費とプランを確認する

Gemini API には無料ティアがあり、本プロジェクトの Pro 呼び出しは1日約24回・Flash は数十回と少ないため、**現状の実費が $0 の可能性がある**。施策の前に必ず確認する。

- 確認先: [Google AI Studio の API キー画面](https://aistudio.google.com/) と Google Cloud 請求コンソール
- 確認内容: 使用中の `GEMINI_API_KEY` が無料ティアか、課金プロジェクト紐付きか。直近30日の Gemini API 請求額。
- **無料ティアならコスト削減は不要**（レート制限対策のみ検討）。有料なら本計画を進める。

## 1. 公式料金（2026-06 時点、ai.google.dev/gemini-api/docs/pricing で確認済み）

| モデル | 入力 /1M tokens | 出力 /1M tokens（thinking 込み） |
|---|---|---|
| gemini-2.5-pro | $1.25（≤200k） | $10.00 |
| gemini-2.5-flash | $0.30 | $2.50 |
| gemini-2.5-flash-lite | $0.10 | $0.40 |

Pro→Flash で入力 1/4・出力 1/4。出力は入力の8倍単価なので **出力（thinking 含む）の抑制が効く**。

## 2. 現状の利用マップ（2026-06-10 棚卸し）

| 呼び出し | モデル | 1日の回数目安 | 入力規模 | 備考 |
|---|---|---|---|---|
| analyzer.py Stage1（ニュース1次フィルタ） | **Pro** | 2 | 全収集件数×350字を1プロンプト | 消費1位候補 |
| analyzer.py Stage2（詳細分析） | **Pro** | 2 | 100件×500字+過去5回分 | 消費1位候補 |
| analyzer.py Stage3（戦略） | **Pro** | 2 | 要約中心で小さい | |
| sns_analyzer.py | **Pro** | 最大10（50件/バッチ×500件） | 800字/件 | 消費2位候補 |
| money_analyzer.py | **Pro** | 2〜4 | 500字/件 | |
| post_generator.py | **Pro（意図しない疑い）** | 6 | 20件サンプル+長プロンプト | コードのデフォルトはFlashだが config の stage1_filter(=Pro) を参照 |
| tools_analyzer.py | Flash | 最大14 | 600字/件 | backfill 200件/run 含む |
| gemini_collector.py | Flash | 約8 | 700字/件 | |
| collector.py / dashboard.py 翻訳 | Flash | 4〜6 | タイトル中心で小 | dashboard 側は collector 翻訳の取りこぼし時のみ（軽微な二重化） |
| build_gemini_omni.py 翻訳 | Flash | キャッシュ済みなら0 | 3500字/件 | thinking=0 設定済み |

- `usage_metadata`（トークン数）は**どこにも記録していない** → 実測値ゼロの状態。
- `max_output_tokens` は全箇所未設定。
- Pro→Flash フォールバックは analyzer.py のみ。

## 3. 施策（優先順）

### 施策G1: トークン計測の追加（前提インフラ・品質影響なし）
- 各 `generate_content` 呼び出し後に `response.usage_metadata` を `data/logs/*.jsonl` に記録。
- check_cost.py 同様の日次集計を作り、モデル別単価で推定額を出す。
- これがないと以降の施策の効果測定ができない。

### 施策G2: post_generator.py の Pro 参照を Flash に修正（バグ修正に近い）
- config 参照キーを `stage1_filter` から専用キーまたは明示 Flash へ。
- 期待削減: 当該呼び出しの約76%。品質リスク小（テンプレ穴埋め生成のため）。

### 施策G3: 1次フィルタ系（stage1 / money / sns）を Pro→Flash
- 対象: analyzer.py Stage1、money_analyzer.py、sns_analyzer.py（いずれも「関連あるか」の分類タスク）。
- config キーを `stage1_filter`（分類用=Flash）と `stage2_analysis`（深い分析=Pro 維持）に分離。
- 期待削減: 当該呼び出しの約76%。
- **検証必須**: 同日データで Pro/Flash の採用判定一致率を比較してから切替（過去にProへ寄せた経緯がないか pitfalls 確認済み・記録なし）。

### 施策G4: max_output_tokens の設定
- 出力単価は入力の8倍。各呼び出しに上限を設定し、暴走出力・冗長 thinking を防ぐ。
- 期待削減: 小〜中（保険の意味が大きい）。

### 施策G5: 分類専任を Flash-Lite 化（G3の発展形）
- tools_analyzer / gemini_collector の分類を flash-lite（$0.10/$0.40）へ。
- G1 の実測後、分類精度を確認してから判断。

### 施策G6: 軽微な無駄の解消
- dashboard.py の HN 再翻訳: collector.py 側で `title_ja` を確実に付与し二重呼び出しを防ぐ。
- tools_analyzer の backfill（200件/run）: 全件処理が完了したら `enabled: false` にする。

## 4. 測定と合格条件

- G1 実装後 3日間の実測を取り、モデル別・呼び出し別の日次推定額を確定。
- 施策ごとに before/after をログで比較。
- 有料ティアの場合の合格条件: Pro 利用を Stage2/Stage3 のみに限定し、推定月額を半減以下。
- 無料ティアの場合: 施策は G2（誤設定修正）と G6 のみ実施し、他は見送り。

## 5. 注意（pitfalls 連携）

- Apify 削減策(6/10実装)の測定期間中。Gemini 施策は Apify 計測を汚さないが、collect.yml 等を触る際はコミットを分ける。
- モデル変更は分析品質に直結するため、必ず検証→ユーザー承認→切替の順。
