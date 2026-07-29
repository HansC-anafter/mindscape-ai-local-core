"""Create the single public knowledge_query tool."""

from .tool import KnowledgeQueryTool


def create_knowledge_query_tool() -> KnowledgeQueryTool:
    return KnowledgeQueryTool()


__all__ = ["KnowledgeQueryTool", "create_knowledge_query_tool"]
