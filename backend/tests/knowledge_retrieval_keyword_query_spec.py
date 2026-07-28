"""Unicode lexical query normalization must stay bounded and deterministic."""

from backend.app.services.knowledge_retrieval.keyword_query import (
    cjk_prefix_tsquery,
)


def test_cjk_prefix_tsquery_builds_overlapping_safe_bigrams() -> None:
    assert cjk_prefix_tsquery("瑜伽包含呼吸練習嗎？") == (
        "瑜伽:* | 伽包:* | 包含:* | 含呼:* | 呼吸:* | "
        "吸練:* | 練習:* | 習嗎:*"
    )


def test_cjk_prefix_tsquery_ignores_non_cjk_and_deduplicates() -> None:
    assert cjk_prefix_tsquery("HRV 瑜伽 / 瑜伽 alert('unsafe')") == "瑜伽:*"


def test_cjk_prefix_tsquery_is_bounded_to_sixty_four_terms() -> None:
    query = "".join(chr(0x4E00 + offset) for offset in range(100))

    terms = cjk_prefix_tsquery(query).split(" | ")

    assert len(terms) == 64
    assert terms[0] == "一丁:*"
    assert terms[-1] == "丿乀:*"
