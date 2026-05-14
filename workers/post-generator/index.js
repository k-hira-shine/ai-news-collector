export default {
  async fetch(request, env) {
    // CORS headers
    const corsHeaders = {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'POST, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type',
    };

    if (request.method === 'OPTIONS') {
      return new Response(null, { headers: corsHeaders });
    }

    if (request.method !== 'POST') {
      return new Response('Method not allowed', { status: 405, headers: corsHeaders });
    }

    try {
      const body = await request.json();
      const { template_id, template_name, prompt_hint, posts } = body;

      if (!env.GEMINI_API_KEY) {
        return new Response(JSON.stringify({ error: 'GEMINI_API_KEY not set' }), {
          status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' }
        });
      }

      // 元ポストのテキストを構築
      let postsText = '';
      for (const p of posts) {
        const insights = (p.key_insights || []).map(i => `  - ${i}`).join('\n');
        postsText += `
[ID: ${p.id}]
著者: @${p.author_display || p.author} (フォロワー ${(p.author_followers || 0).toLocaleString()}人)
要約: ${p.summary || ''}
テーマ: ${p.mind_theme || ''}
key_insights:
${insights || '  (なし)'}
本文（抜粋）:
${(p.content || '').slice(0, 400)}
---`;
      }

      const prompt = `${prompt_hint}

## 条件
- 日本語で書くこと
- 1投稿あたり140字以内
- 5件の投稿文を生成すること
- 各投稿には元ポストのID（[ID: ...]の値）を必ず対応させること
- コピーしてそのままXに投稿できる形にすること

## 元となるSNS成功者ポスト一覧
${postsText}`;

      const schema = {
        type: 'object',
        properties: {
          generated: {
            type: 'array',
            items: {
              type: 'object',
              properties: {
                source_post_id: { type: 'string' },
                text: { type: 'string' },
              },
              required: ['source_post_id', 'text'],
            },
          },
        },
        required: ['generated'],
      };

      const geminiRes = await fetch(
        `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=${env.GEMINI_API_KEY}`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            contents: [{ parts: [{ text: prompt }] }],
            generationConfig: {
              responseMimeType: 'application/json',
              responseSchema: schema,
            },
          }),
        }
      );

      if (!geminiRes.ok) {
        const errText = await geminiRes.text();
        return new Response(JSON.stringify({ error: `Gemini error: ${errText}` }), {
          status: 502, headers: { ...corsHeaders, 'Content-Type': 'application/json' }
        });
      }

      const geminiData = await geminiRes.json();
      const text = geminiData?.candidates?.[0]?.content?.parts?.[0]?.text || '{}';
      const result = JSON.parse(text);

      // source_post_idから元ポスト情報を付与
      const idToPost = Object.fromEntries(posts.map(p => [p.id, p]));
      const enriched = (result.generated || []).map(g => {
        const src = idToPost[g.source_post_id] || {};
        return {
          template_id,
          template_name,
          text: g.text,
          char_count: g.text.length,
          source_post_id: g.source_post_id,
          source_url: src.url || '',
          source_author: src.author_display || src.author || '',
          source_summary: src.summary || '',
        };
      });

      return new Response(JSON.stringify({ generated: enriched }), {
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      });

    } catch (e) {
      return new Response(JSON.stringify({ error: e.message }), {
        status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      });
    }
  }
};
