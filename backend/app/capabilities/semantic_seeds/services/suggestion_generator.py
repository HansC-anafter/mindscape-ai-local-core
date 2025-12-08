"""
Suggestion Generator Service
Clusters seeds using pgvector similarity and generates mindscape update suggestions.
"""

import os
import uuid
import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import psycopg2
from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)


class SuggestionGenerator:
    """Generate mindscape update suggestions from clustered seeds"""

    def __init__(self, llm_provider=None, postgres_config=None):
        self.llm_provider = llm_provider
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

    async def generate_suggestions(
        self,
        user_id: str,
        days_back: int = 7,
        max_suggestions: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Generate mindscape update suggestions from recent seeds

        Args:
            user_id: User profile ID
            days_back: How many days back to look
            max_suggestions: Maximum number of suggestions to generate

        Returns:
            List of suggestions
        """
        try:
            recent_seeds = self._get_recent_seeds(user_id, days_back)

            if len(recent_seeds) < 2:
                logger.info(f"Not enough seeds ({len(recent_seeds)}) to generate suggestions")
                return []

            clusters = self._cluster_seeds_by_similarity(recent_seeds)

            suggestions = []
            for cluster in clusters[:max_suggestions]:
                suggestion = await self._create_suggestion_from_cluster(
                    user_id, cluster
                )
                if suggestion:
                    suggestions.append(suggestion)

            logger.info(f"Generated {len(suggestions)} suggestions for profile {user_id}")
            return suggestions

        except Exception as e:
            logger.error(f"Failed to generate suggestions: {e}", exc_info=True)
            return []

    def _get_recent_seeds(self, user_id: str, days_back: int) -> List[Dict]:
        """Get recent seeds from database"""
        cutoff_date = datetime.utcnow() - timedelta(days=days_back)

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor(cursor_factory=RealDictCursor)
                cursor.execute('''
                    SELECT
                        id, user_id, seed_type, content, metadata,
                        source_type, source_id, confidence, weight,
                        updated_at, embedding
                    FROM mindscape_personal
                    WHERE user_id = %s
                      AND updated_at >= %s
                    ORDER BY updated_at DESC
                    LIMIT 100
                ''', (user_id, cutoff_date))

                seeds = []
                for row in cursor.fetchall():
                    seed_dict = dict(row)
                    if 'user_id' not in seed_dict:
                        seed_dict['user_id'] = user_id
                    seeds.append(seed_dict)

                return seeds
        except Exception as e:
            logger.error(f"Failed to get recent seeds: {e}")
            return []

    def _cluster_seeds_by_similarity(
        self,
        seeds: List[Dict],
        similarity_threshold: float = 0.7
    ) -> List[Dict]:
        """Cluster seeds by vector similarity using pgvector"""
        if not seeds:
            return []

        clusters = []
        processed_seed_ids = set()

        for seed in seeds:
            if seed['id'] in processed_seed_ids:
                continue

            similar_seeds = self._find_similar_seeds(
                seed, seeds, similarity_threshold
            )

            if len(similar_seeds) >= 2:
                cluster = {
                    'seeds': similar_seeds,
                    'type': seed.get('seed_type', seed.get('source_type', 'unknown')),
                    'weight': self._calculate_cluster_weight(similar_seeds),
                    'keywords': self._extract_keywords(similar_seeds)
                }
                clusters.append(cluster)

                for s in similar_seeds:
                    processed_seed_ids.add(s['id'])

        clusters.sort(key=lambda c: c['weight'], reverse=True)
        return clusters

    def _find_similar_seeds(
        self,
        seed: Dict,
        all_seeds: List[Dict],
        threshold: float
    ) -> List[Dict]:
        """Find seeds similar to the given seed using vector similarity"""
        if not seed.get('embedding'):
            return [seed]

        similar = [seed]
        seed_embedding = seed['embedding']
        user_id = seed.get('user_id') or 'default-user'
        seed_id = seed['id']
        seed_type = seed.get('seed_type', seed.get('source_type', 'unknown'))

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor(cursor_factory=RealDictCursor)

                if isinstance(seed_embedding, list):
                    embedding_str = '[' + ','.join(map(str, seed_embedding)) + ']'
                else:
                    embedding_str = str(seed_embedding)

                cursor.execute('''
                    SELECT
                        id, user_id, seed_type, content, metadata,
                        source_type, source_id, confidence, weight,
                        updated_at, embedding,
                        1 - (embedding <=> %s::vector) as similarity
                    FROM mindscape_personal
                    WHERE user_id = %s
                      AND id != %s
                      AND seed_type = %s
                      AND embedding IS NOT NULL
                      AND 1 - (embedding <=> %s::vector) >= %s
                    ORDER BY similarity DESC
                    LIMIT 10
                ''', (
                    embedding_str, user_id, seed_id,
                    seed_type, embedding_str, threshold
                ))

                for row in cursor.fetchall():
                    row_dict = dict(row)
                    if 'user_id' not in row_dict:
                        row_dict['user_id'] = user_id
                    similar.append(row_dict)
        except Exception as e:
            logger.warning(f"Failed to find similar seeds using pgvector: {e}, falling back to simple matching")
            content = seed.get('content', '').lower()
            for s in all_seeds:
                if s['id'] != seed_id and s.get('content', '').lower() in content:
                    similar.append(s)

        return similar

    def _calculate_cluster_weight(self, seeds: List[Dict]) -> float:
        """Calculate cluster weight based on seed count, confidence, and time decay"""
        if not seeds:
            return 0.0

        total_weight = 0.0
        now = datetime.utcnow()

        for seed in seeds:
            base = seed.get('weight', 1.0)
            confidence = seed.get('confidence', 0.5)

            updated_at = seed.get('updated_at')
            if updated_at:
                if isinstance(updated_at, str):
                    updated_at = datetime.fromisoformat(updated_at.replace('Z', '+00:00'))
                days_ago = (now - updated_at.replace(tzinfo=None)).days
                time_decay = max(0, 1 - days_ago / 30)
            else:
                time_decay = 1.0

            weight = base * confidence * time_decay
            total_weight += weight

        count_bonus = 1 + (len(seeds) - 1) * 0.1
        return total_weight * count_bonus

    def _extract_keywords(self, seeds: List[Dict]) -> List[str]:
        """Extract keywords from cluster of seeds"""
        keywords = []
        for seed in seeds[:5]:
            text = seed.get('content', '')
            words = text.split()
            if len(words) <= 5:
                keywords.append(text)
            else:
                keywords.append(' '.join(words[:5]))

        return list(set(keywords))[:3]

    async def _create_suggestion_from_cluster(
        self,
        user_id: str,
        cluster: Dict
    ) -> Optional[Dict[str, Any]]:
        """Create a suggestion from a cluster of seeds"""
        if not self.llm_provider:
            return self._create_simple_suggestion(user_id, cluster)

        try:
            contents = [s['content'] for s in cluster['seeds']]
            source_type = cluster['type']

            prompt = f"""Based on the following similar seeds, generate a mindscape update suggestion:

Seed type: {source_type}
Seed content:
{chr(10).join(f'- {text}' for text in contents[:5])}

Please generate:
1. Title (short)
2. Description (explain why this update is suggested, use format "You often mention...")

Return JSON format:
{{
  "title": "...",
  "description": "You often mention \"...\", would you like to add this as a [Long-term Project]?"
}}
"""

            response = await self.llm_provider.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                model="gpt-4o-mini"
            )

            suggestion_data = self._parse_suggestion_response(response)

            suggestion_id = await self._save_suggestion(
                user_id=user_id,
                suggestion_type=source_type,
                title=suggestion_data.get('title', contents[0]),
                description=suggestion_data.get('description', f"You often mention \"{contents[0]}\", would you like to add this as a [Long-term Project]?"),
                source_seed_ids=[s['id'] for s in cluster['seeds']],
                confidence=cluster['weight'] / len(cluster['seeds'])
            )

            return {
                "id": suggestion_id,
                "type": source_type,
                "title": suggestion_data.get('title', contents[0]),
                "description": suggestion_data.get('description', f"You often mention \"{contents[0]}\", would you like to add this as a [Long-term Project]?"),
                "confidence": cluster['weight'] / len(cluster['seeds']),
                "source_summary": f"Recent {len(cluster['seeds'])} usage records"
            }

        except Exception as e:
            logger.error(f"Failed to create suggestion: {e}")
            return self._create_simple_suggestion(user_id, cluster)

    def _create_simple_suggestion(
        self,
        user_id: str,
        cluster: Dict
    ) -> Dict[str, Any]:
        """Create a simple suggestion without LLM"""
        contents = [s['content'] for s in cluster['seeds']]
        source_type = cluster['type']

        type_names = {
            'project': 'Long-term Project',
            'principle': 'Design Principle',
            'preference': 'Preference Setting',
            'intent': 'Intent Card',
            'entity': 'Key Concept'
        }

        title = contents[0] if contents else "Unnamed"
        description = f"You often mention \"{title}\", would you like to add this as a [{type_names.get(source_type, 'Setting')}]?"

        return {
            "type": source_type,
            "title": title,
            "description": description,
            "confidence": cluster['weight'] / len(cluster['seeds']),
            "source_summary": f"Recent {len(cluster['seeds'])} usage records"
        }

    def _parse_suggestion_response(self, response: str) -> Dict[str, Any]:
        """Parse LLM response to extract suggestion"""
        try:
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            return {}
        except Exception as e:
            logger.error(f"Failed to parse suggestion response: {e}")
            return {}

    async def _save_suggestion(
        self,
        user_id: str,
        suggestion_type: str,
        title: str,
        description: str,
        source_seed_ids: List[str],
        confidence: float
    ) -> str:
        """Save suggestion to database"""
        suggestion_id = str(uuid.uuid4())

        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            self._ensure_suggestion_table_exists(cursor)
            conn.commit()

            cursor.execute('''
                INSERT INTO mindscape_suggestions (
                    id, user_id, suggestion_type, title, description,
                    suggested_data, source_seed_ids, source_summary,
                    confidence, status, generated_at, created_at, updated_at
                ) VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s, %s, %s
                )
            ''', (
                suggestion_id, user_id, suggestion_type, title, description,
                json.dumps({"type": suggestion_type}), source_seed_ids,
                f"Recent {len(source_seed_ids)} usage records",
                confidence, 'pending', datetime.utcnow(), datetime.utcnow(), datetime.utcnow()
            ))

            conn.commit()
        finally:
            conn.close()

        return suggestion_id

    def _ensure_suggestion_table_exists(self, cursor):
        """Ensure mindscape_suggestions table exists"""
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS mindscape_suggestions (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id TEXT NOT NULL,
                suggestion_type TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                suggested_data JSONB,
                source_seed_ids UUID[],
                source_summary TEXT,
                confidence REAL NOT NULL,
                status TEXT DEFAULT 'pending',
                reviewed_at TIMESTAMP,
                reviewed_by TEXT,
                generated_at TIMESTAMP DEFAULT NOW(),
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_suggestions_profile
            ON mindscape_suggestions(user_id)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_suggestions_status
            ON mindscape_suggestions(status)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_suggestions_generated_at
            ON mindscape_suggestions(generated_at DESC)
        ''')

