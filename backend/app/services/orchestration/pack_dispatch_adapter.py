"""
PackDispatchAdapter — Two-stage adapter for spec-aware dispatch.

**Launch side** (``prepare_handoff``):
  Uses ``PlaybookJsonLoader`` to read the playbook's field-level input
  spec (``PlaybookJson.inputs``), verifying required fields and injecting
  defaults. Falls back to ``manifest_utils`` affordance for type-level
  enrichment when playbook.json is unavailable.

**Completion side** (``parse_result``):
  Produces a **sidecar** provenance dict from raw playbook output —
  does NOT mutate the original ``result_data``. This is called
  **after** ``land_result()``, not before, to avoid breaking the
  raw payload structure that ``task_result_landing`` depends on.

Both methods are **gracefully degrading**: if the playbook spec
is unavailable, they return inputs/outputs unchanged.
"""

import logging
import uuid
from typing import Any, Dict, Optional

from backend.app.models.execution_metadata import GOVERNANCE_PAYLOAD_FIELDS
from backend.app.services.orchestration.pack_dispatch_adapter_core import (
    build_acceptance_evidence,
    build_result_sidecar,
    candidate_result_roots,
    compute_hash,
    extract_context_attachments,
    first_value,
    has_material_value,
    legacy_step_output_source,
    resolve_output_value,
    resolve_source_path,
    summarize_output_value,
)

logger = logging.getLogger(__name__)


