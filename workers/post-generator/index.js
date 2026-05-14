export default {
  async fetch(request, env) {
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
      // post: 単一ポストオブジェクト, templates: テンプレート配列
      const { post, templates } = body;

      if (!env.GEMINI_API_KEY) {
        return new Response(JSON.stringify({ error: 'GEMINI_API_KEY not set' }), {
          status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' }
        });
      }

      if (!post || !templates || !templates.length) {
        return new Response(JSON.stringify({ error: 'post and templates are required' }), {
          status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' }
        });
      }

      // ポスト情報のテキスト化
      const insights = (post.key_insights || []).map(i => `  - ${i}`).join('\n');
      const postText = `
著者: @${post.author_display || post.author} (フォロワー ${(post.author_followers || 0).toLocaleString()}人)
テーマ: ${post.mind_theme || ''}
要約: ${post.summary || ''}
key_insights:
${insights || '  (なし)'}
本文:
${(post.content || '').slice(0, 800)}
`.trim();

      // 6テンプレート分のプロンプトを1リクエストにまとめる
      const templateList = templates.map((t, i) =>
        `### テンプレート${i + 1}: ${t.name}\n${t.prompt_hint}`
      ).join('\n\n');

      const prompt = `以下のX（旧Twitter）投稿の内容を元に、6種類のテンプレートで日本語の投稿文を1つずつ作成してください。

## 元ポスト情報
${postText}

## テンプレート定義
${templateList}

## 共通ルール
- 各テンプレートにつき1件の投稿文を作成すること
- 各投稿は140字以内
- 日本語で書くこと
- コピーしてそのままXに投稿できる形にすること
- 元ポストのエッセンス・key_insightsを活かすこと
- 改行が必要な箇所（リスト・ステップ・対比など）は必ず改行文字（\\n）を使うこと。「↓」「・」の前後は改行を入れること
- 1行に複数の要素を詰め込まないこと`;

      const schema = {
        type: 'object',
        properties: {
          results: {
            type: 'array',
            items: {
              type: 'object',
              properties: {
                template_id: { type: 'string' },
                template_name: { type: 'string' },
                text: { type: 'string' },
              },
              required: ['template_id', 'template_name', 'text'],
            },
          },
        },
        required: ['results'],
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
      const rawText = geminiData?.candidates?.[0]?.content?.parts?.[0]?.text || '{}';
      const result = JSON.parse(rawText);

      // template_idが返ってこない場合はtemplates配列のindexで補完
      const enriched = (result.results || []).map((r, i) => {
        const tmpl = templates[i] || {};
        return {
          template_id: r.template_id || tmpl.id || `t${i + 1}`,
          template_name: r.template_name || tmpl.name || '',
          text: (r.text || '').trim(),
          char_count: (r.text || '').trim().length,
          source_post_id: post.id || '',
          source_url: post.url || '',
          source_author: post.author_display || post.author || '',
          source_summary: post.summary || '',
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
