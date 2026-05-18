"""Explicit playbook direct-dispatch helpers for MeetingEngine."""

from __future__ import annotations

from typing import Any, Dict, List, Optional


class MeetingEngineDirectDispatchMixin:
        async def _stage_explicit_playbook_direct_dispatch(
            self,
            *,
            user_message: str,
            handoff_in: Optional[Any] = None,
        ) -> Optional[MeetingResult]:
            """Dispatch explicit requested-action playbooks without a planner turn."""
            direct_requests = self._explicit_requested_action_playbook_requests()
            if not direct_requests:
                return None

            if self.session.metadata is None:
                self.session.metadata = {}
            self.session.metadata["explicit_playbook_direct_dispatch"] = {
                "source": "requested_action",
                "playbook_codes": [
                    item.get("playbook_code")
                    for item in direct_requests
                    if item.get("playbook_code")
                ],
            }

            self._start_session()
            decision = self._render_explicit_playbook_direct_decision(direct_requests)
            action_intents, action_items = self._stage_policy_gate_and_emit(
                action_items=[],
                action_intents=[],
            )
            compiled_ir, dispatch_result = await self._stage_decompose_and_dispatch(
                decision=decision,
                action_intents=action_intents,
                action_items=action_items,
                handoff_in=handoff_in,
            )
            return self._stage_finalize(
                user_message=user_message,
                decision=decision,
                critic_notes=[],
                action_items=action_items,
                converged=True,
                compiled_ir=compiled_ir,
                dispatch_result=dispatch_result,
            )

        def _explicit_requested_action_playbook_requests(self) -> List[Dict[str, Any]]:
            contract = self._get_request_contract_metadata()
            requests = self._extract_request_contract_playbook_requests(contract)
            return [
                item
                for item in requests
                if str(item.get("request_contract_source") or "").strip()
                == "requested_action"
            ]

        @staticmethod
        def _render_explicit_playbook_direct_decision(
            requests: List[Dict[str, Any]],
        ) -> str:
            playbook_codes = [
                str(item.get("playbook_code") or "").strip()
                for item in requests
                if str(item.get("playbook_code") or "").strip()
            ]
            if not playbook_codes:
                return "Execute the explicit requested playbook route."
            return (
                "Execute explicit requested playbook route(s): "
                + ", ".join(playbook_codes)
            )

        def _ensure_requested_playbooks_in_available_cache(self) -> None:
            """Add installed explicit request playbooks to the policy allowlist cache."""
            contract = self._get_request_contract_metadata()
            requests = self._extract_request_contract_playbook_requests(contract)
            if not requests:
                return

            existing_cache = str(getattr(self, "_available_playbooks_cache", "") or "")
            existing_codes = {
                line[2:].split(":", 1)[0].strip()
                for line in existing_cache.splitlines()
                if line.strip().startswith("- ") and ":" in line
            }
            additions: List[str] = []

            try:
                from backend.app.services.orchestration.playbook_alias_resolution import (
                    load_playbook_spec,
                )
            except Exception:
                load_playbook_spec = None

            for item in requests:
                playbook_code = str(item.get("playbook_code") or "").strip()
                if not playbook_code or playbook_code in existing_codes:
                    continue
                if load_playbook_spec is None or load_playbook_spec(playbook_code) is None:
                    continue
                title = str(item.get("title") or playbook_code).strip() or playbook_code
                additions.append(f"- {playbook_code}: {title}")
                existing_codes.add(playbook_code)

            if not additions:
                return
            self._available_playbooks_cache = "\n".join(
                [part for part in [existing_cache.strip(), *additions] if part]
            )
