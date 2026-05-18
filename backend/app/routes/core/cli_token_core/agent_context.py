import logging
import os

logger = logging.getLogger(__name__)


def get_agent_context_payload() -> dict:
    try:
        from backend.app.services.tools.workspace_tools import WorkspaceQueryDatabaseTool

        tool = WorkspaceQueryDatabaseTool()
        tables = sorted(tool.ALLOWED_TABLES)
    except Exception as exc:
        logger.warning("Failed to read ALLOWED_TABLES: %s", exc)
        tables = []

    table_schemas = {}
    if tables:
        try:
            import psycopg2
            import psycopg2.extras

            db_url = (
                os.environ.get("DATABASE_URL_CORE")
                or os.environ.get("DATABASE_URL")
                or "postgresql://mindscape:mindscape_password@postgres:5432/mindscape_core"
            )
            conn = psycopg2.connect(db_url)
            try:
                conn.set_session(readonly=True, autocommit=True)
                cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                placeholders = ",".join(["%s"] * len(tables))
                cur.execute(
                    f"SELECT table_name, column_name, data_type "
                    f"FROM information_schema.columns "
                    f"WHERE table_name IN ({placeholders}) "
                    f"ORDER BY table_name, ordinal_position",
                    tuple(tables),
                )
                for row in cur.fetchall():
                    tname = row["table_name"]
                    col = row["column_name"]
                    dtype = row["data_type"]
                    table_schemas.setdefault(tname, []).append(f"{col} ({dtype})")
                cur.close()
            finally:
                conn.close()
        except Exception as exc:
            logger.warning("Failed to fetch column schemas: %s", exc)

    return {
        "tables": tables,
        "table_schemas": table_schemas,
        "role": (
            "You are a Mindscape AI workspace assistant. "
            "You have access to MCP tools to query and manage workspace data."
        ),
        "data_tool": "mindscape_tool_default_workspace_query_database",
        "data_guidance": (
            "For any question about data, analytics, accounts, targets, "
            "posts, or personas, use the mindscape_tool_default_workspace_query_database "
            "tool to query the PostgreSQL database. Do NOT browse files to find data. "
            "Always provide the actual data in your response. "
            "IMPORTANT: Always reply in the same language the user used."
        ),
        "installed_pack_guides": _get_pack_agent_guides(),
    }


def _get_pack_agent_guides() -> list:
    max_per_guide = 500
    max_total_chars = int(os.environ.get("AGENT_GUIDE_BUDGET", "3000"))

    guides: list = []
    try:
        from backend.app.services.capability_registry import get_registry, load_capabilities
        from backend.app.services.stores.installed_packs_store import InstalledPacksStore

        registry = get_registry()
        if not registry.capabilities:
            load_capabilities()

        enabled_ids = set(InstalledPacksStore().list_enabled_pack_ids())
        for code in enabled_ids:
            cap_info = registry.capabilities.get(code)
            if not cap_info:
                continue
            manifest = cap_info.get("manifest", {})
            guide_ref = manifest.get("agent_guide")
            if not guide_ref:
                continue
            directory = cap_info.get("directory")
            if not directory:
                continue

            guide_path = (directory / guide_ref).resolve()
            if not guide_path.is_relative_to(directory.resolve()):
                logger.warning(
                    "Blocked path traversal in agent_guide for %s: %s",
                    code,
                    guide_ref,
                )
                continue
            if not guide_path.exists():
                continue

            content = guide_path.read_text(encoding="utf-8").strip()[:max_per_guide]
            guides.append(
                {
                    "pack_code": code,
                    "display_name": manifest.get("display_name", code),
                    "guide": content,
                }
            )

        guides.sort(key=lambda item: item["pack_code"])
        total = 0
        capped: list = []
        for guide in guides:
            if total + len(guide["guide"]) > max_total_chars:
                break
            capped.append(guide)
            total += len(guide["guide"])

        truncated_count = len(guides) - len(capped)
        if truncated_count > 0:
            logger.info(
                "Agent guide budget reached: kept %d/%d guides (%d chars)",
                len(capped),
                len(guides),
                total,
            )
        return capped
    except Exception as exc:
        logger.warning("Failed to load pack agent guides: %s", exc)
        return []
