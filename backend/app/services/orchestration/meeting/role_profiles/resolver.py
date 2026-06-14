"""Resolve one pack-scoped meeting role profile for a meeting context."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .manifest_registry import MeetingRoleProfileManifestRegistry


@dataclass(frozen=True)
class SelectedMeetingRoleProfile:
    """Selected manifest profile plus deterministic selection context."""

    pack_id: str
    code: str
    display_name: str
    match: Dict[str, Any]
    slot_overrides: Dict[str, Any]
    planner_lane: Dict[str, Any]
    manifest_path: str
    selection_context: Dict[str, Any] = field(default_factory=dict)

    @property
    def meeting_lane_code(self) -> str:
        lane_code = str(self.planner_lane.get("code") or "").strip()
        return lane_code or self.code

    def as_metadata(self) -> Dict[str, Any]:
        return {
            "active_capability_code": self.pack_id,
            "meeting_role_profile_code": self.code,
            "meeting_lane_code": self.meeting_lane_code,
            "meeting_role_profile_display_name": self.display_name,
            "meeting_role_profile_manifest_path": self.manifest_path,
            "pack_role_names": {
                str(slot): str(overrides.get("pack_role_name"))
                for slot, overrides in self.slot_overrides.items()
                if isinstance(overrides, dict)
                and str(overrides.get("pack_role_name") or "").strip()
            },
        }


class MeetingRoleProfileResolver:
    """Select exactly one active-pack role profile from declarative manifest rules."""

    def __init__(
        self,
        registry: Optional[MeetingRoleProfileManifestRegistry] = None,
    ) -> None:
        self.registry = registry or MeetingRoleProfileManifestRegistry()

    def resolve(
        self,
        *,
        session_metadata: Optional[Dict[str, Any]] = None,
        request_contract: Optional[Any] = None,
    ) -> Optional[SelectedMeetingRoleProfile]:
        metadata = session_metadata if isinstance(session_metadata, dict) else {}
        pack_id = self.registry.active_pack_id(metadata)
        if not pack_id:
            return None

        profiles = self.registry.load_profiles_for_pack(pack_id)
        if not profiles:
            return None

        context = self._selection_context(
            session_metadata=metadata,
            request_contract=request_contract,
        )
        requested_code = str(context.get("meeting_role_profile_code") or "").strip()
        if requested_code:
            for profile in profiles:
                if str(profile.get("code") or "").strip() == requested_code:
                    return self._selected(profile, context)
            return None

        for profile in profiles:
            if self._matches(profile, context):
                return self._selected(profile, context)
        return None

    def _selected(
        self,
        profile: Dict[str, Any],
        context: Dict[str, Any],
    ) -> SelectedMeetingRoleProfile:
        return SelectedMeetingRoleProfile(
            pack_id=str(profile.get("pack_id") or ""),
            code=str(profile.get("code") or ""),
            display_name=str(profile.get("display_name") or profile.get("code") or ""),
            match=dict(profile.get("match") or {}),
            slot_overrides=dict(profile.get("slot_overrides") or {}),
            planner_lane=dict(profile.get("planner_lane") or {}),
            manifest_path=str(profile.get("manifest_path") or ""),
            selection_context=dict(context),
        )

    def _matches(self, profile: Dict[str, Any], context: Dict[str, Any]) -> bool:
        match = dict(profile.get("match") or {})
        if not match:
            return False

        playbook_codes = self._clean_list(match.get("playbook_codes"))
        if playbook_codes and context.get("playbook_code") not in playbook_codes:
            return False

        expected_outputs = self._clean_list(match.get("expected_outputs"))
        if expected_outputs and not set(expected_outputs).intersection(
            self._clean_list(context.get("expected_outputs"))
        ):
            return False

        context_object_kinds = self._clean_list(match.get("context_object_kinds"))
        if context_object_kinds and not set(context_object_kinds).intersection(
            self._clean_list(context.get("context_object_kinds"))
        ):
            return False

        return True

    def _selection_context(
        self,
        *,
        session_metadata: Dict[str, Any],
        request_contract: Optional[Any],
    ) -> Dict[str, Any]:
        contract = self._as_dict(request_contract)
        requested_action = self._as_dict(session_metadata.get("requested_action"))
        role_request = self._as_dict(
            session_metadata.get("meeting_role_profile_request")
            or session_metadata.get("planner_lane_request")
        )

        playbook_code = (
            role_request.get("playbook_code")
            or requested_action.get("playbook_code")
            or self._first_playbook_code(contract)
        )
        context_objects = role_request.get("context_objects")
        if context_objects is None:
            context_objects = session_metadata.get("context_objects")

        context_object_kinds = self._clean_list(role_request.get("context_object_kinds"))
        context_object_kinds.extend(self._context_object_kinds(context_objects))

        return {
            "meeting_role_profile_code": (
                role_request.get("meeting_role_profile_code")
                or session_metadata.get("meeting_role_profile_code")
            ),
            "playbook_code": str(playbook_code or "").strip(),
            "expected_outputs": self._clean_list(
                role_request.get("expected_outputs")
                or session_metadata.get("expected_outputs")
            ),
            "context_object_kinds": sorted(set(context_object_kinds)),
            "context": self._as_dict(
                role_request.get("context") or session_metadata.get("context")
            ),
        }

    def _first_playbook_code(self, contract: Dict[str, Any]) -> str:
        requests = contract.get("playbook_requests")
        if not isinstance(requests, list):
            return ""
        for item in requests:
            payload = self._as_dict(item)
            value = str(payload.get("playbook_code") or "").strip()
            if value:
                return value
        return ""

    def _context_object_kinds(self, context_objects: Any) -> List[str]:
        if not isinstance(context_objects, list):
            return []
        kinds: List[str] = []
        for item in context_objects:
            payload = self._as_dict(item)
            kind = str(payload.get("kind") or payload.get("object_kind") or "").strip()
            if kind:
                kinds.append(kind)
        return kinds

    def _as_dict(self, value: Any) -> Dict[str, Any]:
        if value is None:
            return {}
        if isinstance(value, dict):
            return value
        if hasattr(value, "model_dump"):
            dumped = value.model_dump()
            return dumped if isinstance(dumped, dict) else {}
        return {}

    def _clean_list(self, value: Any) -> List[str]:
        if isinstance(value, str):
            values = [value]
        elif isinstance(value, list):
            values = value
        else:
            values = []
        return [str(item).strip() for item in values if str(item or "").strip()]
