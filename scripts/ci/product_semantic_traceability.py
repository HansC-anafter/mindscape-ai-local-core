"""Shared traceability checks for product semantic validators."""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath


PREFLIGHT_SECTION_RE = re.compile(
    r"product\s+semantic\s+panoramic\s+preflight",
    re.IGNORECASE,
)
PREFLIGHT_REQUIRED_FIELDS = (
    (
        "scope-class",
        re.compile(r"^\s*[-*]?\s*`?scope[-\s]class`?\s*:", re.IGNORECASE | re.MULTILINE),
    ),
    (
        "protected-behavior",
        re.compile(
            r"^\s*[-*]?\s*`?protected[-\s]behavior`?\s*:",
            re.IGNORECASE | re.MULTILINE,
        ),
    ),
    (
        "source-of-truth",
        re.compile(
            r"^\s*[-*]?\s*`?source[-\s]of[-\s]truth`?\s*:",
            re.IGNORECASE | re.MULTILINE,
        ),
    ),
    (
        "registry-scan",
        re.compile(
            r"^\s*[-*]?\s*`?registry[-\s]scan`?\s*:",
            re.IGNORECASE | re.MULTILINE,
        ),
    ),
    (
        "impacted-psc",
        re.compile(r"^\s*[-*]?\s*`?impacted[-\s]psc`?\s*:", re.IGNORECASE | re.MULTILINE),
    ),
    (
        "contract-index-read",
        re.compile(
            r"^\s*[-*]?\s*`?contract[-\s]index[-\s]read`?\s*:",
            re.IGNORECASE | re.MULTILINE,
        ),
    ),
    (
        "adjacent-surface-scan",
        re.compile(
            r"^\s*[-*]?\s*`?adjacent[-\s]surface[-\s]scan`?\s*:",
            re.IGNORECASE | re.MULTILINE,
        ),
    ),
    (
        "semantic-decision",
        re.compile(
            r"^\s*[-*]?\s*`?semantic[-\s]decision`?\s*:",
            re.IGNORECASE | re.MULTILINE,
        ),
    ),
    (
        "verification-mapping",
        re.compile(
            r"^\s*[-*]?\s*`?verification[-\s]mapping`?\s*:",
            re.IGNORECASE | re.MULTILINE,
        ),
    ),
)
PREFLIGHT_DECISION_RE = re.compile(
    r"^\s*[-*]?\s*`?semantic[-\s]decision`?\s*:\s*"
    r"(preserve|restore|approved-change|not-product-semantic)\b",
    re.IGNORECASE | re.MULTILINE,
)
IMPACTED_PSC_RE = re.compile(
    r"^\s*[-*]?\s*`?impacted[-\s]psc`?\s*:\s*(.+)$",
    re.IGNORECASE | re.MULTILINE,
)
PSC_ID_RE = re.compile(r"\bpsc\.[A-Za-z0-9_.-]+\b")
CONTRACT_INDEX_RELATIVE_PATH = (
    "docs/internal/local-core/product-semantics/"
    "product-semantic-contract-index-2026-06-21.zh-TW.md"
)
CLOUD_REPO_NAME = "mindscape-ai-cloud"


def _normalize_path(value: str | Path) -> str:
    normalized = str(value).replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def _contract_doc_path(
    repo_root: Path,
    contract_doc: str,
    contract_root: Path | None = None,
) -> tuple[Path | None, str]:
    normalized = _normalize_path(contract_doc.split("#", 1)[0].strip())
    if (
        not normalized
        or normalized.startswith("/")
        or ".." in PurePosixPath(normalized).parts
    ):
        return None, normalized
    if normalized.startswith(f"{CLOUD_REPO_NAME}/"):
        cloud_relative = normalized.removeprefix(f"{CLOUD_REPO_NAME}/")
        if contract_root is not None:
            return contract_root / cloud_relative, normalized
        return repo_root.parent / normalized, normalized
    return repo_root / normalized, normalized


