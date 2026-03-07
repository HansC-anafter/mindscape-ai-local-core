"""
Golden recall tests for Tool RAG V2 (BM25 + RRF).

Ensures that fuzzy intent queries correctly map to the expected capability tools,
preventing regression in tool discovery for the agent.
"""

import pytest
import pytest_asyncio

pytestmark = pytest.mark.asyncio


GOLDEN_QUERIES = [
    (
        "Can you check what time my next post is scheduled for?",
        "content_scheduler.cs_calendar_view",  # viewing schedule → calendar_view
    ),
    (
        "I need to push this picture to my Instagram feed.",
        "ig.ig_publish_post",
    ),
    (
        "Help me search for new followers or people who liked my competitor's posts.",
        "ig.ig_analyze_following",
    ),
    (
        "Let's create a new text post for tomorrow.",
        "content_scheduler.cs_schedule_create",
    ),
    (
        "Do you have any tools to post media content to social?",
        "ig.ig_publish_post",  # fuzzy hit expected
    ),
]


async def test_golden_queries_recall():
    """Verify that BM25 + Vector RRF hits the right tools for colloquial queries."""
    from app.services.tool_rag import retrieve_relevant_tools

    for query, expected_tool_id in GOLDEN_QUERIES:
        results = await retrieve_relevant_tools(query, top_k=10, workspace_id=None)

        # Verify the expected tool is in the top 10 results
        hit_ids = [r["tool_id"] for r in results]
        assert (
            expected_tool_id in hit_ids
        ), f"Expected {expected_tool_id} in top 10 for query '{query}', but got {hit_ids}"
