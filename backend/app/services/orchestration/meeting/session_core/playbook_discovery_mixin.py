"""Installed playbook discovery helpers for meeting sessions."""

import logging

logger = logging.getLogger(__name__)


class MeetingSessionPlaybookDiscoveryMixin:
    async def _async_load_installed_playbooks(self) -> str:
        """Load available playbooks for prompt injection."""
        seen: set = set()
        candidates: list = []  # list of (tool_id, display_text)
        ws_id = getattr(self.session, "workspace_id", None)

        def _add(tool_id: str, text: str) -> bool:
            if tool_id in seen:
                return False
            seen.add(tool_id)
            candidates.append((tool_id, text))
            return True

        def _confidence_ok() -> bool:
            """Confidence gate: enough candidates to support LLM decision."""
            return len(candidates) >= 3

        try:
            try:
                from app.services.tool_embedding_service import (
                    ToolEmbeddingService,
                )

                rag_svc = ToolEmbeddingService()
                agenda = getattr(self.session, "agenda", []) or []
                user_msg = getattr(self, "_last_user_message", "")
                parts = list(agenda) + ([user_msg] if user_msg else [])
                query = "; ".join(parts) if parts else "available playbooks"

                matches, _status = await rag_svc.search_rrf(
                    query=query, top_k=15, min_score=0.15
                )
                pb_matches = [m for m in matches if m.category == "playbook"]
                for m in pb_matches:
                    _add(m.tool_id, f"- {m.tool_id}: {m.display_name}")

                logger.info(
                    "Playbook discovery round=1 semantic candidates=%d "
                    "top=%s action=%s session=%s",
                    len(pb_matches),
                    pb_matches[0].tool_id if pb_matches else "none",
                    "accept" if _confidence_ok() else "escalate",
                    getattr(self.session, "id", "?"),
                )
            except Exception as rag_exc:
                logger.warning("Playbook discovery round=1 failed: %s", rag_exc)

            if not _confidence_ok():
                try:
                    from app.services.stores.postgres.workspaces_store import (
                        PostgresWorkspacesStore,
                    )
                    from app.services.manifest_utils import (
                        resolve_playbook_produces,
                    )
                    from pathlib import Path
                    import os
                    import yaml as _yaml

                    ws_store = PostgresWorkspacesStore()
                    ws = ws_store.get_workspace_sync(ws_id) if ws_id else None
                    ds = getattr(ws, "data_sources", None) or {}
                    available_types: set = set()
                    for _pack_id, pack_data in ds.items():
                        if isinstance(pack_data, dict):
                            for prod in pack_data.get("produces", []):
                                if isinstance(prod, dict) and prod.get("type"):
                                    available_types.add(prod["type"])

                    if available_types:
                        app_dir = os.getenv("APP_DIR", "/app")
                        cap_dirs = [
                            Path(app_dir) / "backend" / "app" / "capabilities",
                            Path(os.getenv("DATA_DIR", "data")) / "capabilities",
                        ]
                        from app.services.stores.installed_packs_store import (
                            InstalledPacksStore,
                        )

                        packs_store = InstalledPacksStore()
                        pack_ids = packs_store.list_enabled_pack_ids()
                        r2_count = 0
                        for pack_id in pack_ids:
                            for cap_base in cap_dirs:
                                mpath = cap_base / pack_id / "manifest.yaml"
                                if not mpath.exists():
                                    continue
                                try:
                                    with mpath.open("r", encoding="utf-8") as mf:
                                        manifest = _yaml.safe_load(mf) or {}
                                    for pb in manifest.get("playbooks", []):
                                        if not isinstance(pb, dict):
                                            continue
                                        code = pb.get("code", "")
                                        if not code or code in seen:
                                            continue
                                        consumes = pb.get("consumes") or []
                                        consumes_types = {
                                            (c.get("type", "") if isinstance(c, dict) else c)
                                            for c in consumes
                                            if c
                                        }
                                        if consumes_types & available_types:
                                            desc = (pb.get("description") or code)[:60]
                                            if _add(code, f"- {code}: {desc}"):
                                                r2_count += 1
                                except Exception as exc:
                                    logger.warning(
                                        f"R2 Error parsing manifest for pack {pack_id}: {exc}"
                                    )
                                break

                        logger.info(
                            "Playbook discovery round=2 structural +%d "
                            "candidates=%d action=%s",
                            r2_count,
                            len(candidates),
                            "accept" if _confidence_ok() else "escalate",
                        )
                except Exception as r2_exc:
                    logger.warning("Playbook discovery round=2 failed: %s", r2_exc)

            if not _confidence_ok():
                try:
                    from app.services.stores.postgres.workspaces_store import (
                        PostgresWorkspacesStore,
                    )
                    from app.services.stores.installed_packs_store import (
                        InstalledPacksStore,
                    )
                    from pathlib import Path
                    import os
                    import yaml as _yaml

                    packs_store = InstalledPacksStore()
                    eligible_packs = set(packs_store.list_enabled_pack_ids())

                    app_dir = os.getenv("APP_DIR", "/app")
                    cap_dirs = [
                        Path(app_dir) / "backend" / "app" / "capabilities",
                        Path(os.getenv("DATA_DIR", "data")) / "capabilities",
                    ]
                    r3_count = 0
                    for pack_id in eligible_packs:
                        for cap_base in cap_dirs:
                            mpath = cap_base / pack_id / "manifest.yaml"
                            if not mpath.exists():
                                continue
                            try:
                                with mpath.open("r", encoding="utf-8") as mf:
                                    manifest = _yaml.safe_load(mf) or {}
                                for pb in manifest.get("playbooks", []):
                                    if isinstance(pb, dict):
                                        code = pb.get("code", "")
                                        desc = (pb.get("description") or code)[:60]
                                        logger.info(
                                            f"R3 parsing pb={code} from pack={pack_id}"
                                        )
                                        if code and _add(code, f"- {code}: {desc}"):
                                            r3_count += 1
                                            logger.info(f"R3 added {code}")
                            except Exception as exc:
                                logger.warning(
                                    f"R3 Error parsing manifest for pack {pack_id}: {exc}"
                                )
                            break
                        else:
                            logger.info(f"R3 manifest NOT FOUND for pack {pack_id}")

                    logger.info(
                        "Playbook discovery round=3 eligible_scan +%d "
                        "candidates=%d packs=%d",
                        r3_count,
                        len(candidates),
                        len(eligible_packs),
                    )
                except Exception as r3_exc:
                    logger.warning("Playbook discovery round=3 failed: %s", r3_exc)

            if candidates:
                return "\n".join(text for _, text in candidates)
            return "(no playbooks discovered)"
        except Exception as exc:
            logger.warning("Failed to load installed playbooks: %s", exc, exc_info=True)
            return "(playbook discovery unavailable)"
