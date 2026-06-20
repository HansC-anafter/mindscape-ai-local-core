"""Indexing helpers for ToolEmbeddingService."""

from __future__ import annotations

import json
import logging
from typing import Any, List

from backend.app.services.tool_embedding_service_core import (
    IndexableEntry,
    MultiModelIndexingError,
    build_embed_text,
    discover_embed_models,
    vector_to_pg_literal,
)

logger = logging.getLogger(__name__)


async def index_tool(
    service: Any,
    tool_id: str,
    display_name: str,
    description: str,
    category: str,
    capability_code: str | None = None,
    affordance: dict[str, Any] | None = None,
) -> bool:
    """Embed and upsert a single tool."""
    embed_text = build_embed_text(display_name, description)
    if capability_code:
        try:
            cap_meta = service._get_capability_manifest_context(capability_code)
            if cap_meta:
                embed_text = build_embed_text(
                    display_name,
                    description,
                    capability_context=cap_meta,
                )
        except Exception:
            pass

    embedding, model_name = await service._generate_embedding(
        embed_text, is_query=False
    )
    if embedding is None or model_name is None:
        logger.warning(f"Skipping tool {tool_id}: embedding failed")
        return False

    embedding_dim = len(embedding)
    embedding_str = vector_to_pg_literal(embedding)

    try:
        conn = service._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO tool_embeddings
                        (tool_id, display_name, description, category,
                         capability_code, embedding, embedding_model,
                         embedding_dim, affordance, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s::vector, %s, %s, %s, now())
                    ON CONFLICT (tool_id, embedding_model)
                    DO UPDATE SET
                        display_name = EXCLUDED.display_name,
                        description = EXCLUDED.description,
                        category = EXCLUDED.category,
                        capability_code = EXCLUDED.capability_code,
                        embedding = EXCLUDED.embedding,
                        embedding_dim = EXCLUDED.embedding_dim,
                        affordance = EXCLUDED.affordance,
                        updated_at = now()
                    """,
                    (
                        tool_id,
                        display_name,
                        description,
                        category,
                        capability_code,
                        embedding_str,
                        model_name,
                        embedding_dim,
                        json.dumps(affordance) if affordance else "{}",
                    ),
                )
            conn.commit()
            return True
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"Failed to index tool {tool_id}: {e}")
        return False


async def collect_indexable_entries(
    service: Any, *, include_playbooks: bool = True
) -> List[IndexableEntry]:
    """Return the shared tool/playbook corpus used for embedding indexing."""
    entries: List[IndexableEntry] = []

    try:
        from backend.app.services.tool_list_service import ToolListService

        all_tools = ToolListService().get_all_tools()
    except Exception as e:
        logger.error(f"Failed to get tool list: {e}")
        all_tools = []

    for tool in all_tools:
        cap_code = None
        if tool.source == "capability" and "." in tool.tool_id:
            cap_code = tool.tool_id.split(".")[0]
        entries.append(
            {
                "tool_id": tool.tool_id,
                "display_name": tool.name,
                "description": tool.description,
                "category": tool.category,
                "capability_code": cap_code,
                "affordance": None,
            }
        )

    if not include_playbooks:
        return entries

    try:
        from backend.app.services.manifest_utils import resolve_playbook_affordance
        from backend.app.services.playbook_registry import get_playbook_registry
        from backend.app.services.playbook_service import PlaybookService

        pb_svc = PlaybookService()
        pb_svc.registry = get_playbook_registry()
        all_playbooks = await pb_svc.list_playbooks()
        seen_codes: set = set()
        for pb in all_playbooks:
            if pb.playbook_code in seen_codes:
                continue
            seen_codes.add(pb.playbook_code)
            affordance_dict = {}
            if pb.playbook_code:
                affordance_dict = resolve_playbook_affordance(pb.playbook_code)
            entries.append(
                {
                    "tool_id": pb.playbook_code,
                    "display_name": pb.name,
                    "description": pb.description or pb.name,
                    "category": "playbook",
                    "capability_code": getattr(pb, "capability_code", None),
                    "affordance": affordance_dict if affordance_dict else None,
                }
            )
    except Exception as exc:
        logger.warning("Playbook indexing corpus build failed (non-fatal): %s", exc)

    return entries


async def index_all_tools(service: Any, *, include_playbooks: bool = True) -> int:
    """Index all tools from ToolListService."""
    entries = await service._collect_indexable_entries(
        include_playbooks=include_playbooks
    )
    count = 0
    tool_entries = 0
    playbook_entries = 0
    for entry in entries:
        ok = await service.index_tool(
            tool_id=entry["tool_id"],
            display_name=entry["display_name"],
            description=entry["description"],
            category=entry["category"],
            capability_code=entry["capability_code"],
            affordance=entry.get("affordance"),
        )
        if ok:
            count += 1
        if entry["category"] == "playbook":
            playbook_entries += 1
        else:
            tool_entries += 1

    logger.info(
        "Indexed %d/%d entries (%d tools, %d playbooks)",
        count,
        len(entries),
        tool_entries,
        playbook_entries,
    )
    return count


async def ensure_indexed(service: Any, *, include_playbooks: bool = True) -> int:
    """Index stale embedding models while preserving the existing startup contract."""
    primary = service._get_current_model()
    ollama_models = discover_embed_models() or [primary]

    if not ollama_models:
        ollama_models = [primary]

    expected = len(
        await service._collect_indexable_entries(include_playbooks=include_playbooks)
    )

    if expected == 0:
        logger.warning("ensure_indexed: no indexable entries found, skipping")
        return 0

    stale_models: List[str] = []
    try:
        conn = service._get_connection()
        try:
            with conn.cursor() as cur:
                for model in ollama_models:
                    cur.execute(
                        "SELECT count(*) FROM tool_embeddings WHERE embedding_model = %s",
                        (model,),
                    )
                    row_count = cur.fetchone()[0]
                    if row_count < expected:
                        logger.info(
                            f"ensure_indexed: model {model} stale "
                            f"({row_count}/{expected}), will re-index"
                        )
                        stale_models.append(model)
                    else:
                        logger.info(
                            f"ensure_indexed: model {model} up to date "
                            f"({row_count} rows)"
                        )
        finally:
            conn.close()
    except Exception as e:
        logger.warning(
            f"ensure_indexed: DB check failed ({e}), forcing full re-index"
        )
        stale_models = ollama_models

    if not stale_models:
        return 0

    total = 0
    for model in stale_models:
        count = await service._index_all_tools_for_model(
            model, include_playbooks=include_playbooks
        )
        logger.info(f"ensure_indexed: [{model}] indexed {count} tools")
        total += count

    if stale_models and expected > 0 and total == 0:
        raise MultiModelIndexingError("Ollama multi-model indexing failed completely")

    return total


async def index_all_tools_multimodel(
    service: Any, *, include_playbooks: bool = True
) -> int:
    """Re-index all tools for every Ollama embed model currently available."""
    embed_models = discover_embed_models()
    if not embed_models:
        logger.info(
            "index_all_tools_multimodel: no Ollama embed models found, using single-model path"
        )
        return await service.index_all_tools(include_playbooks=include_playbooks)

    logger.info(f"index_all_tools_multimodel: indexing for models {embed_models}")

    total = 0
    for model in embed_models:
        count = await service._index_all_tools_for_model(
            model, include_playbooks=include_playbooks
        )
        logger.info(f"  [{model}] indexed {count} tools")
        total += count

    return total


async def index_all_tools_for_model(
    service: Any, model_name: str, *, include_playbooks: bool = True
) -> int:
    """Index all tools and playbooks using a specific embedding model."""
    entries = await service._collect_indexable_entries(
        include_playbooks=include_playbooks
    )
    count = 0
    for entry in entries:
        embed_text = build_embed_text(entry["display_name"], entry["description"])
        if entry["capability_code"]:
            try:
                cap_meta = service._get_capability_manifest_context(
                    entry["capability_code"]
                )
                if cap_meta:
                    embed_text = build_embed_text(
                        entry["display_name"],
                        entry["description"],
                        capability_context=cap_meta,
                    )
            except Exception:
                pass
        emb, used_model = await service._generate_embedding_for_model(
            embed_text, model_name, is_query=False
        )
        if emb is None:
            logger.warning(f"  Embed failed for {entry['tool_id']} ({model_name})")
            continue

        embedding_str = vector_to_pg_literal(emb)
        embedding_dim = len(emb)
        try:
            conn = service._get_connection()
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO tool_embeddings
                            (tool_id, display_name, description, category,
                             capability_code, embedding, embedding_model,
                             embedding_dim, affordance, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s::vector, %s, %s, %s, now())
                        ON CONFLICT (tool_id, embedding_model)
                        DO UPDATE SET
                            display_name = EXCLUDED.display_name,
                            description = EXCLUDED.description,
                            category = EXCLUDED.category,
                            capability_code = EXCLUDED.capability_code,
                            embedding = EXCLUDED.embedding,
                            embedding_dim = EXCLUDED.embedding_dim,
                            affordance = EXCLUDED.affordance,
                            updated_at = now()
                        """,
                        (
                            entry["tool_id"],
                            entry["display_name"],
                            entry["description"],
                            entry["category"],
                            entry["capability_code"],
                            embedding_str,
                            used_model,
                            embedding_dim,
                            json.dumps(entry.get("affordance") or {}),
                        ),
                    )
                conn.commit()
                count += 1
            finally:
                conn.close()
        except Exception as e:
            logger.error(
                f"  DB write failed for {entry['tool_id']} ({model_name}): {e}"
            )

    return count


async def reindex_all(service: Any) -> int:
    """Re-embed all tools with the current model."""
    current_model = service._get_current_model()

    try:
        conn = service._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM tool_embeddings WHERE embedding_model = %s",
                    (current_model,),
                )
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"Failed to clear embeddings for reindex: {e}")
        return 0

    return await service.index_all_tools()
