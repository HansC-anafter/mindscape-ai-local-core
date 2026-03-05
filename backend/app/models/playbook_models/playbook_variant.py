"""
Playbook Variant Model

Defines playbook-level variants for conversation mode execution.
Variants provide skip_steps, custom_checklist, and execution_params
overrides per-user or per-workspace.

Separate from Graph IR variants (GraphVariantRegistry) which operate
on GraphIR objects for workflow topology modifications.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class PlaybookVariant(BaseModel):
    """Playbook-level variant definition.

    Loaded from manifest.yaml playbooks[].variants[] entries.
    Used by PlaybookRunner in conversation mode (L356-366).
    """

    variant_id: str
    playbook_code: str
    name: str
    description: Optional[str] = None
    # Step indices to skip (List[int], matches conversation_manager.py:L55)
    skip_steps: List[int] = []
    custom_checklist: List[str] = []
    execution_params: Dict[str, Any] = {}
    # Optional auto-select conditions (risk_level, locale, etc.)
    conditions: Optional[Dict[str, Any]] = None

    def to_runner_dict(self) -> Dict[str, Any]:
        """Convert to dict format expected by PlaybookRunner.

        Runner accesses variant via .get() (playbook_runner.py:L357-366),
        so this must return a plain dict.
        """
        return {
            "skip_steps": self.skip_steps,
            "custom_checklist": self.custom_checklist,
            "execution_params": self.execution_params,
        }