def _contract_index_path(repo_root: Path, contract_root: Path | None = None) -> Path:
    candidates = [repo_root / CONTRACT_INDEX_RELATIVE_PATH]
    if contract_root is not None:
        candidates.append(contract_root / CONTRACT_INDEX_RELATIVE_PATH)
    else:
        candidates.append(repo_root.parent / CLOUD_REPO_NAME / CONTRACT_INDEX_RELATIVE_PATH)
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[-1] if contract_root is not None else candidates[0]


def validate_contract_traceability(
    *,
    repo_root: Path,
    registry: dict[str, object],
    contract_root: Path | None = None,
    errors: list[str],
) -> None:
    contract_index = _contract_index_path(repo_root, contract_root)
    contract_index_source = _read_text(contract_index)
    if not contract_index_source:
        errors.append(f"Product semantic contract index is missing: {contract_index}")

    for surface in registry.get("surfaces", []) or []:
        if not isinstance(surface, dict):
            continue
        surface_id = str(surface.get("id") or "unknown-surface")
        contract_doc = str(surface.get("contract_doc") or "")
        contract_path, normalized_contract_doc = _contract_doc_path(
            repo_root,
            contract_doc,
            contract_root,
        )
        if contract_path is None:
            errors.append(
                f"{surface_id}: contract_doc must be a relative path without `..`: "
                f"{normalized_contract_doc or contract_doc}"
            )
            continue
        contract_source = _read_text(contract_path)
        if not contract_source:
            errors.append(f"{surface_id}: contract_doc is missing: {normalized_contract_doc}")
            continue
        if surface_id not in contract_source:
            errors.append(
                f"{surface_id}: contract_doc must name the registered surface id."
            )
        if contract_index_source and surface_id not in contract_index_source:
            errors.append(
                f"{surface_id}: product semantic contract index must name the "
                "registered surface id."
            )


def surface_ids(surface_hits: list[tuple[str, str]]) -> set[str]:
    return {surface_id for surface_id, _path in surface_hits}


def declared_impacted_psc_ids(body: str) -> set[str] | None:
    field = IMPACTED_PSC_RE.search(body)
    if field is None:
        return None
    value = field.group(1)
    ids = set(PSC_ID_RE.findall(value))
    if ids:
        return ids
    if re.search(r"\bnone\b", value, re.IGNORECASE):
        return set()
    return set()


def validate_impacted_psc_declaration(
    *,
    body: str,
    expected_surface_ids: set[str],
    errors: list[str],
) -> None:
    declared_surface_ids = declared_impacted_psc_ids(body)
    if declared_surface_ids is None:
        return
    if declared_surface_ids == expected_surface_ids:
        return
    expected = ", ".join(sorted(expected_surface_ids)) or "none"
    declared = ", ".join(sorted(declared_surface_ids)) or "none"
    errors.append(
        "Product Semantic Panoramic Preflight `impacted-psc:` must match "
        f"registry surface hits. expected: {expected}; declared: {declared}."
    )


def validate_preflight_declaration(
    *,
    body: str,
    semantic_change: str,
    expected_surface_ids: set[str],
    errors: list[str],
) -> None:
    if PREFLIGHT_SECTION_RE.search(body) is None:
        errors.append(
            "Product Semantic Panoramic Preflight is required for protected product "
            "semantic paths."
        )
    for field_name, field_re in PREFLIGHT_REQUIRED_FIELDS:
        if field_re.search(body) is None:
            errors.append(
                "Product Semantic Panoramic Preflight requires "
                f"`{field_name}:`."
            )

    decision = PREFLIGHT_DECISION_RE.search(body)
    if decision is None:
        errors.append(
            "Product Semantic Panoramic Preflight requires `semantic-decision:` "
            "to be one of preserve, restore, approved-change, or not-product-semantic."
        )
        return

    decision_value = decision.group(1).lower()
    if semantic_change == "approved" and decision_value != "approved-change":
        errors.append(
            "`product-semantic-change: approved` requires "
            "`semantic-decision: approved-change`."
        )
    if semantic_change == "none" and decision_value == "approved-change":
        errors.append(
            "`product-semantic-change: none` cannot use "
            "`semantic-decision: approved-change`."
        )
    validate_impacted_psc_declaration(
        body=body,
        expected_surface_ids=expected_surface_ids,
        errors=errors,
    )
