# buzz-dispatch Worker

buzz.html の「ハンドル入力→収集起動」ボタンの中継サーバー。
**GitHub PAT をブラウザに出さない**ための仕組み（旧設計は公開ページにPATを埋め込んでいた＝事故）。

ブラウザは「ハンドル名」だけをこのWorkerに送り、WorkerがsecretのPATで
`buzz-collect.yml` の workflow_dispatch を叩く。

## デプロイ手順（初回・ユーザー操作が必要）

前提: `wrangler`（Cloudflareのデプロイツール）。既存の `workers/post-generator` が
動いているので、同じCloudflareアカウントにそのままデプロイできる。

```bash
cd workers/buzz-dispatch

# 1) 新しいPATを発行（GitHub → Settings → Developer settings → PAT）
#    最小権限: fine-grained で対象リポジトリ k-hira-shine/ai-news-collector の
#    「Actions: Read and write」のみ（または classic なら workflow スコープのみ）。
#    ※ 旧 ghp_mLJz… は revoke 済み。使い回さず必ず新規発行する。

# 2) PATを金庫(secret)に入れる（コードにもページにも書かない）
wrangler secret put GH_PAT
#   → プロンプトに新PATを貼り付け

# 3) デプロイ
wrangler deploy
#   → https://buzz-dispatch.<account>.workers.dev が払い出される
```

## URL整合の確認

`build_buzz.py` 内の `BUZZ_DISPATCH_URL` は
`https://buzz-dispatch.imokonoai.workers.dev` を指している
（既存 post-generator が `*.imokonoai.workers.dev` 配下のため同パターンを想定）。

デプロイ後の実URLがこれと異なる場合は `build_buzz.py` の `dispatch_js` を実URLに直して
`python build_buzz.py` で再ビルドする。

## 動作確認

1. buzz.html を開き、ハンドルを入れて「収集起動」→ `✅ …収集を開始しました` が出るか
2. ページのソースに `ghp_` / PAT が**無い**ことを確認（View Source で検索）
3. GitHub Actions に `Buzz Ranking Collector` の手動起動が現れるか

## 補足

- このWorkerは認証なし（CORS *）＝post-generatorと同じ流儀。誰でも収集を起動できる点は
  旧設計（公開PAT）と実質同等だが、**PATが漏れない**点が本質的な改善。
  乱用が気になるなら将来 Origin 制限や簡易トークンを足せる（ハンドル検証は実装済み）。
- 別トークン `ai-news-collector`（repoのみ・無期限・用途不明）が残っていれば、
  未使用を確認のうえ revoke 推奨（メモ gh-pat-public-exposure）。
