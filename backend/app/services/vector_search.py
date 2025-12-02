"""
Vector Search Service
Provides semantic search across pgvector tables
"""

import os
import logging
from typing import List, Dict, Any, Optional
import psycopg2
from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)


class VectorSearchService:
    """Semantic search service using pgvector"""

    def __init__(self, postgres_config=None):
        self.postgres_config = postgres_config or self._get_postgres_config()

    def _get_postgres_config(self):
        """Get PostgreSQL config from environment"""
        return {
            "host": os.getenv("POSTGRES_HOST", "postgres"),
            "port": int(os.getenv("POSTGRES_PORT", "5432")),
            "database": os.getenv("POSTGRES_DB", "mindscape_vectors"),
            "user": os.getenv("POSTGRES_USER", "mindscape"),
            "password": os.getenv("POSTGRES_PASSWORD", "mindscape_password"),
        }

    def _get_connection(self):
        """Get PostgreSQL connection"""
        return psycopg2.connect(**self.postgres_config)

    async def check_connection(self) -> bool:
        """Check if Vector DB connection is available"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.close()
            conn.close()
            return True
        except Exception as e:
            logger.warning(f"Vector DB connection check failed: {e}")
            return False

    async def _generate_embedding(self, text: str) -> Optional[List[float]]:
        """Generate embedding for query text"""
        try:
            openai_key = os.getenv("OPENAI_API_KEY")
            if not openai_key:
                logger.warning("OPENAI_API_KEY not set")
                return None

            import openai
            client = openai.OpenAI(api_key=openai_key)
            response = client.embeddings.create(
                model="text-embedding-3-small",
                input=text
            )
            return response.data[0].embedding

        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}")
            return None

    async def vector_search(
        self,
        table: str,
        query_embedding: List[float],
        filters: Dict[str, Any] = None,
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Generic vector search across any table

        Args:
            table: Table name (mindscape_personal, playbook_knowledge, external_docs)
            query_embedding: Query vector
            filters: Additional filters (e.g., {"playbook_code": "xxx"})
            top_k: Number of results

        Returns:
            List of matching records with similarity scores
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor(cursor_factory=RealDictCursor)

            # Build WHERE clause from filters
            where_clauses = []
            params = []

            if filters:
                for key, value in filters.items():
                    where_clauses.append(f"{key} = %s")
                    params.append(value)

            where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

            # Execute vector similarity search
            query = f'''
                SELECT
                    *,
                    1 - (embedding <=> %s::vector) as similarity
                FROM {table}
                {where_sql}
                ORDER BY embedding <=> %s::vector
                LIMIT %s
            '''

            params = [str(query_embedding)] + params + [str(query_embedding), top_k]
            cursor.execute(query, params)

            results = cursor.fetchall()
            return [dict(row) for row in results]

        finally:
            conn.close()

    async def search_playbook_sop(
        self,
        playbook_code: str,
        query: str,
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Search for relevant Playbook SOP chunks

        Args:
            playbook_code: Playbook identifier
            query: User query
            top_k: Number of results

        Returns:
            List of relevant SOP chunks
        """
        query_embedding = await self._generate_embedding(query)
        if not query_embedding:
            return []

        return await self.vector_search(
            table="playbook_knowledge",
            query_embedding=query_embedding,
            filters={"playbook_code": playbook_code},
            top_k=top_k
        )

    async def search_personal_context(
        self,
        user_id: str,
        query: str,
        top_k: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Search user's personal mindscape context

        Args:
            user_id: User identifier
            query: User query
            top_k: Number of results

        Returns:
            List of relevant personal context
        """
        query_embedding = await self._generate_embedding(query)
        if not query_embedding:
            return []

        return await self.vector_search(
            table="mindscape_personal",
            query_embedding=query_embedding,
            filters={"user_id": user_id},
            top_k=top_k
        )

    async def execute_playbook_with_context(
        self,
        playbook_code: str,
        user_query: str,
        user_id: str = "default_user"
    ) -> Dict[str, Any]:
        """
        场景 1：AI 成员执行 Playbook时查询 SOP + 个人context

        Args:
            playbook_code: Playbook identifier
            user_query: User's query or task description
            user_id: User identifier

        Returns:
            Combined context for AI
        """
        # 1. Search Playbook SOP
        playbook_chunks = await self.search_playbook_sop(
            playbook_code=playbook_code,
            query=user_query,
            top_k=5
        )

        # 2. Search personal context
        personal_context = await self.search_personal_context(
            user_id=user_id,
            query=user_query,
            top_k=3
        )

        # 3. Format context
        context = {
            "playbook_sop": [
                {
                    "content": chunk["content"],
                    "section_type": chunk["section_type"],
                    "similarity": chunk["similarity"]
                }
                for chunk in playbook_chunks
            ],
            "personal_context": [
                {
                    "content": ctx["content"],
                    "source_type": ctx["source_type"],
                    "similarity": ctx["similarity"]
                }
                for ctx in personal_context
            ]
        }

        # 4. Generate formatted context string
        context_text = self._format_context_for_llm(context)

        return {
            "context": context,
            "context_text": context_text,
            "playbook_code": playbook_code
        }

    def _format_context_for_llm(self, context: Dict[str, Any]) -> str:
        """Format context for LLM consumption"""
        parts = []

        # Playbook SOP
        if context["playbook_sop"]:
            parts.append("## Playbook SOP:")
            for i, chunk in enumerate(context["playbook_sop"], 1):
                parts.append(f"\n### {chunk['section_type'].title()} (相似度: {chunk['similarity']:.2f})")
                parts.append(chunk["content"])

        # Personal context
        if context["personal_context"]:
            parts.append("\n\n## Your Personal Context:")
            for i, ctx in enumerate(context["personal_context"], 1):
                parts.append(f"\n### {ctx['source_type']} (相似度: {ctx['similarity']:.2f})")
                parts.append(ctx["content"])

        return "\n".join(parts)

    async def search_external_docs(
        self,
        query: str,
        source_apps: List[str] = None,
        user_id: str = "default_user",
        top_k: int = 10
    ) -> List[Dict[str, Any]]:
        """
        场景 2：搜索外部知识（RAG）

        Args:
            query: Search query
            source_apps: Filter by source apps (wordpress, notion, etc.)
            user_id: User identifier
            top_k: Number of results

        Returns:
            List of relevant external documents
        """
        query_embedding = await self._generate_embedding(query)
        if not query_embedding:
            return []

        # Build filters
        filters = {"user_id": user_id}

        # Note: For source_apps filtering, we need a different approach
        # since it's a list filter, not single value
        # For now, we'll do post-filtering

        conn = self._get_connection()
        try:
            cursor = conn.cursor(cursor_factory=RealDictCursor)

            where_clauses = ["user_id = %s"]
            params = [user_id]

            if source_apps:
                where_clauses.append("source_app = ANY(%s)")
                params.append(source_apps)

            where_sql = f"WHERE {' AND '.join(where_clauses)}"

            query_sql = f'''
                SELECT
                    *,
                    1 - (embedding <=> %s::vector) as similarity
                FROM external_docs
                {where_sql}
                ORDER BY embedding <=> %s::vector
                LIMIT %s
            '''

            params = [str(query_embedding)] + params + [str(query_embedding), top_k]
            cursor.execute(query_sql, params)

            results = cursor.fetchall()
            return [dict(row) for row in results]

        finally:
            conn.close()

    async def multi_scope_search(
        self,
        query: str,
        user_id: str,
        workspace_id: Optional[str] = None,
        intent_id: Optional[str] = None,
        scopes: List[str] = None,
        top_k_per_scope: Dict[str, int] = None
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Multi-scope hierarchical memory search

        Args:
            query: Search query text
            user_id: User identifier
            workspace_id: Optional workspace ID
            intent_id: Optional intent ID
            scopes: List of scopes to search ('global', 'workspace', 'intent')
            top_k_per_scope: Dict mapping scope to top_k (e.g., {'global': 3, 'workspace': 8})

        Returns:
            Dict mapping scope to list of results
        """
        if scopes is None:
            scopes = ['global', 'workspace', 'intent']

        if top_k_per_scope is None:
            top_k_per_scope = {
                'global': 3,
                'workspace': 8,
                'intent': 8
            }

        query_embedding = await self._generate_embedding(query)
        if not query_embedding:
            return {scope: [] for scope in scopes}

        results = {}

        for scope in scopes:
            filters = {
                'user_id': user_id,
                'scope': scope
            }

            if scope == 'workspace' and workspace_id:
                filters['workspace_id'] = workspace_id
            elif scope == 'intent' and intent_id:
                filters['intent_id'] = intent_id
                if workspace_id:
                    filters['workspace_id'] = workspace_id

            top_k = top_k_per_scope.get(scope, 5)

            scope_results = await self.vector_search(
                table="mindscape_personal",
                query_embedding=query_embedding,
                filters=filters,
                top_k=top_k * 2  # Get more results for composite scoring
            )

            # Apply composite scoring
            scored_results = await self._calculate_composite_scores(
                scope_results,
                query_embedding
            )

            # Return top_k after scoring
            results[scope] = scored_results[:top_k]

        return results

    async def _calculate_composite_scores(
        self,
        results: List[Dict[str, Any]],
        query_embedding: List[float]
    ) -> List[Dict[str, Any]]:
        """
        Calculate composite scores using multiple factors

        Score = α * cosine_similarity + β * recency_score + γ * importance

        Args:
            results: List of search results
            query_embedding: Query embedding vector

        Returns:
            List of results sorted by composite score
        """
        from datetime import datetime, timezone
        import math

        # Weight factors (can be configured)
        alpha = 0.6  # cosine similarity weight
        beta = 0.2   # recency weight
        gamma = 0.2  # importance weight

        scored_results = []

        for result in results:
            # Cosine similarity (already calculated in vector_search)
            similarity = result.get('similarity', 0.0)

            # Recency score (based on last_used_at)
            recency_score = 0.5  # default
            if 'last_used_at' in result and result['last_used_at']:
                try:
                    if isinstance(result['last_used_at'], str):
                        last_used = datetime.fromisoformat(result['last_used_at'].replace('Z', '+00:00'))
                    else:
                        last_used = result['last_used_at']

                    if last_used.tzinfo is None:
                        last_used = last_used.replace(tzinfo=timezone.utc)

                    now = datetime.now(timezone.utc)
                    days_ago = (now - last_used).days

                    # Exponential decay: more recent = higher score
                    # Score decays to 0.1 after 30 days
                    recency_score = max(0.1, math.exp(-days_ago / 30.0))
                except Exception as e:
                    logger.debug(f"Failed to calculate recency score: {e}")

            # Importance score
            importance = result.get('importance', 0.5)
            if importance is None:
                importance = 0.5

            # Composite score
            composite_score = (
                alpha * similarity +
                beta * recency_score +
                gamma * importance
            )

            result['composite_score'] = composite_score
            result['recency_score'] = recency_score
            scored_results.append(result)

        # Sort by composite score (descending)
        scored_results.sort(key=lambda x: x['composite_score'], reverse=True)

        return scored_results

    async def update_last_used_at(
        self,
        record_ids: List[str],
        table: str = "mindscape_personal"
    ):
        """
        Update last_used_at timestamp for records

        Args:
            record_ids: List of record IDs to update
            table: Table name
        """
        if not record_ids:
            return

        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            # Update last_used_at for all matching IDs
            placeholders = ','.join(['%s'] * len(record_ids))
            query = f"""
                UPDATE {table}
                SET last_used_at = NOW()
                WHERE id::text = ANY(ARRAY[{placeholders}])
            """

            cursor.execute(query, record_ids)
            conn.commit()

            logger.debug(f"Updated last_used_at for {len(record_ids)} records in {table}")

        finally:
            conn.close()
