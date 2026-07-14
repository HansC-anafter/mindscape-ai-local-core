"""Settings extension candidate filtering and runtime descriptor projection."""

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.models.runtime_environment import RuntimeEnvironment
from backend.app.routes.core.capability_packs_core.installed_routes import (
    _get_runtime_ui_component,
)

from . import manifest_catalog

logger = logging.getLogger(__name__)

_BUILT_IN_RUNTIME_CODES = {
    "local-core",
    "local_core",
    "blender-bridge-mesh",
    "blender_bridge_mesh",
    "blender_bridge",
}


class ExactOwnerDescriptorError(RuntimeError):
    """Raised when an exact owner component descriptor is malformed."""


@dataclass(frozen=True)
class SettingsExtensionCandidate:
    """One settings component selected for condition evaluation."""

    capability_code: str
    component: Dict[str, Any]
    settings_config: Dict[str, Any]
    show_when: Dict[str, Any]
    manifest_file: Optional[str] = None


def _slugify_runtime_code(value: Any) -> Optional[str]:
    text_value = str(value or "").strip().lower()
    if not text_value:
        return None
    normalized = "".join(
        character if character.isalnum() else "_" for character in text_value
    )
    normalized = "_".join(
        segment for segment in normalized.split("_") if segment
    )
    return normalized or None


def get_registered_runtime_codes(db: Session) -> List[str]:
    """Return runtime codes used by conditional settings descriptors."""
    try:
        runtimes = db.query(RuntimeEnvironment).all()
        codes = set(_BUILT_IN_RUNTIME_CODES)
        for runtime in runtimes:
            metadata = runtime.extra_metadata or {}
            for value in (
                runtime.id,
                _slugify_runtime_code(runtime.id),
                runtime.name,
                _slugify_runtime_code(runtime.name),
                metadata.get("runtime_type"),
                _slugify_runtime_code(metadata.get("runtime_type")),
                metadata.get("capability_code"),
                _slugify_runtime_code(metadata.get("capability_code")),
            ):
                if value:
                    codes.add(value)
        return list(codes)
    except Exception as exc:
        logger.warning("Failed to get runtimes from DB: %s", exc)
        return []


def get_registered_service_codes(db: Session) -> List[str]:
    """Return service codes used by conditional settings descriptors."""
    try:
        result = db.execute(
            text("SELECT DISTINCT provider, capability_code FROM tool_registry")
        )
        codes = set()
        for row in result:
            if row.provider:
                codes.add(row.provider)
            if row.capability_code:
                codes.add(row.capability_code)
        return list(codes)
    except Exception as exc:
        logger.warning("Failed to get services from DB: %s", exc)
        return []


def check_show_when(
    show_when: Dict[str, Any],
    registered_runtimes: Sequence[str],
    registered_services: Sequence[str],
) -> bool:
    """Return whether one settings component satisfies its display condition."""
    if not show_when or show_when.get("always"):
        return True
    if runtime_codes := show_when.get("runtime_codes"):
        return any(code in registered_runtimes for code in runtime_codes)
    if service_codes := show_when.get("service_codes"):
        return any(code in registered_services for code in service_codes)
    return True


def _matches_scope(
    settings_config: Dict[str, Any],
    *,
    section: Optional[str],
    workspace_id: Optional[str],
) -> bool:
    if section and settings_config.get("section") != section:
        return False
    requires_workspace_id = bool(settings_config.get("requires_workspace_id"))
    if workspace_id and not requires_workspace_id:
        return False
    if requires_workspace_id and not workspace_id:
        return False
    return True


def _generic_candidates(
    *,
    section: Optional[str],
    workspace_id: Optional[str],
) -> List[SettingsExtensionCandidate]:
    candidates: List[SettingsExtensionCandidate] = []
    for capability_code in manifest_catalog.get_installed_capabilities():
        manifest = manifest_catalog.load_manifest(capability_code)
        if not manifest:
            continue
        components = manifest.get("ui_components", [])
        if not isinstance(components, list):
            logger.warning(
                "Ignoring malformed ui_components for capability %s",
                capability_code,
            )
            continue
        for component in components:
            if not isinstance(component, dict):
                logger.warning(
                    "Ignoring malformed settings component for capability %s",
                    capability_code,
                )
                continue
            settings_config = component.get("settings")
            if not isinstance(settings_config, dict) or not _matches_scope(
                settings_config,
                section=section,
                workspace_id=workspace_id,
            ):
                continue
            show_when = settings_config.get("show_when", {})
            candidates.append(
                SettingsExtensionCandidate(
                    capability_code=capability_code,
                    component=component,
                    settings_config=settings_config,
                    show_when=show_when if isinstance(show_when, dict) else {},
                )
            )
    return candidates