class PackDispatchAdapter:
    """Spec-aware adapter layer between Meeting Engine and Pack execution.

    Usage — Launch side::

        adapter = PackDispatchAdapter()
        inputs = adapter.prepare_handoff(
            playbook_code="article_draft",
            raw_inputs={...},
            action_item={...},
        )

    Usage — Completion side (called AFTER land_result, not before)::

        sidecar = adapter.parse_result(
            result_data=raw_result,
            playbook_code="article_draft",
        )
        # sidecar is a provenance dict, does NOT replace result_data
    """

    # ------------------------------------------------------------------
    # Launch side
    # ------------------------------------------------------------------

    def prepare_handoff(
        self,
        *,
        playbook_code: str,
        raw_inputs: Dict[str, Any],
        phase: Any = None,
        action_item: Optional[Dict[str, Any]] = None,
        session: Any = None,
        profile_id: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Enrich launch inputs using the playbook's field-level spec.

        Resolution order:
        1.  **PlaybookJson.inputs** (field-level spec from playbook.json)
            — inject defaults for missing required fields
        2.  **manifest_utils affordance** (type-level consumes) — fallback
        3.  Governance field injection (trace_id, governance_constraints, etc.)

        Returns:
            Enriched inputs dict ready for ``ExecutionLauncher.launch()``.
        """
        inputs = dict(raw_inputs)

        # --- 1. PlaybookJson field-level spec ---
        playbook_spec = self._load_playbook_spec(playbook_code)
        if playbook_spec:
            spec_inputs = playbook_spec.get("inputs", {})
            for field_name, field_def in spec_inputs.items():
                if field_name in inputs:
                    continue  # Already provided, don't overwrite
                # Check action_item for matching field
                if action_item and field_name in action_item:
                    inputs[field_name] = action_item[field_name]
                elif field_def.get("default") is not None:
                    inputs[field_name] = field_def["default"]
                # Log missing required fields
                elif field_def.get("required", True):
                    logger.debug(
                        "PackDispatchAdapter: required input '%s' missing for %s",
                        field_name,
                        playbook_code,
                    )

        # --- 2. Manifest affordance fallback (type-level) ---
        if not playbook_spec:
            try:
                from backend.app.services.manifest_utils import (
                    resolve_playbook_affordance,
                )
                affordance = resolve_playbook_affordance(playbook_code)
                consumes = affordance.get("consumes", [])
                if consumes and action_item:
                    for declaration in consumes:
                        dtype = declaration.get("type", "") if isinstance(declaration, dict) else str(declaration)
                        field_name = dtype.split(".")[-1] if "." in dtype else dtype
                        if field_name and field_name in action_item and field_name not in inputs:
                            inputs[field_name] = action_item[field_name]
            except Exception as exc:
                logger.debug(
                    "PackDispatchAdapter: affordance fallback failed for %s: %s",
                    playbook_code, exc,
                )

        # Merge phase.input_params (lower priority)
        if phase and hasattr(phase, "input_params") and phase.input_params:
            for k, v in phase.input_params.items():
                if k not in inputs:
                    inputs[k] = v

        # Execution context autofill for meeting-dispatched playbooks.
        if session is not None:
            meeting_session_id = getattr(session, "id", None)
            if meeting_session_id and "meeting_session_id" not in inputs:
                inputs["meeting_session_id"] = meeting_session_id
            thread_id = getattr(session, "thread_id", None)
            if thread_id and "thread_id" not in inputs:
                inputs["thread_id"] = thread_id

        if project_id and "project_id" not in inputs:
            inputs["project_id"] = project_id

        # --- 3. Governance fields injection ---
        if action_item:
            for gov_field in GOVERNANCE_PAYLOAD_FIELDS:
                if gov_field in action_item and action_item[gov_field] is not None:
                    inputs.setdefault(gov_field, action_item[gov_field])

        request_contract = self._extract_request_contract(session)
        if request_contract:
            for gov_field in GOVERNANCE_PAYLOAD_FIELDS:
                if gov_field in inputs:
                    continue
                if gov_field == "governance_constraints":
                    candidate = request_contract.get(
                        "governance_constraints"
                    ) or request_contract.get("constraints")
                else:
                    candidate = request_contract.get(gov_field)
                if candidate is not None:
                    inputs[gov_field] = candidate

        if "trace_id" not in inputs:
            inputs["trace_id"] = str(uuid.uuid4())

        # Adapter provenance tag
        inputs["_adapter_version"] = "pack_dispatch_adapter_v1"
        inputs["_spec_resolved"] = playbook_spec is not None

        logger.debug(
            "PackDispatchAdapter.prepare_handoff: playbook=%s spec=%s keys=%s",
            playbook_code,
            playbook_spec is not None,
            list(inputs.keys()),
        )

        return inputs

    # ------------------------------------------------------------------
    # Completion side — SIDECAR, does NOT mutate result_data
    # ------------------------------------------------------------------

    def parse_result(
        self,
        *,
        result_data: Any,
        playbook_code: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Produce a provenance sidecar from raw playbook output.

        This is called **after** ``land_result()``, so it does NOT
        mutate the original ``result_data``. The returned dict is a
        structured provenance record that can be stored separately.

        Returns:
            Provenance sidecar dict with output_hash, matched produces,
            and provenance_schema_version.
        """
        playbook_spec = None
        if playbook_code and isinstance(result_data, dict):
            playbook_spec = self._load_playbook_spec(playbook_code)
        sidecar = build_result_sidecar(
            result_data=result_data,
            playbook_code=playbook_code,
            playbook_spec=playbook_spec,
        )

        logger.debug(
            "PackDispatchAdapter.parse_result: playbook=%s hash=%s",
            playbook_code,
            sidecar.get("output_hash", "")[:12],
        )

        return sidecar

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _load_playbook_spec(playbook_code: str) -> Optional[Dict[str, Any]]:
        """Load field-level spec from PlaybookJsonLoader.

        Returns simplified dict with 'inputs' and 'outputs' keys,
        or None if spec unavailable.
        """
        try:
            from backend.app.services.playbook_loaders import PlaybookJsonLoader

            pb = PlaybookJsonLoader.load_playbook_json(playbook_code)
            if pb is None:
                return None

            return {
                "inputs": {
                    name: {
                        "type": inp.type,
                        "required": inp.required,
                        "default": inp.default,
                        "description": inp.description,
                    }
                    for name, inp in (pb.inputs or {}).items()
                },
                "outputs": {
                    name: {
                        "type": out.type,
                        "source": out.source,
                        "description": out.description,
                    }
                    for name, out in (pb.outputs or {}).items()
                },
            }
        except Exception as exc:
            logger.debug(
                "PackDispatchAdapter: spec load failed for %s: %s",
                playbook_code,
                exc,
            )
            return None

    @staticmethod
    def _extract_request_contract(session: Any) -> Optional[Dict[str, Any]]:
        """Read request_contract from session metadata if present."""
        if session is None:
            return None
        metadata = getattr(session, "metadata", None)
        if not isinstance(metadata, dict):
            return None
        contract = metadata.get("request_contract")
        return contract if isinstance(contract, dict) and contract else None

    _resolve_source_path = staticmethod(resolve_source_path)
    _extract_context_attachments = staticmethod(extract_context_attachments)
    _candidate_result_roots = staticmethod(candidate_result_roots)
    _legacy_step_output_source = staticmethod(legacy_step_output_source)
    _resolve_output_value = staticmethod(resolve_output_value)
    _has_material_value = staticmethod(has_material_value)
    _summarize_output_value = staticmethod(summarize_output_value)
    _build_acceptance_evidence = staticmethod(build_acceptance_evidence)
    _first_value = staticmethod(first_value)
    _compute_hash = staticmethod(compute_hash)
