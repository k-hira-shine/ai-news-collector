"""全ページ共通ナビゲーション"""

NAV_LINKS: list[tuple[str, str]] = [
    ("index.html",          "📰 ニュース"),
]

NAV_CSS = """
.topnav { position: fixed; top: 0; left: 0; right: 0; z-index: 1000; background: #0a0f1eee; backdrop-filter: blur(8px); border-bottom: 1px solid #2d3748; display: flex; gap: 0.4rem; justify-content: center; flex-wrap: wrap; padding: 6px 12px; }
.topnav a { display: inline-block; padding: 4px 12px; background: #1a2236; border-radius: 6px; color: #94a3b8; text-decoration: none; font-size: 0.82rem; white-space: nowrap; }
.topnav a:hover { color: #38bdf8; background: rgba(56,189,248,0.1); }
.topnav a.active { background: #0284c7; color: #fff; }
@media (max-width: 640px) {
  .topnav { gap: 4px; padding: 4px 8px; }
  .topnav a { font-size: 0.75rem; padding: 3px 8px; }
}
"""


def render_nav(active_page: str) -> str:
    """active_page: 現在ページの href（例: 'index.html'）"""
    lines = ["<nav class=\"topnav\">"]
    for href, label in NAV_LINKS:
        cls = ' class="active"' if href == active_page else ""
        lines.append(f'  <a href="{href}"{cls}>{label}</a>')
    lines.append("</nav>")
    return "\n".join(lines)
