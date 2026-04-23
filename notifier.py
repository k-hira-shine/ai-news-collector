"""Discord Webhook で分析結果を Embed 形式で配信"""

import json
import logging
import os
import time

import requests

from utils import retry, today_str

logger = logging.getLogger("ai-news.notifier")

COLORS = {
    "header": 0x5865F2,  # blurple
    "top": 0xED4245,  # red
    "モデル/ツール": 0x57F287,  # green
    "企業動向": 0xFEE75C,  # yellow
    "規制/政策": 0xEB459E,  # fuchsia
    "研究論文": 0x5865F2,  # blurple
    "資金調達": 0xF47B67,  # coral
    "ユースケース": 0x3498DB,  # blue
    "action": 0xE67E22,  # orange
    "stats": 0x95A5A6,  # grey
    "x_trends": 0x1DA1F2,  # twitter blue
}

SLOT_LABELS = {"morning": "朝便", "evening": "夕便"}


class DiscordNotifier:
    def __init__(
        self,
        webhook_url: str | None = None,
        delay: float = 0.5,
        ranking_top: int = 10,
        max_items_per_category: int = 5,
    ):
        self.webhook_url = webhook_url or os.environ.get("DISCORD_WEBHOOK_URL", "")
        self.delay = delay
        self.ranking_top = ranking_top
        self.max_items_per_category = max_items_per_category

    # ── public ────────────────────────────────────────────────────────

    def notify(
        self,
        analysis: dict,
        stats: dict,
        diagram_png: bytes | None = None,
    ) -> bool:
        """分析結果を Discord に配信 (複数メッセージ分割)

        diagram_png が指定された場合は先頭に図解メッセージを送信する。
        """
        if not self.webhook_url:
            logger.warning("DISCORD_WEBHOOK_URL not set — skipping notification")
            return False

        if not analysis.get("top_articles"):
            return self._send_simple("⚠️ 本日の収集データがありません。")

        results: list[tuple[str, bool]] = []

        if diagram_png:
            diagram_filename = self._diagram_filename(analysis)
            diagram_embed = self._build_diagram_embed(analysis, diagram_filename)
            ok = self._send_payload_with_file(
                {"embeds": [diagram_embed]},
                filename=diagram_filename,
                file_bytes=diagram_png,
                content_type="image/png",
            )
            results.append(("diagram_png", ok))
            time.sleep(self.delay)

        messages = self._build_messages(analysis, stats)
        for i, payload in enumerate(messages):
            if i > 0:
                time.sleep(self.delay)
            results.append((f"msg{i}", self._send_payload(payload)))

        failed = [label for label, ok in results if not ok]
        if failed:
            logger.error(
                "Discord notify partial failure: %d/%d dropped (%s)",
                len(failed), len(results), ",".join(failed),
            )
        return not failed

    def send_status(self, message: str) -> bool:
        """ステータス通知 (プレーンテキスト)"""
        if not self.webhook_url:
            return False
        return self._send_simple(message)

    def send_alerts(self, anomalies: list[dict]) -> bool:
        """健全性アラートのみを Embed で送信（0件実行時など notify() を通らない経路用）"""
        if not self.webhook_url or not anomalies:
            return False
        from alerts import build_alert_embed
        embed = build_alert_embed(anomalies)
        if not embed:
            return False
        return self._send_payload({"embeds": [embed]})

    # ── メッセージ構築 ─────────────────────────────────────────────────

    @staticmethod
    def _diagram_filename(analysis: dict) -> str:
        date = (analysis.get("run_time", "") or "")[:10] or today_str()
        slot = analysis.get("slot", "morning")
        return f"ai-news-{date}-{slot}.png"

    def _build_diagram_embed(self, analysis: dict, filename: str) -> dict:
        slot = SLOT_LABELS.get(analysis.get("slot", ""), "")
        date = today_str()
        return {
            "title": f"🤖 AI News 図解版 {date} {slot}",
            "description": "**今日の AI ニュースを 1 枚にまとめました**",
            "color": COLORS["header"],
            "image": {"url": f"attachment://{filename}"},
        }

    def _build_messages(self, analysis: dict, stats: dict) -> list[dict]:
        """6000文字制限を考慮して複数メッセージに分割"""
        slot = SLOT_LABELS.get(analysis.get("slot", ""), "")
        date_label = today_str()

        # Message 1: ヘッダー + トレンド + 前日比
        embed_header = self._build_header_embed(analysis, date_label, slot)

        # Message 2: TOP ランキング
        embed_top = self._build_top_embed(analysis)

        # Message 3+: カテゴリ別
        category_embeds = self._build_category_embeds(analysis)

        # Message: X トレンド
        x_trends_embeds = self._build_x_trends_embeds(analysis)

        # Message N: アクションアイテム + 統計
        embed_action = self._build_action_embed(analysis)
        embed_stats = self._build_stats_embed(stats)

        messages: list[dict] = []
        messages.append({"embeds": [embed_header]})

        if x_trends_embeds:
            messages.append({"embeds": x_trends_embeds[:10]})

        messages.append({"embeds": [embed_top]})

        chunk: list[dict] = []
        chunk_chars = 0
        for emb in category_embeds:
            emb_len = self._embed_char_count(emb)
            if chunk and (chunk_chars + emb_len > 5500 or len(chunk) >= 10):
                messages.append({"embeds": chunk})
                chunk = []
                chunk_chars = 0
            chunk.append(emb)
            chunk_chars += emb_len
        if chunk:
            messages.append({"embeds": chunk})

        footer_embeds = [embed_action]
        if embed_stats:
            footer_embeds.append(embed_stats)

        anomalies = stats.get("anomalies") or []
        if anomalies:
            from alerts import build_alert_embed
            alert_embed = build_alert_embed(anomalies)
            if alert_embed:
                footer_embeds.append(alert_embed)

        messages.append({"embeds": footer_embeds})

        return messages

    def _build_header_embed(self, analysis: dict, date: str, slot: str) -> dict:
        trend = analysis.get("trend_summary", "")
        evo = analysis.get("trend_evolution", {})

        desc_parts = [f"**📊 今日の注目トレンド**\n{trend}"]

        since_last = evo.get("since_last", "")
        if since_last:
            desc_parts.append(f"**🔄 前回からの変化**\n{since_last}")

        tracked = evo.get("tracked_topics", [])
        if tracked:
            status_icons = {
                "NEW": "⚡", "RISING": "📈", "SUSTAINED": "➡️",
                "FADING": "📉", "RESURFACED": "🔄",
            }
            topic_lines: list[str] = []
            for t in tracked:
                icon = status_icons.get(t.get("status", ""), "•")
                topic = t.get("topic", "")
                status = t.get("status", "")
                streak = t.get("streak_days", 0)
                streak_str = f" ({streak}日目)" if streak and streak > 1 else ""
                evolution = t.get("evolution", "")
                evo_str = f"\n　_{evolution}_" if evolution else ""
                topic_lines.append(f"{icon} **{status}** {topic}{streak_str}{evo_str}")
            desc_parts.append("**📈 トレンド推移**\n" + "\n".join(topic_lines))

        return {
            "title": f"🤖 AI News {date} {slot}",
            "description": "\n\n".join(desc_parts)[:4096],
            "color": COLORS["header"],
        }

    def _build_top_embed(self, analysis: dict) -> dict:
        articles = analysis.get("top_articles", [])[:self.ranking_top]
        medals = ("🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟")

        lines: list[str] = []
        for i, art in enumerate(articles):
            medal = medals[i] if i < len(medals) else f"{i + 1}."
            title = art.get("title", "")[:80]
            url = art.get("url", "")
            summary = art.get("summary", "")
            cat = art.get("category", "")
            src = art.get("source_label", "")

            link = f"[{title}]({url})" if url else title
            lines.append(f"{medal} {link}\n　→ {summary} [{cat}] [{src}]")

        return {
            "title": f"⭐ 重要ニュース TOP{len(articles)}",
            "description": "\n\n".join(lines)[:4096],
            "color": COLORS["top"],
        }

    def _build_category_embeds(self, analysis: dict) -> list[dict]:
        embeds: list[dict] = []
        for cat_sum in analysis.get("category_summaries", []):
            cat = cat_sum.get("category", "")
            summary = cat_sum.get("summary", "")
            count = cat_sum.get("count", 0)
            articles = cat_sum.get("key_articles", [])[:self.max_items_per_category]

            lines: list[str] = [summary]
            if articles:
                lines.append("")
                for a in articles:
                    t = a.get("title", "")[:60]
                    u = a.get("url", "")
                    link = f"[{t}]({u})" if u else t
                    sub = a.get("summary", "")
                    line = f"• {link}"
                    if sub:
                        line += f"\n　{sub}"
                    lines.append(line)

            count_str = f" ({count}件)" if count else ""
            embeds.append(
                {
                    "title": f"📁 {cat}{count_str}",
                    "description": "\n".join(lines)[:4096],
                    "color": COLORS.get(cat, 0x99AAB5),
                }
            )
        return embeds

    def _build_x_trends_embeds(self, analysis: dict) -> list[dict]:
        trends = analysis.get("x_trends", [])
        if not trends:
            return []

        buzz_icons = {"high": "🔥🔥🔥", "medium": "🔥🔥", "low": "🔥"}
        sentiment_icons = {
            "positive": "😊", "negative": "😟",
            "neutral": "😐", "mixed": "🤔",
        }

        lines: list[str] = []
        for tr in trends:
            topic = tr.get("topic", "")
            desc = tr.get("description", "")
            buzz = buzz_icons.get(tr.get("buzz_level", ""), "🔥")
            sent = sentiment_icons.get(tr.get("sentiment", ""), "")

            lines.append(f"**{buzz} {topic}** {sent}\n{desc}")

            for tw in tr.get("representative_tweets", [])[:2]:
                author = tw.get("author", "")
                text = tw.get("text", "")[:120]
                url = tw.get("url", "")
                likes = tw.get("likes", 0)
                rts = tw.get("retweets", 0)
                eng = f"❤️{likes} 🔁{rts}" if likes or rts else ""
                link = f"[@{author}]({url})" if url else f"@{author}"
                lines.append(f"　> {link}: {text}… {eng}")

        return [{
            "title": "🐦 X/Twitter で話題",
            "description": "\n\n".join(lines)[:4096],
            "color": COLORS["x_trends"],
        }]

    def _build_action_embed(self, analysis: dict) -> dict:
        items = analysis.get("action_items", [])
        lines = [f"• {a}" for a in items]
        return {
            "title": "💡 ビジネスへの示唆",
            "description": "\n".join(lines)[:4096] if lines else "なし",
            "color": COLORS["action"],
        }

    def _build_stats_embed(self, stats: dict) -> dict | None:
        if not stats:
            return None

        parts: list[str] = []
        if stats.get("total"):
            src_line = " / ".join(
                f"{k}: {v}"
                for k, v in [
                    ("X", stats.get("x_count", 0)),
                    ("RSS", stats.get("rss_count", 0)),
                    ("YouTube", stats.get("youtube_count", 0)),
                ]
            )
            parts.append(f"収集: {stats['total']}件 ({src_line})")
        if stats.get("official_count"):
            parts.append(f"公式ソース: {stats['official_count']}件")
        if stats.get("must_follow_count"):
            parts.append(f"必須アカウント: {stats['must_follow_count']}件")
        apify_runs = stats.get("apify_runs", 0)
        apify_cost = stats.get("apify_cost_usd", 0)
        if apify_runs or apify_cost:
            budget = stats.get("apify_monthly_budget_usd", 29.0)
            cycle_total = stats.get("apify_cycle_total_usd", 0)
            remaining = max(0, budget - cycle_total)
            cost_str = f"${apify_cost:.4f}" if apify_cost else "測定不可（反映ラグ）"
            apify_line = f"💰 Apify: {cost_str} ({apify_runs}回実行)"
            if cycle_total:
                apify_line += f" | 通算 ${cycle_total:.2f} / ${budget:.0f} (残り ${remaining:.2f})"
            parts.append(apify_line)
            threshold = stats.get("apify_warning_threshold", 0.8)
            if cycle_total and cycle_total >= budget * threshold:
                parts.append(f"⚠️ Apify 残高が {(1 - threshold) * 100:.0f}% を切りました！")
        if stats.get("elapsed_sec"):
            parts.append(f"処理時間: {stats['elapsed_sec']:.0f}秒")

        return {
            "title": "📈 収集統計",
            "description": "\n".join(parts)[:4096],
            "color": COLORS["stats"],
        }

    # ── Discord API 送信 ───────────────────────────────────────────────

    @retry(max_retries=3, base_delay=2)
    def _send_payload(self, payload: dict) -> bool:
        try:
            res = requests.post(self.webhook_url, json=payload, timeout=30)
        except (requests.ConnectionError, requests.Timeout) as e:
            logger.warning("Discord send network error: %s — retrying", e)
            raise
        if res.status_code in (200, 204):
            return True
        if res.status_code == 429:
            try:
                retry_after = res.json().get("retry_after", 1)
            except Exception:
                retry_after = 2
            logger.warning("Discord rate limited, waiting %.1fs", retry_after)
            time.sleep(retry_after)
            raise Exception(f"Discord rate limited ({retry_after}s)")
        if 500 <= res.status_code < 600:
            logger.warning("Discord %d — retrying: %s", res.status_code, res.text[:200])
            raise Exception(f"Discord server error {res.status_code}")
        logger.error("Discord send failed: %d %s", res.status_code, res.text[:300])
        return False

    def _send_simple(self, content: str) -> bool:
        return self._send_payload({"content": content})

    @retry(max_retries=3, base_delay=2)
    def _send_payload_with_file(
        self,
        payload: dict,
        filename: str,
        file_bytes: bytes,
        content_type: str = "application/octet-stream",
    ) -> bool:
        """multipart/form-data でファイル添付付きメッセージを送信"""
        files = {"files[0]": (filename, file_bytes, content_type)}
        data = {"payload_json": json.dumps(payload, ensure_ascii=False)}
        try:
            res = requests.post(self.webhook_url, data=data, files=files, timeout=60)
        except (requests.ConnectionError, requests.Timeout) as e:
            logger.warning("Discord file send network error: %s — retrying", e)
            raise
        if res.status_code in (200, 204):
            return True
        if res.status_code == 429:
            try:
                retry_after = res.json().get("retry_after", 1)
            except Exception:
                retry_after = 2
            logger.warning("Discord rate limited (file), waiting %.1fs", retry_after)
            time.sleep(retry_after)
            raise Exception(f"Discord rate limited ({retry_after}s)")
        if 500 <= res.status_code < 600:
            logger.warning("Discord file %d — retrying: %s", res.status_code, res.text[:200])
            raise Exception(f"Discord server error {res.status_code}")
        logger.error("Discord file send failed: %d %s", res.status_code, res.text[:300])
        return False

    @staticmethod
    def _embed_char_count(embed: dict) -> int:
        total = len(embed.get("title", ""))
        total += len(embed.get("description", ""))
        for f in embed.get("fields", []):
            total += len(f.get("name", "")) + len(f.get("value", ""))
        return total
