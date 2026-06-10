from analysis_quality import (
    filter_analysis_results,
    is_promotional_content,
    is_rights_violation_content,
    prefilter_analysis_items,
)


def _item(item_id: str, content: str, followers: int = 10_000) -> dict:
    return {
        "id": item_id,
        "content": content,
        "author_followers": followers,
    }


def test_rejects_promotional_and_rights_violation_content() -> None:
    assert is_promotional_content("20大特典を配布します。無料勉強会の予約はこちら")
    assert is_promotional_content("Sign up now for my free course. Limited spots.")
    assert is_rights_violation_content("日本の無断転載動画で月1000万円を稼ぐ")
    assert not is_rights_violation_content("無断転載は著作権違反なので絶対に避けるべき")


def test_prefilter_removes_low_followers_short_replies_and_unsafe_posts() -> None:
    items = [
        _item("good", "YouTube運営で得た具体的な改善手順を5項目に整理します。" * 3),
        _item("low", "具体的な長文ですがフォロワー基準未満です。" * 5, followers=999),
        _item("reply", "@someone 良ポスト"),
        _item("promo", "無料勉強会を開催。特典を配布します。"),
        _item("rights", "無断転載動画で稼ぐ方法を紹介します。"),
    ]

    assert [item["id"] for item in prefilter_analysis_items(items, 1000)] == ["good"]


def test_postfilter_collapses_near_duplicates() -> None:
    base = (
        "Instagram運用で月7桁を達成するまでに実施した手順を公開します。"
        "投稿設計、分析、改善を毎週繰り返し、半年間継続しました。"
    )
    items = [
        _item("first", base + " https://example.com/a"),
        _item("duplicate", "最後に。" + base + " https://example.com/b"),
        _item("different", "YouTube Shortsの視聴維持率を改善するための具体策を解説します。" * 3),
    ]

    assert [item["id"] for item in filter_analysis_results(items)] == ["first", "different"]


def test_postfilter_keeps_distinct_thread_sections() -> None:
    items = [
        _item("part1", "①供給者が少ないため、日本市場には参入余地がある。" * 5),
        _item("part2", "②競争者密度と視聴単価を比較し、市場を選定する。" * 5),
    ]

    assert len(filter_analysis_results(items)) == 2
