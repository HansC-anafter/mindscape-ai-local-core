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

import hashlib
import json
import logging
import uuid
from typing import Any, Dict, List, Optional

from backend.app.models.execution_metadata import GOVERNANCE_PAYLOAD_FIELDS

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

        # --- 3. Governance fields injection ---
        if action_item:
            for gov_field in GOVERNANCE_PAYLOAD_FIELDS:
                if gov_field in action_item and action_item[gov_field] is not None:
                    inputs.setdefault(gov_field, action_item[gov_field])

        request_contract = self._extract_request_contract(session)
        if request_contract:
            if "acceptance_tests" not in inputs and request_contract.get("acceptance_tests") is not None:
                inputs["acceptance_tests"] = request_contract["acceptance_tests"]
            if "governance_constraints" not in inputs and request_contract.get("constraints") is not None:
                inputs["governance_constraints"] = request_contract["constraints"]

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
        sidecar: Dict[str, Any] = {
            "provenance_schema_version": "1.1",
            "playbook_code": playbook_code,
            "parsed_by": "pack_dispatch_adapter_v1",
            "trace_index": {"entries": []},
        }

        if not isinstance(result_data, dict):
            sidecar["output_hash"] = self._compute_hash(result_data)
            return sidecar

        # Compute output hash
        sidecar["output_hash"] = self._compute_hash(result_data)
        context_attachments = self._extract_context_attachments(result_data)
        if context_attachments:
            sidecar["context_attachments"] = context_attachments

        # Resolve produces spec
        if playbook_code:
            playbook_spec = self._load_playbook_spec(playbook_code)
            if playbook_spec:
                spec_outputs = playbook_spec.get("outputs", {})
                matched = {}
                for output_name, output_def in spec_outputs.items():
                    source = output_def.get("source", "")
                    # Try to extract from result_data following source path
                    value = self._resolve_source_path(result_data, source)
                    if value is not None:
                        matched[output_name] = {
                            "type": output_def.get("type", "unknown"),
                            "source": source,
                            "resolved": True,
                        }
                    else:
                        matched[output_name] = {
                            "type": output_def.get("type", "unknown"),
                            "source": source,
                            "resolved": False,
                        }
                sidecar["outputs_matched"] = matched

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

    @staticmethod
    def _resolve_source_path(data: Dict[str, Any], source: str) -> Any:
        """Resolve a dot-path source (e.g. 'step.ocr.ocr_text') from data."""
        if not source or not isinstance(data, dict):
            return None
        parts = source.split(".")
        current = data
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return None
        return current

    @staticmethod
    def _extract_context_attachments(result_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract evidence attachments from result payload and metadata."""
        candidates: List[Dict[str, Any]] = []

        direct = result_data.get("context_attachments")
        if isinstance(direct, list):
            candidates.extend(item for item in direct if isinstance(item, dict))

        metadata = result_data.get("metadata")
        if isinstance(metadata, dict):
            nested = metadata.get("context_attachments")
            if isinstance(nested, list):
                candidates.extend(item for item in nested if isinstance(item, dict))

        attachments = result_data.get("attachments")
        if isinstance(attachments, list):
            candidates.extend(item for item in attachments if isinstance(item, dict))

        deduped: List[Dict[str, Any]] = []
        seen = set()
        for item in candidates:
            key = json.dumps(item, sort_keys=True, default=str)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped

    @staticmethod
    def _compute_hash(data: Any) -> Optional[str]:
        """Compute SHA-256 hash of serializable data."""
        try:
            serialized = json.dumps(data, sort_keys=True, default=str)
            return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
        except Exception:
            return None
