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

    def create_pairing_code(self, *, workspace_id: str) -> DevicePairingCode:
        now = time.time()
        self.cleanup_expired(now_epoch=now)
        pairing_code = self._generate_pairing_code()
        pairing = DevicePairingCode(
            workspace_id=workspace_id,
            pairing_code=pairing_code,
            expires_at_epoch=now + DEVICE_PAIRING_CODE_TTL_SECONDS,
            expires_in_seconds=DEVICE_PAIRING_CODE_TTL_SECONDS,
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
        return entry

    def list_active_sessions(self, *, workspace_id: str) -> list[DeviceSessionEntry]:
        self.cleanup_expired()
        return [
            entry
            for entry in self._sessions.values()
            if entry.workspace_id == workspace_id
            and entry.state not in {"revoked", "expired", "closed", "rejected"}
        ]

    def cleanup_expired(self, *, now_epoch: float | None = None) -> int:
        now = time.time() if now_epoch is None else now_epoch
        removed = 0
        expired_pairings = [
            code
            for code, record in self._pairings.items()
            if record.expired(now) and not record.consumed_session_id
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
        return entry

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


__all__ = [
    "DEVICE_PAIRING_CODE_TTL_SECONDS",
    "DEVICE_SESSION_TTL_SECONDS",
    "MAX_ACTIVE_SOURCE_DEVICES_PER_WORKSPACE",
    "DeviceBindingRegistry",
    "DeviceBindingRegistryError",
    "get_device_binding_registry",
]
