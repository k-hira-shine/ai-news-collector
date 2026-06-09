"""全 docs/*.html のナビゲーションを site_nav.py の最新定義へ一括同期する。

各ページはビルド時にナビを焼き込むため、ページを追加しても再生成されない
ページは古いナビのままになる。このスクリプトは既存の `<nav class="topnav">`
ブロックを最新のナビへ置き換え、どのページからでも全リンクが見えるようにする。
ビルド系ワークフローのデプロイ直前に必ず実行すること。
"""

import re
from pathlib import Path

from site_nav import render_nav

BASE = Path(__file__).parent
DOCS = BASE / "docs"

NAV_RE = re.compile(r'<nav class="topnav">.*?</nav>', re.DOTALL)


def sync() -> int:
    updated = 0
    for path in sorted(DOCS.glob("*.html")):
        html = path.read_text(encoding="utf-8")
        if not NAV_RE.search(html):
            continue
        new_nav = render_nav(path.name)
        new_html = NAV_RE.sub(lambda _m: new_nav, html, count=1)
        if new_html != html:
            path.write_text(new_html, encoding="utf-8")
            updated += 1
            print(f"updated nav: {path.name}")
    print(f"sync_nav: {updated} file(s) updated")
    return updated


if __name__ == "__main__":
    sync()
