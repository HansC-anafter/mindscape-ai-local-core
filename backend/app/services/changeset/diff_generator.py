"""
Diff Generator

Generates readable diff summaries from change sets.
"""

import logging
from typing import Optional, Dict, Any
import difflib

from backend.app.core.ir.changeset import ChangeSetIR, ChangePatch, ChangeType

logger = logging.getLogger(__name__)


class DiffGenerator:
    """
    Generates readable diff summaries from change sets
    """

    def __init__(self):
        """Initialize DiffGenerator"""
        pass

    def generate_diff(
        self,
        changeset: ChangeSetIR,
        format: str = "unified"
    ) -> Dict[str, Any]:
        """
        Generate diff summary and details from change set

        Args:
            changeset: ChangeSetIR instance
            format: Diff format ("unified", "context", "html")

        Returns:
            Dictionary with diff_summary and diff_details
        """
        try:
            diff_summary = self._generate_summary(changeset)
            diff_details = self._generate_details(changeset, format)

            return {
                "diff_summary": diff_summary,
                "diff_details": diff_details,
            }
        except Exception as e:
            logger.error(f"DiffGenerator: Failed to generate diff: {e}", exc_info=True)
            return {
                "diff_summary": f"Failed to generate diff: {str(e)}",
                "diff_details": {},
            }

    def _generate_summary(self, changeset: ChangeSetIR) -> str:
        """
        Generate human-readable diff summary

        Args:
            changeset: ChangeSetIR instance

        Returns:
            Summary string
        """
        lines = []
        lines.append(f"ChangeSet {changeset.changeset_id}")
        lines.append(f"Workspace: {changeset.workspace_id}")
        lines.append(f"Status: {changeset.status.value}")
        lines.append(f"Total patches: {len(changeset.patches)}")
        lines.append("")

        # Group patches by type
        by_type = {}
        for patch in changeset.patches:
            patch_type = patch.change_type.value
            if patch_type not in by_type:
                by_type[patch_type] = []
            by_type[patch_type].append(patch)

        # Summary by type
        for patch_type, patches in by_type.items():
            lines.append(f"{patch_type.upper()}: {len(patches)} changes")
            for patch in patches[:5]:  # Show first 5
                target = patch.target
                if patch.path:
                    target = f"{target}/{patch.path}"
                lines.append(f"  - {target}")
            if len(patches) > 5:
                lines.append(f"  ... and {len(patches) - 5} more")
            lines.append("")

        return "\n".join(lines)

    def _generate_details(
        self,
        changeset: ChangeSetIR,
        format: str = "unified"
    ) -> Dict[str, Any]:
        """
        Generate detailed diff

        Args:
            changeset: ChangeSetIR instance
            format: Diff format

        Returns:
            Dictionary with detailed diff information
        """
        details = {
            "format": format,
            "patches": []
        }

        for patch in changeset.patches:
            patch_diff = self._generate_patch_diff(patch, format)
            details["patches"].append(patch_diff)

        return details

    def _generate_patch_diff(
        self,
        patch: ChangePatch,
        format: str = "unified"
    ) -> Dict[str, Any]:
        """
        Generate diff for a single patch

        Args:
            patch: ChangePatch instance
            format: Diff format

        Returns:
            Dictionary with patch diff information
        """
        patch_diff = {
            "change_type": patch.change_type.value,
            "target": patch.target,
            "path": patch.path,
        }

        if format == "unified":
            if patch.change_type == ChangeType.UPDATE:
                # Generate unified diff for update
                old_lines = self._value_to_lines(patch.old_value)
                new_lines = self._value_to_lines(patch.new_value)

                diff_lines = list(difflib.unified_diff(
                    old_lines,
                    new_lines,
                    fromfile=patch.target,
                    tofile=patch.target,
                    lineterm=""
                ))
                patch_diff["diff"] = "\n".join(diff_lines)
            elif patch.change_type == ChangeType.CREATE:
                new_lines = self._value_to_lines(patch.new_value)
                patch_diff["diff"] = "\n".join([f"+ {line}" for line in new_lines])
            elif patch.change_type == ChangeType.DELETE:
                old_lines = self._value_to_lines(patch.old_value)
                patch_diff["diff"] = "\n".join([f"- {line}" for line in old_lines])
            else:
                patch_diff["diff"] = f"{patch.change_type.value}: {patch.target}"
        else:
            # Simple format
            patch_diff["old_value"] = patch.old_value
            patch_diff["new_value"] = patch.new_value

        if patch.metadata:
            patch_diff["metadata"] = patch.metadata

        return patch_diff

    def _value_to_lines(self, value: Any) -> list:
        """
        Convert value to lines for diff

        Args:
            value: Value to convert

        Returns:
            List of strings
        """
        if value is None:
            return []
        elif isinstance(value, str):
            return value.splitlines()
        elif isinstance(value, (dict, list)):
            import json
            try:
                json_str = json.dumps(value, indent=2, ensure_ascii=False)
                return json_str.splitlines()
            except Exception:
                return [str(value)]
        else:
            return [str(value)]





