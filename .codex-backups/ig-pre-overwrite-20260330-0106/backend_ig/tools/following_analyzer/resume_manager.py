"""
Resume management for Instagram following analyzer.

This module handles resuming interrupted analyses and merging
accounts from multiple artifacts.
"""

import logging
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


def normalize_accounts(accounts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Normalize and deduplicate accounts list.

    Ensures each account has username, account_link, and external_url fields.
    """
    out: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for a in accounts or []:
        if not isinstance(a, dict):
            continue
        u = (a.get("username") or "").strip()
        if not u or u in seen:
            continue
        seen.add(u)
        # Ensure account_link exists
        link = a.get("account_link") or a.get("external_url")
        if not link:
            link = f"https://www.instagram.com/{u}/"
        a = dict(a)
        a["username"] = u
        a["account_link"] = link
        a["external_url"] = a.get("external_url") or link
        out.append(a)
    return out


def should_skip_scrolling_from_resume(accounts: List[Dict[str, Any]]) -> bool:
    """
    Determine if scrolling can be skipped based on resume data.

    Resume is now EXPLICIT (run_mode='visit'). No hidden thresholds.
    Only resume if we have a meaningful list.
    """
    if not accounts:
        return False
    return len(accounts) >= 1


def is_account_page_done(a: Dict[str, Any]) -> bool:
    """
    Check if an account page has been successfully analyzed.

    Consider done if we have page_analyzed_at and no error,
    OR we have BOTH bio AND key stats (follower/following/post count).
    """
    if not isinstance(a, dict):
        return False
    if a.get("page_analysis_error"):
        return False
    if a.get("page_analyzed_at"):
        return True

    # Must have BOTH bio AND stats to be considered done
    has_bio = bool(a.get("bio"))
    has_stats = bool(
        a.get("follower_count_text")
        or a.get("following_count_text")
        or a.get("post_count_text")
        or a.get("follower_count")
        or a.get("following_count")
        or a.get("post_count")
    )
    return has_bio and has_stats


class ResumeManager:
    """
    Manages resume and account merging for following analyzer.
    """

    def __init__(
        self,
        artifacts_store,
        workspace_id: str,
        target_username: str,
        user_data_dir: Optional[str],
        run_mode: Optional[str],
    ):
        self.artifacts_store = artifacts_store
        self.workspace_id = workspace_id
        self.target_username = target_username
        self.user_data_dir = user_data_dir
        self.run_mode = run_mode

    def load_resume_accounts(self) -> Optional[Dict[str, Any]]:
        """
        Resume visiting_pages from the latest progress artifact in the same workspace/target/profile.

        Selection rules:
        - playbook_code == ig_analyze_following
        - artifact.metadata.source == ig_analyze_following_progress
        - content.metadata.target_username matches
        - content.metadata.source_profile_ref matches current user_data_dir
        """
        if not self.artifacts_store:
            return None
        try:
            # Resume is opt-in: only when run_mode explicitly requests it.
            # Default behavior must not reuse old lists.
            if (self.run_mode or "").strip().lower() != "visit":
                return None
        except Exception:
            return None

        try:
            candidates = self.artifacts_store.list_artifacts_by_playbook(
                self.workspace_id, "ig_analyze_following"
            )
        except Exception:
            candidates = []

        best = None
        best_score = (-1, 0.0)  # (completeness_score, updated_ts)
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
                # Prefer artifacts that represent a full list (accounts >= expected_following_count) when known.
                accounts0 = c.get("accounts") if isinstance(c, dict) else None
                accounts_len = len(accounts0) if isinstance(accounts0, list) else 0
                expected0 = cm.get("expected_following_count")
                try:
                    expected_i = int(expected0) if expected0 is not None else None
                except Exception:
                    expected_i = None
                completeness = 0
                if expected_i and expected_i > 0 and accounts_len >= expected_i:
                    completeness = 2
                elif accounts_len > 0:
                    completeness = 1
                # prefer latest updated_at
                ts = 0.0
                try:
                    ts = art.updated_at.timestamp()
                except Exception:
                    try:
                        ts = art.created_at.timestamp()
                    except Exception:
                        ts = 0.0
                score = (completeness, ts)
                if score > best_score:
                    best_score = score
                    best = art
            except Exception:
                continue

        if not best:
            logger.info(
                f"[ResumeManager] No matching artifact found, trying ig_accounts_flat fallback"
            )
            return self._load_accounts_from_db_fallback()

        try:
            c = best.content or {}
            accounts = c.get("accounts") if isinstance(c, dict) else None
            meta = c.get("metadata") if isinstance(c, dict) else None
            if not isinstance(accounts, list) or not isinstance(meta, dict):
                logger.info(
                    f"[ResumeManager] Artifact {best.id} has invalid structure, trying ig_accounts_flat fallback"
                )
                return self._load_accounts_from_db_fallback()
            accounts_norm = normalize_accounts(accounts)
            # If artifact has empty accounts list, try database fallback
            if not accounts_norm:
                logger.info(
                    f"[ResumeManager] Artifact {best.id} has empty accounts list, trying ig_accounts_flat fallback"
                )
                return self._load_accounts_from_db_fallback()
            if not should_skip_scrolling_from_resume(accounts_norm):
                return None
            return {
                "accounts": accounts_norm,
                "meta": meta,
                "artifact_id": best.id,
                "updated_at": (
                    best.updated_at.isoformat()
                    if getattr(best, "updated_at", None)
                    else None
                ),
            }
        except Exception:
            return self._load_accounts_from_db_fallback()

    def _load_accounts_from_db_fallback(self) -> Optional[Dict[str, Any]]:
        """
        Fallback to load accounts from ig_accounts_flat when artifact is empty.
        """
        logger.info(
            f"[ResumeManager] _load_accounts_from_db_fallback called with "
            f"workspace_id={self.workspace_id}, target_username={self.target_username}, "
            f"user_data_dir={self.user_data_dir}"
        )
        try:
            from .persistence import load_accounts_from_db

            accounts = load_accounts_from_db(
                workspace_id=self.workspace_id,
                seed=self.target_username,
                source_profile_ref=self.user_data_dir,
                include_unverified=True,
            )
            if not accounts:
                logger.info(
                    f"[ResumeManager] ig_accounts_flat fallback returned no accounts"
                )
                return None

            accounts_norm = normalize_accounts(accounts)
            if not accounts_norm:
                logger.info(
                    f"[ResumeManager] ig_accounts_flat fallback returned no valid accounts after normalization"
                )
                return None

            if not should_skip_scrolling_from_resume(accounts_norm):
                logger.info(
                    f"[ResumeManager] ig_accounts_flat accounts ({len(accounts_norm)}) not sufficient to skip scrolling"
                )
                return None

            logger.info(
                f"[ResumeManager] Successfully loaded {len(accounts_norm)} accounts from ig_accounts_flat fallback"
            )
            return {
                "accounts": accounts_norm,
                "meta": {
                    "target_username": self.target_username,
                    "source_profile_ref": self.user_data_dir,
                    "source": "ig_accounts_flat_fallback",
                },
                "artifact_id": None,
                "updated_at": None,
            }
        except Exception as e:
            logger.warning(f"[ResumeManager] ig_accounts_flat fallback failed: {e}")
            return None

    def load_saved_accounts_union(
        self, expected_following_count: Optional[int]
    ) -> Optional[Dict[str, Any]]:
        """
        Build a merged (deduplicated) accounts list from existing artifacts in the same workspace/target/profile.

        This is used to optimize the "full -> visit_pages" transition:
        when persisted accounts exist, return the best available deduplicated list
        for the same workspace/target/profile so visiting_pages can cover as many
        accounts as possible even if the current scrolling session is incomplete.
        """
        if not self.artifacts_store:
            return None
        if not expected_following_count:
            return None
        try:
            expected_i = int(expected_following_count)
            if expected_i <= 0:
                return None
        except Exception:
            return None

        try:
            candidates = self.artifacts_store.list_artifacts_by_playbook(
                self.workspace_id, "ig_analyze_following"
            )
        except Exception:
            candidates = []

        # Merge newest-first so newer fields win.
        def _ts(a: Any) -> float:
            try:
                return a.updated_at.timestamp()
            except Exception:
                try:
                    return a.created_at.timestamp()
                except Exception:
                    return 0.0

        merged: Dict[str, Dict[str, Any]] = {}
        used_artifact_ids: List[str] = []
        for art in sorted(candidates or [], key=_ts, reverse=True):
            try:
                m = art.metadata or {}
                # Only merge artifacts that are part of the IG following analyzer pipeline.
                if (m.get("source") or "") not in (
                    "ig_analyze_following_progress",
                    "ig_analyze_following",
                ):
                    continue
                c = art.content or {}
                cm = (c.get("metadata") or {}) if isinstance(c, dict) else {}
                if (cm.get("target_username") or "") != self.target_username:
                    continue
                # Normalize source_profile_ref comparison (ignore trailing slashes)
                stored_ref = (cm.get("source_profile_ref") or "").rstrip("/")
                current_ref = (self.user_data_dir or "").rstrip("/")
                if stored_ref != current_ref:
                    continue
                accounts0 = c.get("accounts") if isinstance(c, dict) else None
                if not isinstance(accounts0, list) or not accounts0:
                    continue
                used_artifact_ids.append(str(getattr(art, "id", "") or ""))

                for a0 in accounts0:
                    if not isinstance(a0, dict):
                        continue
                    u = (
                        (a0.get("username") or a0.get("handle") or "")
                        .strip()
                        .lstrip("@")
                    )
                    if not u:
                        continue
                    prev = merged.get(u)
                    if not prev:
                        merged[u] = dict(a0)
                        continue
                    # Shallow-merge: keep newer value, but don't lose existing keys.
                    nxt = dict(prev)
                    for k, v in a0.items():
                        if v is None:
                            continue
                        if k not in nxt or nxt.get(k) in (None, "", [], {}):
                            nxt[k] = v
                        else:
                            # Prefer non-empty strings over empty strings.
                            if (
                                isinstance(v, str)
                                and v
                                and isinstance(nxt.get(k), str)
                                and not nxt.get(k)
                            ):
                                nxt[k] = v
                    merged[u] = nxt
            except Exception:
                continue

        if len(merged) < expected_i:
            # Fallback: try loading from ig_accounts_flat if artifacts are incomplete
            try:
                from .persistence import load_accounts_from_db

                db_accounts = load_accounts_from_db(
                    workspace_id=self.workspace_id,
                    seed=self.target_username,
                    source_profile_ref=self.user_data_dir,
                    include_unverified=True,
                )
                if db_accounts and len(db_accounts) > len(merged):
                    logger.info(
                        f"[ResumeManager] load_saved_accounts_union fallback: loaded {len(db_accounts)} accounts from ig_accounts_flat"
                    )
                    try:
                        accounts_norm = normalize_accounts(db_accounts)
                    except Exception:
                        accounts_norm = db_accounts
                    return {
                        "accounts": accounts_norm,
                        "dedup_total": len(db_accounts),
                        "expected_following_count": expected_i,
                        "artifact_ids": [],
                        "source": "ig_accounts_flat_fallback",
                    }
            except Exception as e:
                logger.warning(
                    f"[ResumeManager] load_saved_accounts_union fallback failed: {e}"
                )
            if not merged:
                return None

        try:
            accounts_norm = normalize_accounts(list(merged.values()))
        except Exception:
            accounts_norm = list(merged.values())

        return {
            "accounts": accounts_norm,
            "dedup_total": len(merged),
            "expected_following_count": expected_i,
            "artifact_ids": [x for x in used_artifact_ids if x],
        }


# Legacy aliases for backward compatibility
_normalize_accounts = normalize_accounts
_should_skip_scrolling_from_resume = should_skip_scrolling_from_resume
_is_account_page_done = is_account_page_done
