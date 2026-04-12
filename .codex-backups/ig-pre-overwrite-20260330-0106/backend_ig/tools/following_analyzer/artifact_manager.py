"""
Artifact manager for Instagram following analyzer.

This module handles creating and updating progress artifacts during analysis.
"""

import logging
import time
import uuid
from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)


from threading import Lock
from typing import Any, Callable, Dict, List, Optional

from backend.app.models.workspace import Artifact, ArtifactType, PrimaryActionType
from backend.app.services.stores.postgres.artifacts_store import PostgresArtifactsStore

from .persistence import persist_accounts_flat
from .progress import generate_summary

logger = logging.getLogger(__name__)


class ArtifactManager:
    """
    Manages progress artifact creation and updates during following analysis.
    """

    def __init__(
        self,
        artifacts_store: Optional[PostgresArtifactsStore],
        workspace_id: str,
        trace_id: Optional[str],
        target_username: str,
        user_data_dir: Optional[str],
        visit_account_pages: bool,
        schema_version: str,
        seed_version: Optional[str],
        run_mode: Optional[str],
    ):
        self.artifacts_store = artifacts_store
        self.workspace_id = workspace_id
        self.trace_id = trace_id
        self.target_username = target_username
        self.user_data_dir = user_data_dir
        self.visit_account_pages = visit_account_pages
        self.schema_version = schema_version
        self.seed_version = seed_version
        self.run_mode = run_mode

        # State tracking
        self.progress_artifact_id: Optional[str] = None
        self.source_account_handle: Optional[str] = None
        self.expected_following_count: Optional[int] = None
        self.scroll_stop_reason: Optional[str] = None
        self.list_capture_status: Optional[str] = None
        self.list_capture_evidence: Optional[Dict[str, Any]] = None
        self.scroll_debug_screenshots: List[str] = []
        self.scroll_debug_screenshot_notes: List[Dict[str, Any]] = []
        self.pre_scroll_state: Dict[str, Any] = {}

        # Watchdog state (shared between main flow and watchdog thread)
        self._lock = Lock()
        self._last_upsert_ts = time.time()
        self._last_accounts: List[Dict[str, Any]] = []
        self._last_progress: Dict[str, Any] = {"stage": "init"}

    def set_source_account_handle(self, handle: Optional[str]) -> None:
        """Set the logged-in account handle."""
        self.source_account_handle = handle

    def set_expected_following_count(self, count: Optional[int]) -> None:
        """Set expected following count from profile."""
        self.expected_following_count = count

    def set_scroll_stop_reason(self, reason: Optional[str]) -> None:
        """Set reason for scroll termination."""
        self.scroll_stop_reason = reason

    def set_list_capture_status(self, status: Optional[str]) -> None:
        """Set list capture status."""
        self.list_capture_status = status

    def set_list_capture_evidence(self, evidence: Optional[Dict[str, Any]]) -> None:
        """Set list capture evidence."""
        self.list_capture_evidence = evidence

    def add_debug_screenshot(
        self, path: str, note: Optional[Dict[str, Any]] = None
    ) -> None:
        """Add a debug screenshot path."""
        self.scroll_debug_screenshots.append(path)
        if note:
            self.scroll_debug_screenshot_notes.append(note)

    def update_pre_scroll_state(self, **fields: Any) -> None:
        """Persist pre-scroll phase diagnostics across later artifact updates."""
        self.pre_scroll_state.update(fields)

    def get_watchdog_state(self) -> Dict[str, Any]:
        """Get current state for watchdog thread."""
        with self._lock:
            return {
                "last_upsert_ts": self._last_upsert_ts,
                "accounts": self._last_accounts,
                "progress": self._last_progress,
                "artifact_id": self.progress_artifact_id,
            }

    def update_watchdog_timestamp(self) -> None:
        """Update the last upsert timestamp (called from watchdog after heartbeat)."""
        with self._lock:
            self._last_upsert_ts = time.time()

    def _get_existing_progress_artifact_id(self) -> Optional[str]:
        """
        Find an existing progress artifact for the same workspace + target + profile combination.
        This enables incremental updates instead of creating duplicate artifacts on every run.

        Returns the artifact ID if found, None otherwise.
        """
        if not self.artifacts_store:
            return None

        try:
            candidates = self.artifacts_store.list_artifacts_by_playbook(
                self.workspace_id, "ig_analyze_following"
            )
        except Exception:
            return None

        # Find progress artifacts for the same target+profile
        for art in candidates or []:
            try:
                m = art.metadata or {}
                if (m.get("source") or "") != "ig_analyze_following_progress":
                    continue
                c = art.content or {}
                cm = (c.get("metadata") or {}) if isinstance(c, dict) else {}
                if (cm.get("target_username") or "") != self.target_username:
                    continue
                if (cm.get("source_profile_ref") or "") != (self.user_data_dir or ""):
                    continue
                # Found a matching artifact - return its ID
                self._debug_log(f"Found existing artifact: {art.id}")
                return str(art.id)
            except Exception:
                continue

        self._debug_log("No existing artifact found, will create new")
        return None

    def _debug_log(self, message: str) -> None:
        """Write debug log to file."""
        try:
            with open("/app/data/ig_debug_upsert.log", "a") as f:
                f.write(f"[{datetime.now().isoformat()}] {message}\n")
        except Exception:
            pass

    def _build_metadata(
        self, accounts: List[Dict[str, Any]], progress: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Build metadata dict for artifact content."""
        metadata = {
            "schema_version": self.schema_version,
            "seed_version": self.seed_version,
            "target_username": self.target_username,
            "workspace_id": self.workspace_id,
            "analyzed_at": datetime.now().isoformat(),
            "total_accounts": len(accounts),
            "visit_account_pages": self.visit_account_pages,
            "trace_id": self.trace_id,
            "execution_id": self.trace_id,
            "source_account_handle": self.source_account_handle,
            "source_profile_ref": self.user_data_dir,
            "target_seed": self.target_username,
            "capture_method": "following_list",
            "run_mode": self.run_mode,
            "stage": progress.get("stage") or "following_list_scroll",
            "expected_following_count": self.expected_following_count,
            "scroll_stop_reason": self.scroll_stop_reason,
            "list_capture_status": self.list_capture_status,
            "list_capture_evidence": self.list_capture_evidence,
            "scroll_debug_screenshots": self.scroll_debug_screenshots[-10:],
            "scroll_debug_screenshot_notes": self.scroll_debug_screenshot_notes[-10:],
        }

        if self.pre_scroll_state:
            metadata.update(self.pre_scroll_state)

        # Surface last-known scroll diagnostics in metadata for quick UI inspection.
        try:
            if (progress.get("stage") or "") == "scrolling":
                metadata["scroll_iteration"] = progress.get("iteration")
                metadata["scroll_no_new_accounts_streak"] = progress.get(
                    "no_new_accounts_streak"
                )
                metadata["scroll_reached_bottom"] = progress.get("reached_bottom")
                metadata["scroll_mode"] = progress.get("scroll_mode")
                metadata["scroll_js_metrics"] = progress.get("js_scroll_metrics")
                metadata["scroll_post_metrics"] = progress.get("post_metrics")
        except Exception:
            pass

        return metadata

    def _build_artifact_metadata(self) -> Dict[str, Any]:
        """Build metadata dict for artifact record."""
        return {
            "platform": "instagram",
            "source": "ig_analyze_following_progress",
            "playbook_code": "ig_analyze_following",
            "execution_id": self.trace_id,
            "trace_id": self.trace_id,
            "schema_version": self.schema_version,
            "seed_version": self.seed_version,
            "workspace_id": self.workspace_id,
            "target_username": self.target_username,
            "source_account_handle": self.source_account_handle,
            "source_profile_ref": self.user_data_dir,
        }

    async def upsert_progress(
        self, accounts: List[Dict[str, Any]], progress: Dict[str, Any]
    ) -> None:
        """
        Create or update progress artifact with current state.

        This is the main entry point for progress updates during analysis.
        """
        if not self.artifacts_store or not self.workspace_id or not self.trace_id:
            return

        # Update watchdog state
        try:
            with self._lock:
                self._last_upsert_ts = time.time()
                self._last_accounts = accounts
                self._last_progress = progress
        except Exception:
            pass

        summary = generate_summary(accounts)
        metadata = self._build_metadata(accounts, progress)

        content = {
            "summary": summary,
            "accounts": accounts,
            "metadata": metadata,
            "progress": progress,
        }

        title = f"IG Following Analysis (Progress) - {self.target_username}"
        summary_text = f"Captured {len(accounts)} accounts so far"

        if not self.progress_artifact_id:
            # Check for existing artifact first (enables incremental updates)
            existing_id = self._get_existing_progress_artifact_id()
            if existing_id:
                # Found existing artifact - update it instead of creating new
                self.progress_artifact_id = existing_id
                logger.info(
                    f"[IGFollowingAnalyzer] Reusing existing progress artifact: id={self.progress_artifact_id}"
                )
                try:
                    self._debug_log(
                        f"Updating existing artifact: {self.progress_artifact_id}"
                    )
                    # GUARD: Never overwrite a larger accounts list with a smaller one.
                    # A new run starts with accounts=[] which would destroy
                    # previous successful crawl data if blindly overwritten.
                    if not accounts:
                        existing_art = self.artifacts_store.get_artifact(
                            self.progress_artifact_id
                        )
                        if existing_art:
                            existing_content = existing_art.content or {}
                            existing_accounts = (
                                existing_content.get("accounts", [])
                                if isinstance(existing_content, dict)
                                else []
                            )
                            if existing_accounts:
                                content["accounts"] = existing_accounts
                                self._debug_log(
                                    f"Preserved {len(existing_accounts)} existing accounts "
                                    f"(new run has 0)"
                                )
                    self.artifacts_store.update_artifact(
                        self.progress_artifact_id,
                        title=title,
                        summary=summary_text,
                        content=content,
                        execution_id=self.trace_id,
                        metadata=self._build_artifact_metadata(),
                        updated_at=_utc_now(),
                    )
                    self._debug_log("Update succeeded")
                    return
                except Exception as e:
                    self._debug_log(f"Update failed: {e}")
                    logger.warning(
                        f"[IGFollowingAnalyzer] Failed to update existing artifact, will create new: {e}"
                    )
                    self.progress_artifact_id = None

            # No existing artifact found - create new one
            self.progress_artifact_id = str(uuid.uuid4())
            artifact = Artifact(
                id=self.progress_artifact_id,
                workspace_id=self.workspace_id,
                intent_id=None,
                task_id=None,
                execution_id=self.trace_id,
                thread_id=None,
                playbook_code="ig_analyze_following",
                artifact_type=ArtifactType.DATA,
                title=title,
                summary=summary_text,
                content=content,
                storage_ref=None,
                sync_state=None,
                primary_action_type=PrimaryActionType.PREVIEW,
                metadata=self._build_artifact_metadata(),
                created_at=_utc_now(),
                updated_at=_utc_now(),
            )
            try:
                self._debug_log(f"Creating new artifact: {self.progress_artifact_id}")
                self.artifacts_store.create_artifact(artifact)
                self._debug_log("Create succeeded")
                logger.info(
                    f"[IGFollowingAnalyzer] Progress artifact created: id={self.progress_artifact_id}, accounts={len(accounts)}"
                )
            except Exception as e:
                self._debug_log(f"Create failed: {e}")
                logger.warning(
                    f"[IGFollowingAnalyzer] Failed to create progress artifact: {e}"
                )
                self.progress_artifact_id = None
            return

        # Update existing artifact
        try:
            self.artifacts_store.update_artifact(
                self.progress_artifact_id,
                title=title,
                summary=summary_text,
                content=content,
                execution_id=self.trace_id,
                metadata=self._build_artifact_metadata(),
                updated_at=_utc_now(),
            )
            logger.info(
                f"[IGFollowingAnalyzer] Progress artifact updated: id={self.progress_artifact_id}, accounts={len(accounts)}, stage={progress.get('stage')}"
            )
        except Exception as e:
            logger.warning(
                f"[IGFollowingAnalyzer] Failed to update progress artifact: {e}"
            )

        # Incremental persist: write accounts to ig_accounts_flat during scrolling
        # Uses UPSERT pattern so safe to call multiple times
        try:
            persist_accounts_flat(
                workspace_id=self.workspace_id,
                seed=self.target_username,
                source_account_handle=self.source_account_handle,
                source_profile_ref=self.user_data_dir,
                accounts=accounts,
                analyzed_at=metadata.get("analyzed_at") or "",
                execution_id=self.trace_id,
                trace_id=self.trace_id,
                artifact_id=self.progress_artifact_id,
                schema_version=self.schema_version,
                seed_version=self.seed_version,
                capture_method="following_list",
                run_mode=self.run_mode,
            )
        except Exception as e:
            logger.warning(f"[IGFollowingAnalyzer] Incremental persist failed: {e}")

    def update_artifact_sync(
        self, accounts: List[Dict[str, Any]], progress: Dict[str, Any]
    ) -> None:
        """
        Synchronous version of artifact update (for watchdog thread).
        """
        if not self.artifacts_store or not self.progress_artifact_id:
            return

        summary = generate_summary(accounts if isinstance(accounts, list) else [])
        metadata = self._build_metadata(accounts, progress)

        content = {
            "summary": summary,
            "accounts": accounts,
            "metadata": metadata,
            "progress": progress,
        }

        try:
            self.artifacts_store.update_artifact(
                self.progress_artifact_id,
                title=f"IG Following Analysis (Progress) - {self.target_username}",
                summary=f"Captured {len(accounts) if isinstance(accounts, list) else 0} accounts so far",
                content=content,
                execution_id=self.trace_id,
                metadata=self._build_artifact_metadata(),
                updated_at=_utc_now(),
            )
            with self._lock:
                self._last_upsert_ts = time.time()
        except Exception:
            pass