def _exact_owner_candidates(
    *,
    capability_code: str,
    component_code: str,
    section: Optional[str],
    workspace_id: Optional[str],
) -> List[SettingsExtensionCandidate]:
    manifest = manifest_catalog.load_exact_owner_manifest(capability_code)
    if manifest is None:
        return []
    components = manifest.get("ui_components", [])
    if not isinstance(components, list):
        raise ExactOwnerDescriptorError(
            "Exact owner ui_components must be a list"
        )
    matches = [
        component
        for component in components
        if isinstance(component, dict) and component.get("code") == component_code
    ]
    if not matches:
        return []
    if len(matches) != 1:
        raise ExactOwnerDescriptorError(
            "Exact owner component code must be unique"
        )
    component = matches[0]
    settings_config = component.get("settings")
    if not isinstance(settings_config, dict):
        raise ExactOwnerDescriptorError(
            "Exact owner settings descriptor must be an object"
        )
    if not _matches_scope(
        settings_config,
        section=section,
        workspace_id=workspace_id,
    ):
        return []
    show_when = settings_config.get("show_when", {})
    if not isinstance(show_when, dict):
        raise ExactOwnerDescriptorError(
            "Exact owner show_when descriptor must be an object"
        )
    if show_when and show_when.get("always") is not True:
        raise ExactOwnerDescriptorError(
            "Exact owner settings descriptors must be unconditional"
        )
    return [
        SettingsExtensionCandidate(
            capability_code=capability_code,
            component=component,
            settings_config=settings_config,
            show_when=show_when,
            manifest_file=manifest.get("_file_path"),
        )
    ]


def _project_candidate(
    candidate: SettingsExtensionCandidate,
) -> Dict[str, Any]:
    component = candidate.component
    settings_config = candidate.settings_config
    capability_code = candidate.capability_code
    component_code = component.get("code")
    component_path = component.get("path", "")

    if component_path.startswith("ui/components/"):
        installed_path = (
            "components/" + component_path[len("ui/components/") :]
        )
    elif component_path.startswith("ui/"):
        installed_path = "components/" + component_path[len("ui/") :]
    else:
        installed_path = component_path

    import_path = f"@/app/capabilities/{capability_code}/{installed_path}"
    for extension in (".tsx", ".ts", ".jsx", ".js"):
        if import_path.endswith(extension):
            import_path = import_path[: -len(extension)]
            break

    descriptor = {
        "capability_code": capability_code,
        "component_code": component_code,
        "path": component_path,
        "import_path": import_path,
        "export": component.get("export", "default"),
        "section": settings_config.get("section"),
        "title": settings_config.get("title", component_code),
        "description": settings_config.get("description")
        or component.get("description"),
        "order": settings_config.get("order", 100),
        "requires_workspace_id": bool(
            settings_config.get("requires_workspace_id")
        ),
        "display_mode": settings_config.get("display_mode"),
        "show_when": candidate.show_when,
        "props_schema": settings_config.get("props_schema"),
        "legacy_context": component.get("legacy_context"),
    }
    runtime_component = _get_runtime_ui_component(
        capability_code,
        component_code,
        strict=True,
        manifest_file=candidate.manifest_file,
    )
    for field_name in (
        "asset_url",
        "integrity",
        "bytes",
        "runtime",
        "asset_path",
    ):
        if runtime_component.get(field_name) is not None:
            descriptor[field_name] = runtime_component[field_name]
    if runtime_component.get("export"):
        descriptor["export"] = runtime_component["export"]
    return descriptor


def get_settings_extension_descriptors(
    *,
    section: Optional[str],
    workspace_id: Optional[str],
    capability_code: Optional[str],
    component_code: Optional[str],
    db: Session,
) -> List[Dict[str, Any]]:
    """Return generic or exact-owner settings extension descriptors."""
    if capability_code is not None and component_code is not None:
        candidates = _exact_owner_candidates(
            capability_code=capability_code,
            component_code=component_code,
            section=section,
            workspace_id=workspace_id,
        )
    else:
        candidates = _generic_candidates(
            section=section,
            workspace_id=workspace_id,
        )

    needs_runtime_codes = any(
        not candidate.show_when.get("always")
        and candidate.show_when.get("runtime_codes")
        for candidate in candidates
    )
    needs_service_codes = any(
        not candidate.show_when.get("always")
        and not candidate.show_when.get("runtime_codes")
        and candidate.show_when.get("service_codes")
        for candidate in candidates
    )
    registered_runtimes = (
        get_registered_runtime_codes(db) if needs_runtime_codes else []
    )
    registered_services = (
        get_registered_service_codes(db) if needs_service_codes else []
    )

    descriptors = [
        _project_candidate(candidate)
        for candidate in candidates
        if check_show_when(
            candidate.show_when,
            registered_runtimes,
            registered_services,
        )
    ]
    descriptors.sort(key=lambda descriptor: descriptor["order"])
    return descriptors
