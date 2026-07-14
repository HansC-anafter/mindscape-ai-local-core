"""In-memory registry for workspace-scoped device binding sessions."""

from __future__ import annotations

import secrets
import string
import time
from dataclasses import dataclass, field
from typing import Any

from backend.app.models.device_binding import (
    DeviceCapabilityDeclaration,
    DevicePairingCode,
    DeviceSessionEntry,
)


DEVICE_PAIRING_CODE_TTL_SECONDS = 120
MAX_DEVICE_PAIRING_CODE_TTL_SECONDS = 600
DEVICE_SESSION_TTL_SECONDS = 60
MAX_ACTIVE_SOURCE_DEVICES_PER_WORKSPACE = 3
_PAIRING_ALPHABET = string.ascii_uppercase + string.digits


class DeviceBindingRegistryError(Exception):
    """Registry-level device binding error."""

    def __init__(
        self,
        *,
        reason: str,
        message: str,
        status_code: int = 400,
        close_code: int = 4400,
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.message = message
        self.status_code = status_code
        self.close_code = close_code


@dataclass
class _PairingRecord:
    pairing: DevicePairingCode
    observer_websockets: list[Any] = field(default_factory=list)
    consumed_session_id: str | None = None

    def expired(self, now_epoch: float) -> bool:
        return now_epoch >= self.pairing.expires_at_epoch


class DeviceBindingRegistry:
    """Process-local pairing and active source session registry."""

    def __init__(self) -> None:
        self._pairings: dict[str, _PairingRecord] = {}
        self._sessions: dict[str, DeviceSessionEntry] = {}
        self._workspace_observers: dict[str, list[Any]] = {}

    def create_pairing_code(
        self,
        *,
        workspace_id: str,
        ttl_seconds: int | None = None,
    ) -> DevicePairingCode:
        now = time.time()
        self.cleanup_expired(now_epoch=now)
        effective_ttl = _normalize_pairing_ttl_seconds(ttl_seconds)
        pairing_code = self._generate_pairing_code()
        pairing = DevicePairingCode(
            workspace_id=workspace_id,
            pairing_code=pairing_code,
            expires_at_epoch=now + effective_ttl,
            expires_in_seconds=effective_ttl,
            device_link_path=f"/device-link/{pairing_code}",
        )
        self._pairings[pairing_code] = _PairingRecord(pairing=pairing)
        return pairing

    def attach_workspace_observer(
        self,
        *,
        workspace_id: str,
        pairing_code: str,
        websocket: Any,
    ) -> DevicePairingCode:
        record = self._require_pairing(
            workspace_id=workspace_id,
            pairing_code=pairing_code,
            now_epoch=time.time(),
        )
        if websocket not in record.observer_websockets:
            record.observer_websockets.append(websocket)
        return record.pairing

    def detach_workspace_observer(self, *, pairing_code: str, websocket: Any) -> None:
        record = self._pairings.get(pairing_code)
        if record is None:
            return
        record.observer_websockets = [
            observer for observer in record.observer_websockets if observer is not websocket
        ]

    def workspace_observers(self, *, pairing_code: str) -> list[Any]:
        record = self._pairings.get(pairing_code)
        if record is None:
            return []
        return list(record.observer_websockets)

    def attach_workspace_session_observer(
        self,
        *,
        workspace_id: str,
        websocket: Any,
    ) -> None:
        observers = self._workspace_observers.setdefault(workspace_id, [])
        if websocket not in observers:
            observers.append(websocket)

    def detach_workspace_session_observer(
        self,
        *,
        workspace_id: str,
        websocket: Any,
    ) -> None:
        observers = self._workspace_observers.get(workspace_id)
        if observers is None:
            return
        remaining = [observer for observer in observers if observer is not websocket]
        if remaining:
            self._workspace_observers[workspace_id] = remaining
            return
        self._workspace_observers.pop(workspace_id, None)

    def workspace_session_observers(self, *, workspace_id: str) -> list[Any]:
        return list(self._workspace_observers.get(workspace_id, []))

    def connect_source_device(
        self,
        *,
        workspace_id: str,
        pairing_code: str,
        declaration: DeviceCapabilityDeclaration,
        websocket: Any,
    ) -> DeviceSessionEntry:
        now = time.time()
        self.cleanup_expired(now_epoch=now)
        record = self._require_pairing(
            workspace_id=workspace_id,
            pairing_code=pairing_code,
            now_epoch=now,
        )
        if record.consumed_session_id:
            raise DeviceBindingRegistryError(
                reason="duplicate_pairing_code",
                message="This pairing code is already bound to a source device.",
                status_code=409,
                close_code=4409,
            )
        active_count = len(self.list_active_sessions(workspace_id=workspace_id))
        if active_count >= MAX_ACTIVE_SOURCE_DEVICES_PER_WORKSPACE:
            raise DeviceBindingRegistryError(
                reason="active_source_limit_reached",
                message="This workspace already has the maximum active source devices.",
                status_code=409,
                close_code=4409,
            )
        session_id = self._generate_session_id()
        entry = DeviceSessionEntry(
            session_id=session_id,
            workspace_id=workspace_id,
            pairing_code=pairing_code,
            device_id=declaration.device_id or self._generate_device_id(),
            display_name=declaration.display_name,
            source_types=declaration.source_types,
            metadata=dict(declaration.metadata),
            state="paired",
            created_at_epoch=now,
            updated_at_epoch=now,
            expires_at_epoch=now + DEVICE_SESSION_TTL_SECONDS,
            websocket=websocket,
        )
        self._sessions[session_id] = entry
        record.consumed_session_id = session_id
        return entry

    def refresh_session(self, *, session_id: str) -> DeviceSessionEntry:
        now = time.time()
        entry = self._sessions.get(session_id)
        if entry is None:
            raise DeviceBindingRegistryError(
                reason="unknown_session",
                message="No active device session exists for this session_id.",
                status_code=404,
                close_code=4404,
            )
        if entry.expires_at_epoch <= now:
            self._expire_session(entry)
            raise DeviceBindingRegistryError(
                reason="session_expired",
                message="The device session expired.",
                status_code=410,
                close_code=4408,
            )
        entry.state = "active"
        entry.updated_at_epoch = now
        entry.expires_at_epoch = now + DEVICE_SESSION_TTL_SECONDS
        self._sessions[session_id] = entry
        return entry

    def revoke_session(
        self,
        *,
        workspace_id: str,
        session_id: str,
        reason: str = "revoked_by_workspace",
    ) -> DeviceSessionEntry:
        entry = self._sessions.get(session_id)
        if entry is None or entry.workspace_id != workspace_id:
            raise DeviceBindingRegistryError(
                reason="unknown_session",
                message="No active device session exists for this workspace.",
                status_code=404,
                close_code=4404,
            )
        entry.state = "revoked"
        entry.terminal_reason = reason
        entry.updated_at_epoch = time.time()
        self._sessions.pop(session_id, None)
        self._release_pairing_session(
            pairing_code=entry.pairing_code,
            session_id=entry.session_id,
        )
        return entry

    def close_session(
        self,
        *,
        session_id: str,
        reason: str = "socket_closed",
    ) -> DeviceSessionEntry | None:
        entry = self._sessions.pop(session_id, None)
        if entry is None:
            return None
        entry.state = "closed"
        entry.terminal_reason = reason
        entry.updated_at_epoch = time.time()
        self._release_pairing_session(
            pairing_code=entry.pairing_code,
            session_id=entry.session_id,
        )
        return entry

    def list_active_sessions(self, *, workspace_id: str) -> list[DeviceSessionEntry]:
        self.cleanup_expired()
        return [
            entry
            for entry in self._sessions.values()
            if entry.workspace_id == workspace_id
            and entry.state not in {"revoked", "expired", "closed", "rejected"}
        ]

    def get_active_session(
        self,
        *,
        workspace_id: str,
        session_id: str,
    ) -> DeviceSessionEntry | None:
        self.cleanup_expired()
        entry = self._sessions.get(session_id)
        if entry is None or entry.workspace_id != workspace_id:
            return None
        if entry.state in {"revoked", "expired", "closed", "rejected"}:
            return None
        return entry

    def attach_live_media_session(
        self,
        *,
        workspace_id: str,
        session_id: str,
        media_session_id: str,
        media_session_state: str,
        media_session_expires_at_epoch: float,
    ) -> DeviceSessionEntry:
        entry = self.get_active_session(
            workspace_id=workspace_id,
            session_id=session_id,
        )
        if entry is None:
            raise DeviceBindingRegistryError(
                reason="unknown_session",
                message="No active device session exists for this workspace.",
                status_code=404,
                close_code=4404,
            )
        if entry.media_session_id and entry.media_session_id != media_session_id:
            raise DeviceBindingRegistryError(
                reason="device_media_session_conflict",
                message="This device already owns another active media session.",
                status_code=409,
                close_code=4409,
            )
        entry.media_session_id = media_session_id
        entry.media_session_state = media_session_state
        entry.media_session_expires_at_epoch = media_session_expires_at_epoch
        entry.updated_at_epoch = time.time()
        self._sessions[session_id] = entry
        return entry

    def detach_live_media_session(
        self,
        *,
        workspace_id: str,
        session_id: str,
        media_session_id: str,
    ) -> DeviceSessionEntry:
        entry = self.get_active_session(
            workspace_id=workspace_id,
            session_id=session_id,
        )
        if entry is None:
            raise DeviceBindingRegistryError(
                reason="unknown_session",
                message="No active device session exists for this workspace.",
                status_code=404,
                close_code=4404,
            )
        if entry.media_session_id != media_session_id:
            raise DeviceBindingRegistryError(
                reason="device_media_session_mismatch",
                message="The media session does not belong to this device session.",
                status_code=409,
                close_code=4409,
            )
        entry.media_session_id = None
        entry.media_session_state = "stopped"
        entry.media_session_expires_at_epoch = None
        entry.updated_at_epoch = time.time()
        self._sessions[session_id] = entry
        return entry

    def cleanup_expired(self, *, now_epoch: float | None = None) -> int:
        now = time.time() if now_epoch is None else now_epoch
        removed = 0
        expired_pairings = [
            code
            for code, record in self._pairings.items()
            if record.expired(now)
            and (
                not record.consumed_session_id
                or record.consumed_session_id not in self._sessions
            )
        ]
        for code in expired_pairings:
            self._pairings.pop(code, None)
            removed += 1

        expired_sessions = [
            entry for entry in self._sessions.values() if entry.expires_at_epoch <= now
        ]
        for entry in expired_sessions:
            self._expire_session(entry)
            removed += 1
        return removed

    def active_count(self, *, workspace_id: str | None = None) -> int:
        self.cleanup_expired()
        if workspace_id is None:
            return len(self._sessions)
        return len(self.list_active_sessions(workspace_id=workspace_id))

    def _require_pairing(
        self,
        *,
        workspace_id: str,
        pairing_code: str,
        now_epoch: float,
    ) -> _PairingRecord:
        record = self._pairings.get(pairing_code)
        if record is None:
            raise DeviceBindingRegistryError(
                reason="unknown_pairing_code",
                message="No active pairing code exists for this workspace.",
                status_code=404,
                close_code=4404,
            )
        if record.pairing.workspace_id != workspace_id:
            raise DeviceBindingRegistryError(
                reason="workspace_mismatch",
                message="The pairing code does not belong to this workspace.",
                status_code=403,
                close_code=4403,
            )
        if record.expired(now_epoch):
            self._pairings.pop(pairing_code, None)
            raise DeviceBindingRegistryError(
                reason="pairing_code_expired",
                message="The pairing code expired.",
                status_code=410,
                close_code=4408,
            )
        return record

    def _expire_session(self, entry: DeviceSessionEntry) -> DeviceSessionEntry:
        entry.state = "expired"
        entry.terminal_reason = "session_expired"
        entry.updated_at_epoch = time.time()
        self._sessions.pop(entry.session_id, None)
        self._release_pairing_session(
            pairing_code=entry.pairing_code,
            session_id=entry.session_id,
        )
        return entry

    def _release_pairing_session(self, *, pairing_code: str, session_id: str) -> None:
        record = self._pairings.get(pairing_code)
        if record is None:
            return
        if record.consumed_session_id == session_id:
            record.consumed_session_id = None

    def _generate_pairing_code(self) -> str:
        while True:
            code = "".join(secrets.choice(_PAIRING_ALPHABET) for _ in range(8))
            if code not in self._pairings:
                return code

    @staticmethod
    def _generate_session_id() -> str:
        return f"device_session_{secrets.token_urlsafe(12)}"

    @staticmethod
    def _generate_device_id() -> str:
        return f"device_{secrets.token_urlsafe(8)}"


_registry = DeviceBindingRegistry()


def get_device_binding_registry() -> DeviceBindingRegistry:
    return _registry


def _normalize_pairing_ttl_seconds(ttl_seconds: int | None) -> int:
    if ttl_seconds is None:
        return DEVICE_PAIRING_CODE_TTL_SECONDS
    return max(1, min(int(ttl_seconds), MAX_DEVICE_PAIRING_CODE_TTL_SECONDS))


__all__ = [
    "DEVICE_PAIRING_CODE_TTL_SECONDS",
    "DEVICE_SESSION_TTL_SECONDS",
    "MAX_DEVICE_PAIRING_CODE_TTL_SECONDS",
    "MAX_ACTIVE_SOURCE_DEVICES_PER_WORKSPACE",
    "DeviceBindingRegistry",
    "DeviceBindingRegistryError",
    "get_device_binding_registry",
]
