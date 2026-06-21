import re

from .models import ValidationError


AOL_LEVELS = {
    "AOL-0": 0,
    "AOL-1": 1,
    "AOL-2": 2,
    "AOL-3": 3,
    "AOL-4": 4,
    "AOL-5": 5,
}
AOL_SELECTOR_FAMILIES = {
    "object_root",
    "dom_anchor",
    "image_region",
    "media_time_range",
    "storyboard_scene",
    "storyboard_slot",
    "timeline_clip",
    "pack_local_path",
    "graph_node",
}
AOL_ROLES = {
    "source",
    "target",
    "character",
    "constraint",
    "output",
    "meeting",
    "session",
    "node",
}
AOL_WRITE_MODES = {
    "proposal_only",
    "staged",
    "canonical_with_review",
    "owner_canonical_lane",
    "recommendation_only",
}
AOL_BACKEND_PATTERN = re.compile(
    r"^(app\.)?capabilities\.[a-z0-9_]+(?:\.[A-Za-z0-9_]+)+:[A-Za-z_][A-Za-z0-9_]*$"
)
AOL_OBJECT_KIND_PATTERN = re.compile(r"^[a-z0-9_]+$")
AOL_FIELD_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
PACK_CODE_PATTERN = re.compile(r"^[a-z0-9_]+$")
CONTRACT_ID_PATTERN = re.compile(r"^[a-z0-9_]+$")
CONTRACT_MODULE_PATTERN = re.compile(
    r"^(app\.)?capabilities\.[a-z0-9_]+\.schema(?:\.[A-Za-z0-9_]+)+$"
)
CONTRACT_VERSION_PATTERN = re.compile(
    r"^[0-9]+\.[0-9]+(?:\.[0-9]+)?(?:[-+][A-Za-z0-9_.-]+)?$"
)
CONTRACT_RANGE_PATTERN = re.compile(r"^[\^~<>=!, 0-9A-Za-z_.-]+$")
LEGACY_ALIAS_PATTERN = re.compile(
    r"^(shared|backend\.shared)\.schemas\.[A-Za-z0-9_]+$"
)
MIME_TYPE_PATTERN = re.compile(
    r"^[A-Za-z0-9!#$&^_.+-]+/[A-Za-z0-9!#$&^_.+-]+(?:\+[A-Za-z0-9!#$&^_.+-]+)?$"
)
MEETING_ARTIFACT_BACKEND_PATTERN = re.compile(
    r"^capabilities\.[a-z0-9_]+\.[A-Za-z0-9_\.]+:[A-Za-z_][A-Za-z0-9_]*$"
)
RUNTIME_LOCK_TOKEN_PATTERN = re.compile(r"{([^{}]+)}")
RUNTIME_READ_PATH_ENDPOINT_CLASSES = {
    "ui_list",
    "summary",
    "facet",
    "sidebar",
    "status",
}
RUNTIME_READ_PATH_DB_MODELS = {
    "projection",
    "summary_table",
    "indexed_compact_query",
    "external_search_index",
}
RUNTIME_READ_PATH_REQUIRED_FIELDS = (
    "id",
    "endpoint_class",
    "method",
    "path",
    "request_query",
    "purpose",
    "max_ttfb_ms",
    "max_total_ms",
    "max_response_bytes",
    "db_read_model",
    "forbidden_sources",
    "expected_status",
)
RUNTIME_READ_PATH_DENY_LIST_REQUIRED_CLASSES = {
    "ui_list",
    "summary",
    "facet",
    "sidebar",
}


def _aol_error(
    capability_code: str,
    field: str,
    message: str,
) -> ValidationError:
    return ValidationError(
        capability=capability_code,
        field=field,
        message=message,
        severity="error",
    )


def _manifest_error(
    capability_code: str,
    field: str,
    message: str,
) -> ValidationError:
    return ValidationError(
        capability=capability_code,
        field=field,
        message=message,
        severity="error",
    )


def _manifest_warning(
    capability_code: str,
    field: str,
    message: str,
) -> ValidationError:
    return ValidationError(
        capability=capability_code,
        field=field,
        message=message,
        severity="warning",
    )
