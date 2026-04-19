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

_PD_STORYBOARD_PLAYBOOK_CODES = {
    "pd_execute_storyboard_preview",
    "pd_intake_storyboard_preview",
    "pd_scene_package_preview_handoff",
}


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

        inspection_roots = self._candidate_result_roots(
            result_data=result_data,
            playbook_code=playbook_code,
        )

        # Resolve produces spec
        if playbook_code:
            playbook_spec = self._load_playbook_spec(playbook_code)
            if playbook_spec:
                spec_outputs = playbook_spec.get("outputs", {})
                matched = {}
                resolved_outputs = {}
                for output_name, output_def in spec_outputs.items():
                    source = output_def.get("source", "")
                    value = self._resolve_output_value(
                        roots=inspection_roots,
                        output_name=output_name,
                        source=source,
                    )
                    if value is not None:
                        matched[output_name] = {
                            "type": output_def.get("type", "unknown"),
                            "source": source,
                            "resolved": True,
                            "value_present": self._has_material_value(value),
                        }
                        summarized = self._summarize_output_value(output_name, value)
                        if summarized is not None:
                            resolved_outputs[output_name] = summarized
                    else:
                        matched[output_name] = {
                            "type": output_def.get("type", "unknown"),
                            "source": source,
                            "resolved": False,
                            "value_present": False,
                        }
                sidecar["outputs_matched"] = matched
                if resolved_outputs:
                    sidecar["resolved_outputs"] = resolved_outputs

        pd_storyboard_evidence = self._build_pd_storyboard_evidence(
            playbook_code=playbook_code,
            result_data=result_data,
            resolved_outputs=sidecar.get("resolved_outputs"),
        )
        if pd_storyboard_evidence:
            sidecar["pd_storyboard_evidence"] = pd_storyboard_evidence

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
    def _candidate_result_roots(
        result_data: Dict[str, Any],
        playbook_code: Optional[str],
    ) -> List[Dict[str, Any]]:
        roots: List[Dict[str, Any]] = []
        if isinstance(result_data, dict):
            roots.append(result_data)
            steps = result_data.get("steps")
            if isinstance(steps, dict) and playbook_code:
                nested = steps.get(playbook_code)
                if isinstance(nested, dict):
                    roots.append(nested)
            result_json = result_data.get("result_json")
            if isinstance(result_json, dict):
                roots.append(result_json)
                nested_steps = result_json.get("steps")
                if isinstance(nested_steps, dict) and playbook_code:
                    nested = nested_steps.get(playbook_code)
                    if isinstance(nested, dict):
                        roots.append(nested)

        deduped: List[Dict[str, Any]] = []
        seen = set()
        for root in roots:
            root_id = id(root)
            if root_id in seen:
                continue
            seen.add(root_id)
            deduped.append(root)
        return deduped

    @staticmethod
    def _legacy_step_output_source(source: str) -> Optional[str]:
        if isinstance(source, str) and source.startswith("step."):
            return f"step_outputs.{source[len('step.'):]}"
        return None

    @classmethod
    def _resolve_output_value(
        cls,
        *,
        roots: List[Dict[str, Any]],
        output_name: str,
        source: str,
    ) -> Any:
        candidate_paths: List[str] = []
        if isinstance(source, str) and source:
            candidate_paths.append(source)
            legacy_source = cls._legacy_step_output_source(source)
            if legacy_source:
                candidate_paths.append(legacy_source)
        candidate_paths.append(f"outputs.{output_name}")

        for root in roots:
            if not isinstance(root, dict):
                continue
            for path in candidate_paths:
                value = cls._resolve_source_path(root, path)
                if value is not None:
                    return value
        return None

    @staticmethod
    def _has_material_value(value: Any) -> bool:
        if value is None:
            return False
        if isinstance(value, str):
            return bool(value.strip())
        if isinstance(value, (list, tuple, set, dict)):
            return len(value) > 0
        return True

    @staticmethod
    def _summarize_output_value(output_name: str, value: Any) -> Any:
        """Reduce resolved output values into provenance-safe summaries."""
        if not PackDispatchAdapter._has_material_value(value):
            return None
        if output_name == "storyboard" and isinstance(value, dict):
            scenes = value.get("scenes")
            return {
                "storyboard_id": str(value.get("storyboard_id") or "").strip(),
                "workspace_id": str(value.get("workspace_id") or "").strip(),
                "scene_count": len(scenes) if isinstance(scenes, list) else 0,
            }
        if output_name == "selected_scene_package_selector" and isinstance(value, dict):
            return {
                field_name: value[field_name]
                for field_name in (
                    "artifact_id",
                    "package_id",
                    "scene_scope",
                    "variant_id",
                    "provider",
                    "generation_mode",
                    "status",
                )
                if value.get(field_name) not in (None, "", [], {})
            }
        if isinstance(value, dict):
            filtered = {
                field_name: value[field_name]
                for field_name in (
                    "session_id",
                    "storyboard_id",
                    "run_id",
                    "status",
                    "source_type",
                    "timeline_items_synced",
                )
                if value.get(field_name) not in (None, "", [], {})
            }
            if filtered:
                return filtered
            return {"keys": sorted(value.keys())[:10]}
        if isinstance(value, list):
            return {"count": len(value)}
        return value

    @staticmethod
    def _build_pd_storyboard_evidence(
        *,
        playbook_code: Optional[str],
        result_data: Dict[str, Any],
        resolved_outputs: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        if playbook_code not in _PD_STORYBOARD_PLAYBOOK_CODES:
            return {}

        resolved_outputs = (
            dict(resolved_outputs)
            if isinstance(resolved_outputs, dict)
            else {}
        )
        evidence: Dict[str, Any] = {"playbook_code": playbook_code}

        session_id = resolved_outputs.get("session_id")
        if not isinstance(session_id, str) or not session_id.strip():
            session_id = PackDispatchAdapter._first_value(
                result_data,
                [
                    "outputs.session_id",
                    "session_id",
                    "metadata.inputs.session_id",
                    "context.inputs.session_id",
                ],
            )
        if isinstance(session_id, str) and session_id.strip():
            evidence["session_id"] = session_id.strip()

        storyboard_summary = resolved_outputs.get("storyboard")
        if isinstance(storyboard_summary, dict) and storyboard_summary:
            evidence["storyboard"] = storyboard_summary
            storyboard_id = str(storyboard_summary.get("storyboard_id") or "").strip()
            if storyboard_id:
                evidence["storyboard_id"] = storyboard_id

        source_type = resolved_outputs.get("source_type")
        if isinstance(source_type, str) and source_type.strip():
            evidence["source_type"] = source_type.strip()

        run_id = resolved_outputs.get("run_id")
        if isinstance(run_id, str) and run_id.strip():
            evidence["run_id"] = run_id.strip()

        status = resolved_outputs.get("status")
        if isinstance(status, str) and status.strip():
            evidence["status"] = status.strip()

        timeline_items_synced = resolved_outputs.get("timeline_items_synced")
        if isinstance(timeline_items_synced, (int, float)) and not isinstance(
            timeline_items_synced, bool
        ):
            evidence["timeline_items_synced"] = timeline_items_synced

        selector_summary = resolved_outputs.get("selected_scene_package_selector")
        if isinstance(selector_summary, dict) and selector_summary:
            evidence["selected_scene_package_selector"] = selector_summary

        return evidence

    @staticmethod
    def _first_value(data: Dict[str, Any], paths: List[str]) -> Any:
        for path in paths:
            value = PackDispatchAdapter._resolve_source_path(data, path)
            if PackDispatchAdapter._has_material_value(value):
                return value
        return None

    @staticmethod
    def _compute_hash(data: Any) -> Optional[str]:
        """Compute SHA-256 hash of serializable data."""
        try:
            serialized = json.dumps(data, sort_keys=True, default=str)
            return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
        except Exception:
            return None
