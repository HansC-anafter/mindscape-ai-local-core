"""
Run Tracker for IG Capability

Provides high-level interface for tracking playbook execution with automatic
step tracking, artifact creation, and metering event recording.
"""
import logging
import hashlib
import json
from typing import Dict, Any, Optional, List
from datetime import datetime

try:
    from capabilities.ig.services.workspace_storage import WorkspaceStorage
    from capabilities.ig.services.control_plane_registry import (
        ControlPlaneRegistry,
        PlaybookRun,
        StepRun,
        Artifact,
        RunStatus,
        StepStatus,
        ArtifactKind
    )
except ImportError:
    # Fallback for local development
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent))
    from workspace_storage import WorkspaceStorage
    from control_plane_registry import (
        ControlPlaneRegistry,
        PlaybookRun,
        StepRun,
        Artifact,
        RunStatus,
        StepStatus,
        ArtifactKind
    )

logger = logging.getLogger(__name__)


class RunTracker:
    """
    High-level run tracker for playbook execution

    Automatically tracks:
    - Playbook run lifecycle
    - Step execution
    - Artifact creation
    - Metering events
    - Audit logs
    """

    def __init__(self, workspace_storage: WorkspaceStorage):
        """
        Initialize Run Tracker

        Args:
            workspace_storage: WorkspaceStorage instance
        """
        self.storage = workspace_storage
        self.registry = ControlPlaneRegistry(workspace_storage)
        self.current_run: Optional[PlaybookRun] = None
        self.current_steps: Dict[str, StepRun] = {}

    def start_run(
        self,
        workspace_id: str,
        tenant_id: Optional[str],
        playbook_code: str,
        playbook_version: str,
        invoked_by: str,
        input_data: Dict[str, Any],
        parent_run_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> PlaybookRun:
        """
        Start a new playbook run

        Args:
            workspace_id: Workspace identifier
            tenant_id: Tenant identifier (optional)
            playbook_code: Playbook code
            playbook_version: Playbook version
            invoked_by: Actor ID who invoked the run
            input_data: Input data dictionary
            parent_run_id: Parent run ID (for nested runs)
            metadata: Additional metadata

        Returns:
            PlaybookRun instance
        """
        # Calculate input hash
        input_json = json.dumps(input_data, sort_keys=True, ensure_ascii=False)
        input_hash = hashlib.sha256(input_json.encode("utf-8")).hexdigest()

        # Create run
        self.current_run = self.registry.create_run(
            workspace_id=workspace_id,
            tenant_id=tenant_id,
            playbook_code=playbook_code,
            playbook_version=playbook_version,
            invoked_by=invoked_by,
            input_hash=input_hash,
            input_data=input_data,
            parent_run_id=parent_run_id,
            metadata=metadata
        )

        # Update status to running
        self.current_run = self.registry.update_run_status(
            self.current_run.run_id,
            RunStatus.RUNNING
        )

        logger.info(f"Started run {self.current_run.run_id} for playbook {playbook_code}")

        return self.current_run

    def start_step(
        self,
        step_id: str,
        step_index: int,
        tool_ref: str,
        tool_slot: Optional[str],
        input_data: Dict[str, Any],
        depends_on: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> StepRun:
        """
        Start a new step run

        Args:
            step_id: Step ID from playbook spec
            step_index: Step index in playbook
            tool_ref: Tool reference
            tool_slot: Tool slot (optional)
            input_data: Input data dictionary
            depends_on: List of step_run_id dependencies
            metadata: Additional metadata

        Returns:
            StepRun instance
        """
        if not self.current_run:
            raise ValueError("No active run. Call start_run() first.")

        # Calculate input hash
        input_json = json.dumps(input_data, sort_keys=True, ensure_ascii=False)
        input_hash = hashlib.sha256(input_json.encode("utf-8")).hexdigest()

        # Create step run
        step_run = self.registry.create_step_run(
            run_id=self.current_run.run_id,
            step_id=step_id,
            step_index=step_index,
            tool_ref=tool_ref,
            tool_slot=tool_slot,
            input_hash=input_hash,
            input_data=input_data,
            depends_on=depends_on,
            metadata=metadata
        )

        # Update status to running (after saving)
        step_run.status = StepStatus.RUNNING
        step_run.started_at = datetime.now()
        self.registry._save_step_run(step_run)

        self.current_steps[step_id] = step_run

        logger.debug(f"Started step {step_id} (step_run_id: {step_run.step_run_id})")

        return step_run

    def complete_step(
        self,
        step_id: str,
        output_data: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None
    ) -> StepRun:
        """
        Complete a step run

        Args:
            step_id: Step ID
            output_data: Output data dictionary
            metadata: Additional metadata

        Returns:
            Updated StepRun instance
        """
        if step_id not in self.current_steps:
            raise ValueError(f"Step {step_id} not found in current run")

        step_run = self.current_steps[step_id]

        # Update step run
        step_run = self.registry.update_step_run_status(
            step_run.step_run_id,
            StepStatus.COMPLETED,
            output_data=output_data
        )

        if metadata:
            step_run.metadata.update(metadata)
            self.registry._save_step_run(step_run)

        logger.debug(f"Completed step {step_id} (step_run_id: {step_run.step_run_id})")

        return step_run

    def fail_step(
        self,
        step_id: str,
        error_message: str,
        error_trace: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> StepRun:
        """
        Mark a step as failed

        Args:
            step_id: Step ID
            error_message: Error message
            error_trace: Error trace (optional)
            metadata: Additional metadata

        Returns:
            Updated StepRun instance
        """
        if step_id not in self.current_steps:
            raise ValueError(f"Step {step_id} not found in current run")

        step_run = self.current_steps[step_id]

        # Update step run (use the stored step_run_id)
        updated_step_run = self.registry.update_step_run_status(
            step_run.step_run_id,
            StepStatus.FAILED,
            error_message=error_message,
            error_trace=error_trace
        )

        # Update cached step run
        self.current_steps[step_id] = updated_step_run

        if metadata:
            step_run.metadata.update(metadata)
            self.registry._save_step_run(step_run)

        logger.warning(f"Failed step {step_id} (step_run_id: {step_run.step_run_id}): {error_message}")

        return step_run

    def create_artifact(
        self,
        kind: ArtifactKind,
        uri: str,
        checksum: str,
        size: int,
        step_id: Optional[str] = None,
        mime_type: Optional[str] = None,
        retention_policy: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None
    ) -> Artifact:
        """
        Create an artifact

        Args:
            kind: Artifact kind
            uri: Artifact URI
            checksum: SHA256 checksum
            size: Size in bytes
            step_id: Step ID that created the artifact (optional)
            mime_type: MIME type (optional)
            retention_policy: Retention policy (optional)
            metadata: Additional metadata
            tags: Tags list

        Returns:
            Artifact instance
        """
        if not self.current_run:
            raise ValueError("No active run. Call start_run() first.")

        step_run_id = None
        if step_id and step_id in self.current_steps:
            step_run_id = self.current_steps[step_id].step_run_id

        artifact = self.registry.create_artifact(
            workspace_id=self.current_run.workspace_id,
            tenant_id=self.current_run.tenant_id,
            kind=kind,
            uri=uri,
            checksum=checksum,
            size=size,
            run_id=self.current_run.run_id,
            step_run_id=step_run_id,
            mime_type=mime_type,
            created_by=self.current_run.invoked_by,
            retention_policy=retention_policy,
            metadata=metadata,
            tags=tags
        )

        logger.info(f"Created artifact {artifact.artifact_id} (kind: {kind.value})")

        return artifact

    def record_metering(
        self,
        tool_ref: str,
        provider: str,
        units: float,
        unit_type: str,
        cost: float,
        currency: str = "USD",
        step_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Record a metering event

        Args:
            tool_ref: Tool reference
            provider: Provider name
            units: Units consumed
            unit_type: Unit type
            cost: Cost in currency
            currency: Currency code
            step_id: Step ID (optional)
            metadata: Additional metadata
        """
        if not self.current_run:
            raise ValueError("No active run. Call start_run() first.")

        step_run_id = None
        if step_id and step_id in self.current_steps:
            step_run_id = self.current_steps[step_id].step_run_id

        self.registry.record_metering_event(
            run_id=self.current_run.run_id,
            tenant_id=self.current_run.tenant_id or "default",
            workspace_id=self.current_run.workspace_id,
            tool_ref=tool_ref,
            provider=provider,
            units=units,
            unit_type=unit_type,
            cost=cost,
            currency=currency,
            step_run_id=step_run_id,
            metadata=metadata
        )

        logger.debug(f"Recorded metering event: {provider} {units} {unit_type} (cost: {cost} {currency})")

    def complete_run(
        self,
        output_data: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None
    ) -> PlaybookRun:
        """
        Complete the current run

        Args:
            output_data: Output data dictionary
            metadata: Additional metadata

        Returns:
            Updated PlaybookRun instance
        """
        if not self.current_run:
            raise ValueError("No active run. Call start_run() first.")

        # Update run status
        self.current_run = self.registry.update_run_status(
            self.current_run.run_id,
            RunStatus.COMPLETED,
            output_data=output_data
        )

        if metadata:
            self.current_run.metadata.update(metadata)
            self.registry._save_run(self.current_run)

        # Log audit event
        self.registry.log_audit(
            actor_id=self.current_run.invoked_by,
            actor_type="user",
            action="playbook.run.complete",
            object_type="PlaybookRun",
            object_id=self.current_run.run_id,
            status="success"
        )

        logger.info(f"Completed run {self.current_run.run_id}")

        return self.current_run

    def fail_run(
        self,
        error_message: str,
        error_trace: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> PlaybookRun:
        """
        Mark the current run as failed

        Args:
            error_message: Error message
            error_trace: Error trace (optional)
            metadata: Additional metadata

        Returns:
            Updated PlaybookRun instance
        """
        if not self.current_run:
            raise ValueError("No active run. Call start_run() first.")

        # Update run status
        self.current_run = self.registry.update_run_status(
            self.current_run.run_id,
            RunStatus.FAILED,
            error_message=error_message,
            error_trace=error_trace
        )

        if metadata:
            self.current_run.metadata.update(metadata)
            self.registry._save_run(self.current_run)

        # Log audit event
        self.registry.log_audit(
            actor_id=self.current_run.invoked_by,
            actor_type="user",
            action="playbook.run.fail",
            object_type="PlaybookRun",
            object_id=self.current_run.run_id,
            status="failure",
            error_message=error_message
        )

        logger.error(f"Failed run {self.current_run.run_id}: {error_message}")

        return self.current_run

    def save_checkpoint(self, checkpoint_data: Dict[str, Any]) -> str:
        """
        Save a checkpoint for the current run

        Args:
            checkpoint_data: Checkpoint data dictionary

        Returns:
            Checkpoint reference path
        """
        if not self.current_run:
            raise ValueError("No active run. Call start_run() first.")

        run_path = self.storage.get_run_path(self.current_run.run_id)
        checkpoint_file = run_path / "checkpoint.json"

        with open(checkpoint_file, "w", encoding="utf-8") as f:
            json.dump(checkpoint_data, f, indent=2, ensure_ascii=False)

        # Update run checkpoint reference
        self.current_run.checkpoint_ref = str(checkpoint_file)
        self.registry._save_run(self.current_run)

        logger.debug(f"Saved checkpoint for run {self.current_run.run_id}")

        return str(checkpoint_file)

    def load_checkpoint(self) -> Optional[Dict[str, Any]]:
        """
        Load checkpoint for the current run

        Returns:
            Checkpoint data dictionary or None
        """
        if not self.current_run:
            raise ValueError("No active run. Call start_run() first.")

        if not self.current_run.checkpoint_ref:
            return None

        checkpoint_file = Path(self.current_run.checkpoint_ref)
        if not checkpoint_file.exists():
            return None

        try:
            with open(checkpoint_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load checkpoint: {e}", exc_info=True)
            return None

