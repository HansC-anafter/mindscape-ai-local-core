"""
Seed Extractor Service
Extracts semantic seeds from task executions, conversations, and tool calls.
Uses LLM to extract themes, concepts, and entities, then generates embeddings.
"""

import os
import uuid
import json
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
import psycopg2
from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)


class SeedExtractor:
    """Extract semantic seeds from content using LLM and generate embeddings"""

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

    async def extract_seeds_from_content(
        self,
        user_id: str,
        content: str,
        source_type: str,
        source_id: Optional[str] = None,
        source_context: Optional[str] = None,
        locale: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Extract seeds from content using LLM

        Args:
            user_id: User profile ID
            content: Task text or conversation content
            source_type: 'execution', 'conversation', 'tool_call', or 'file_upload'
            source_id: ID of the source (execution ID, etc.)
            source_context: Additional context
            locale: Locale code for i18n (defaults to "en" if not provided)

        Returns:
            List of extracted seeds with embeddings
        """
        if not self.llm_provider:
            logger.warning("LLM provider not available, skipping seed extraction")
            return []

        try:
            from backend.app.services.i18n_service import get_i18n_service

            locale = locale or "en"
            i18n = get_i18n_service(default_locale=locale)

            prompt_template_str = i18n.t(
                "semantic_seeds",
                "extract_seeds_prompt",
                default="""Extract semantic seeds from the following content:

Content:
{{content}}

Please extract the following types of seeds:
1. Long-term goals/projects (if mentioned, such as "XXX project", "build XXX")
2. Work mode preferences (task handling methods, such as "break down problems first", "list schedule first", "prefer outline")
3. Emotion/stress patterns (if any, such as "not enough time", "high stress", "switching costs")
4. Key people/brands/concepts (frequently mentioned names, brands, key concepts)

Return in JSON format, each seed contains:
- type: 'project', 'principle', 'preference', 'intent', 'entity'
- text: seed text
- confidence: confidence level (0-1)

Return format:
{{
  "seeds": [
    {{"type": "project", "text": "...", "confidence": 0.8}},
    ...
  ]
}}"""
            )

            # Use replace instead of format to avoid issues with JSON braces
            prompt = prompt_template_str.replace("{{content}}", content)

            # Get model name from system settings (no fallback, no hardcoding)
            from backend.app.shared.llm_provider_helper import get_model_name_from_chat_model
            model_name = get_model_name_from_chat_model()
            if not model_name:
                raise ValueError("chat_model not configured in system settings. Please configure chat_model in Settings.")

            response = await self.llm_provider.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                model=model_name
            )

            # Log raw response for debugging
            logger.debug(f"LLM raw response (first 500 chars): {response[:500] if response else 'None'}")

            # Parse LLM response
            seeds_data = self._parse_llm_response(response)

            # Generate embeddings and save seeds
            saved_seeds = []
            for seed_data in seeds_data:
                # Generate embedding
                embedding = await self._generate_embedding(seed_data['text'])

                # Save to database
                seed_id = await self._save_seed(
                    user_id=user_id,
                    seed_type=seed_data['type'],
                    content=seed_data['text'],
                    confidence=seed_data.get('confidence', 0.5),
                    embedding=embedding,
                    source_type=source_type,
                    source_id=source_id,
                    source_context=source_context
                )

                saved_seeds.append({
                    "id": seed_id,
                    "type": seed_data['type'],
                    "text": seed_data['text'],
                    "confidence": seed_data.get('confidence', 0.5)
                })

            logger.info(f"Extracted {len(saved_seeds)} seeds from {source_type} {source_id}")
            return saved_seeds

        except Exception as e:
            logger.error(f"Failed to extract seeds: {e}", exc_info=True)
            return []

    def _parse_llm_response(self, response: str) -> List[Dict[str, Any]]:
        """Parse LLM response to extract seeds"""
        try:
            if not response:
                logger.warning("Empty LLM response")
                return []

            import re
            # Try to find JSON object, handling markdown code blocks
            # First, try to extract from markdown code blocks
            json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response, re.DOTALL)
            if not json_match:
                # If no code block, try to find JSON object directly
                json_match = re.search(r'\{.*\}', response, re.DOTALL)

            if json_match:
                json_str = json_match.group(1) if json_match.lastindex else json_match.group()
                # Clean up the JSON string
                json_str = json_str.strip()
                data = json.loads(json_str)
                seeds = data.get('seeds', [])
                logger.info(f"Parsed {len(seeds)} seeds from LLM response")
                return seeds
            else:
                logger.warning(f"Could not find JSON in LLM response. Response preview: {response[:200]}")
                return []
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}. Response preview: {response[:500]}")
            return []
        except Exception as e:
            logger.error(f"Failed to parse LLM response: {e}. Response preview: {response[:500]}")
            return []

    async def _generate_embedding(self, text: str) -> List[float]:
        """Generate embedding for text using OpenAI"""
        try:
            openai_key = os.getenv("OPENAI_API_KEY")
            if openai_key:
                import openai
                client = openai.OpenAI(api_key=openai_key)
                response = client.embeddings.create(
                    model="text-embedding-3-small",
                    input=text
                )
                return response.data[0].embedding

            logger.warning("No embedding provider available")
            return []

        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}")
            return []

    async def _save_seed(
        self,
        user_id: str,
        seed_type: str,
        content: str,
        confidence: float,
        embedding: List[float],
        source_type: str,
        source_id: Optional[str] = None,
        source_context: Optional[str] = None
    ) -> str:
        """Save seed to PostgreSQL database"""
        seed_id = str(uuid.uuid4())

        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            # Ensure table exists
            self._ensure_seed_table_exists(cursor)
            conn.commit()

            # Convert embedding to PostgreSQL vector format
            if embedding:
                cursor.execute('''
                    INSERT INTO mindscape_personal (
                        id, user_id, seed_type, content, metadata,
                        source_type, source_id, source_context,
                        confidence, weight, updated_at, created_at, embedding
                    ) VALUES (
                        %s, %s, %s, %s, %s,
                        %s, %s, %s,
                        %s, %s, %s, %s, %s::vector
                    )
                ''', (
                    seed_id, user_id, seed_type, content,
                    json.dumps({}) if not source_context else json.dumps({"context": source_context}),
                    source_type, source_id, source_context,
                    confidence, 1.0, datetime.utcnow(), datetime.utcnow(),
                    str(embedding)
                ))
            else:
                cursor.execute('''
                    INSERT INTO mindscape_personal (
                        id, user_id, seed_type, content, metadata,
                        source_type, source_id, source_context,
                        confidence, weight, updated_at, created_at
                    ) VALUES (
                        %s, %s, %s, %s, %s,
                        %s, %s, %s,
                        %s, %s, %s, %s
                    )
                ''', (
                    seed_id, user_id, seed_type, content,
                    json.dumps({}) if not source_context else json.dumps({"context": source_context}),
                    source_type, source_id, source_context,
                    confidence, 1.0, datetime.utcnow(), datetime.utcnow()
                ))

            conn.commit()
        finally:
            conn.close()

        return seed_id

    def _ensure_seed_table_exists(self, cursor):
        """Ensure mindscape_personal table exists with pgvector support"""
        try:
            cursor.execute("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
            if not cursor.fetchone():
                cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
        except Exception as e:
            logger.warning(f"Could not check/create pgvector extension: {e}")

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS mindscape_personal (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id TEXT NOT NULL,
                seed_type TEXT NOT NULL,
                content TEXT NOT NULL,
                metadata JSONB,
                source_type TEXT NOT NULL,
                source_id TEXT,
                source_context TEXT,
                confidence REAL DEFAULT 0.5,
                weight REAL DEFAULT 1.0,
                embedding vector(1536),
                updated_at TIMESTAMP DEFAULT NOW(),
                created_at TIMESTAMP DEFAULT NOW()
            )
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_mindscape_personal_user
            ON mindscape_personal(user_id)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_mindscape_personal_seed_type
            ON mindscape_personal(seed_type)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_mindscape_personal_source_type
            ON mindscape_personal(source_type)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_mindscape_personal_updated_at
            ON mindscape_personal(updated_at DESC)
        ''')

        try:
            cursor.execute('SELECT COUNT(*) FROM mindscape_personal WHERE embedding IS NOT NULL')
            count = cursor.fetchone()[0]
            if count > 0:
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_mindscape_personal_embedding
                    ON mindscape_personal
                    USING ivfflat (embedding vector_cosine_ops)
                    WITH (lists = 100)
                ''')
        except Exception as e:
            logger.warning(f"Could not create vector index: {e}")

