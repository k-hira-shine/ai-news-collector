// buzz.html の「ハンドル入力→収集起動」ボタンの中継サーバー（Cloudflare Worker）。
//
// 目的: GitHub PAT をブラウザに出さないこと。
//   旧設計は公開ページ docs/buzz.html に PAT を分割埋め込みしていた（誰でも復元可能＝事故）。
//   本Workerが PAT を secret(env.GH_PAT) に隠し持ち、ブラウザはハンドル名だけ送る。
//
// デプロイ: workers/buzz-dispatch/ で
//   wrangler secret put GH_PAT     # 最小権限の新PAT（workflowスコープ）を金庫に入れる
//   wrangler deploy                # → https://buzz-dispatch.<account>.workers.dev
export default {
  async fetch(request, env) {
    const corsHeaders = {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'POST, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type',
    };
    const json = (obj, status = 200) => new Response(JSON.stringify(obj), {
      status, headers: { ...corsHeaders, 'Content-Type': 'application/json' },
    });

    if (request.method === 'OPTIONS') {
      return new Response(null, { headers: corsHeaders });
    }
    if (request.method !== 'POST') {
      return new Response('Method not allowed', { status: 405, headers: corsHeaders });
    }

    try {
      if (!env.GH_PAT) {
        return json({ error: 'GH_PAT not set（wrangler secret put GH_PAT が未実施）' }, 500);
      }

      const body = await request.json().catch(() => ({}));

      // ハンドル抽出（@除去・URL形式 x.com/handle からも拾う）
      let handle = String(body.account || '').trim().replace(/^@/, '');
      const m = handle.match(/(?:x\.com|twitter\.com)\/([A-Za-z0-9_]+)/);
      if (m) handle = m[1];
      // X（Twitter）のハンドル規則＝英数字とアンダースコアのみ・1〜15字。
      // サーバー側で検証＝任意の値で他ワークフローを叩かれるのを防ぐ。
      if (!/^[A-Za-z0-9_]{1,15}$/.test(handle)) {
        return json({ error: 'invalid handle' }, 400);
      }

      // days は 1〜90 にclamp（既定30）
      let days = parseInt(body.days, 10);
      if (!Number.isFinite(days)) days = 30;
      days = String(Math.min(90, Math.max(1, days)));

      const ghRes = await fetch(
        'https://api.github.com/repos/k-hira-shine/ai-news-collector/actions/workflows/buzz-collect.yml/dispatches',
        {
          method: 'POST',
          headers: {
            'Authorization': 'Bearer ' + env.GH_PAT,
            'Accept': 'application/vnd.github+json',
            'Content-Type': 'application/json',
            'User-Agent': 'buzz-dispatch-worker',  // GitHub API は User-Agent 必須
          },
          body: JSON.stringify({ ref: 'main', inputs: { account: handle, days } }),
        }
      );

      // workflow_dispatch 成功時は 204 No Content
      if (ghRes.status === 204) {
        return json({ ok: true, account: handle });
      }
      const text = await ghRes.text();
      return json({ error: `GitHub ${ghRes.status}: ${text}` }, 502);
    } catch (e) {
      return json({ error: e.message }, 500);
    }
  },
};
