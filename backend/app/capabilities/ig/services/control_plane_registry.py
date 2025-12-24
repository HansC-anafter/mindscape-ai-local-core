"""
Control Plane Registry for IG Capability

Provides data layer for tracking runs, steps, artifacts, metering events, and audit logs.
This implements the control plane data model for enterprise governance.
"""
import logging
import json
import uuid
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
from dataclasses import dataclass, asdict
from enum import Enum

try:
    from capabilities.ig.services.workspace_storage import WorkspaceStorage
except ImportError:
    # Fallback for local development
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent))
    from workspace_storage import WorkspaceStorage

logger = logging.getLogger(__name__)


class RunStatus(str, Enum):
    """Playbook run status"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StepStatus(str, Enum):
    """Step run status"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class ArtifactKind(str, Enum):
    """Artifact kind"""
    FILE = "file"
    DATA = "data"
    CHECKPOINT = "checkpoint"
    LOG = "log"
    REPORT = "report"


@dataclass
class PlaybookRun:
    """Playbook run record"""
    run_id: str
    workspace_id: str
    tenant_id: Optional[str]
    playbook_code: str
    playbook_version: str
    status: RunStatus
    invoked_by: str
    started_at: datetime
    ended_at: Optional[datetime]
    input_hash: str
    input_ref: str
    output_ref: Optional[str]
    checkpoint_ref: Optional[str]
    error_message: Optional[str]
    error_trace: Optional[str]
    retry_count: int
    parent_run_id: Optional[str]
    metadata: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        data = asdict(self)
        data["status"] = self.status.value
        data["started_at"] = self.started_at.isoformat()
        if self.ended_at:
            data["ended_at"] = self.ended_at.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PlaybookRun":
        """Create from dictionary"""
        data["status"] = RunStatus(data["status"])
        data["started_at"] = datetime.fromisoformat(data["started_at"])
        if data.get("ended_at"):
            data["ended_at"] = datetime.fromisoformat(data["ended_at"])
        return cls(**data)


@dataclass
class StepRun:
    """Step run record"""
    step_run_id: str
    run_id: str
    step_id: str
    step_index: int
    tool_ref: str
    tool_slot: Optional[str]
    status: StepStatus
    started_at: datetime
    ended_at: Optional[datetime]
    input_hash: str
    input_ref: str
    output_ref: Optional[str]
    error_message: Optional[str]
    error_trace: Optional[str]
    retry_count: int
    depends_on: List[str]
    metadata: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        data = asdict(self)
        data["status"] = self.status.value
        data["started_at"] = self.started_at.isoformat()
        if self.ended_at:
            data["ended_at"] = self.ended_at.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StepRun":
        """Create from dictionary"""
        data["status"] = StepStatus(data["status"])
        data["started_at"] = datetime.fromisoformat(data["started_at"])
        if data.get("ended_at"):
            data["ended_at"] = datetime.fromisoformat(data["ended_at"])
        return cls(**data)


@dataclass
class Artifact:
    """Artifact record"""
    artifact_id: str
    workspace_id: str
    tenant_id: Optional[str]
    run_id: Optional[str]
    step_run_id: Optional[str]
    kind: ArtifactKind
    uri: str
    checksum: str
    size: int
    mime_type: Optional[str]
    created_at: datetime
    created_by: Optional[str]
    retention_policy: Optional[str]
    expires_at: Optional[datetime]
    metadata: Dict[str, Any]
    tags: List[str]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        data = asdict(self)
        data["kind"] = self.kind.value
        data["created_at"] = self.created_at.isoformat()
        if self.expires_at:
            data["expires_at"] = self.expires_at.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Artifact":
        """Create from dictionary"""
        data["kind"] = ArtifactKind(data["kind"])
        data["created_at"] = datetime.fromisoformat(data["created_at"])
        if data.get("expires_at"):
            data["expires_at"] = datetime.fromisoformat(data["expires_at"])
        return cls(**data)


@dataclass
class MeteringEvent:
    """Metering event record"""
    event_id: str
    run_id: str
    step_run_id: Optional[str]
    tenant_id: str
    workspace_id: str
    tool_ref: str
    provider: str
    units: float
    unit_type: str
    cost: float
    currency: str
    occurred_at: datetime
    metadata: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        data = asdict(self)
        data["occurred_at"] = self.occurred_at.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MeteringEvent":
        """Create from dictionary"""
        data["occurred_at"] = datetime.fromisoformat(data["occurred_at"])
        return cls(**data)


@dataclass
class AuditLog:
    """Audit log record"""
    event_id: str
    actor_id: str
    actor_type: str
    action: str
    object_type: str
    object_id: Optional[str]
    object_ref: Optional[str]
    status: str
    error_message: Optional[str]
    ip_address: Optional[str]
    user_agent: Optional[str]
    occurred_at: datetime
    metadata: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        data = asdict(self)
        data["occurred_at"] = self.occurred_at.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AuditLog":
        """Create from dictionary"""
        data["occurred_at"] = datetime.fromisoformat(data["occurred_at"])
        return cls(**data)


class ControlPlaneRegistry:
    """
    Control Plane Registry for tracking runs, steps, artifacts, metering, and audit

    This provides a file-based registry implementation. In enterprise mode,
    this can be replaced with a database-backed implementation.
    """

    def __init__(self, workspace_storage: WorkspaceStorage):
        """
        Initialize Control Plane Registry

        Args:
            workspace_storage: WorkspaceStorage instance
        """
        self.storage = workspace_storage
        self.runs_index_path = self.storage.get_runs_path() / "runs_index.json"
        self.artifacts_index_path = self.storage.get_artifacts_path() / "artifacts_index.json"

    # PlaybookRun methods

    def create_run(
        self,
        workspace_id: str,
        tenant_id: Optional[str],
        playbook_code: str,
        playbook_version: str,
        invoked_by: str,
        input_hash: str,
        input_data: Dict[str, Any],
        parent_run_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> PlaybookRun:
        """
        Create a new playbook run

        Args:
            workspace_id: Workspace identifier
            tenant_id: Tenant identifier (optional)
            playbook_code: Playbook code
            playbook_version: Playbook version
            invoked_by: Actor ID who invoked the run
            input_hash: SHA256 hash of input JSON
            input_data: Input data dictionary
            parent_run_id: Parent run ID (for nested runs)
            metadata: Additional metadata

        Returns:
            PlaybookRun instance
        """
        run_id = str(uuid.uuid4())
        run_path = self.storage.get_run_path(run_id)

        # Save input snapshot
        input_ref = str(run_path / "input.json")
        with open(run_path / "input.json", "w", encoding="utf-8") as f:
            json.dump(input_data, f, indent=2, ensure_ascii=False)

        run = PlaybookRun(
            run_id=run_id,
            workspace_id=workspace_id,
            tenant_id=tenant_id,
            playbook_code=playbook_code,
            playbook_version=playbook_version,
            status=RunStatus.PENDING,
            invoked_by=invoked_by,
            started_at=datetime.now(),
            ended_at=None,
            input_hash=input_hash,
            input_ref=input_ref,
            output_ref=None,
            checkpoint_ref=None,
            error_message=None,
            error_trace=None,
            retry_count=0,
            parent_run_id=parent_run_id,
            metadata=metadata or {}
        )

        # Save run record
        self._save_run(run)

        # Log audit event
        self.log_audit(
            actor_id=invoked_by,
            actor_type="user",
            action="playbook.run.create",
            object_type="PlaybookRun",
            object_id=run_id,
            object_ref=input_ref,
            status="success"
        )

        return run

    def update_run_status(
        self,
        run_id: str,
        status: RunStatus,
        output_data: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
        error_trace: Optional[str] = None
    ) -> PlaybookRun:
        """
        Update run status

        Args:
            run_id: Run ID
            status: New status
            output_data: Output data (for completed runs)
            error_message: Error message (for failed runs)
            error_trace: Error trace (for failed runs)

        Returns:
            Updated PlaybookRun instance
        """
        run = self.get_run(run_id)
        if not run:
            raise ValueError(f"Run {run_id} not found")

        run.status = status
        run.ended_at = datetime.now() if status in [RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED] else None

        if output_data:
            run_path = self.storage.get_run_path(run_id)
            output_ref = str(run_path / "output.json")
            with open(run_path / "output.json", "w", encoding="utf-8") as f:
                json.dump(output_data, f, indent=2, ensure_ascii=False)
            run.output_ref = output_ref

        if error_message:
            run.error_message = error_message
        if error_trace:
            run.error_trace = error_trace

        self._save_run(run)

        return run

    def get_run(self, run_id: str) -> Optional[PlaybookRun]:
        """Get run by ID"""
        run_path = self.storage.get_run_path(run_id)
        run_file = run_path / "run.json"

        if not run_file.exists():
            return None

        try:
            with open(run_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return PlaybookRun.from_dict(data)
        except Exception as e:
            logger.error(f"Failed to load run {run_id}: {e}", exc_info=True)
            return None

    def list_runs(
        self,
        workspace_id: Optional[str] = None,
        playbook_code: Optional[str] = None,
        status: Optional[RunStatus] = None,
        limit: int = 100
    ) -> List[PlaybookRun]:
        """
        List runs with filters

        Args:
            workspace_id: Filter by workspace ID
            playbook_code: Filter by playbook code
            status: Filter by status
            limit: Maximum number of results

        Returns:
            List of PlaybookRun instances
        """
        runs_index = self._load_runs_index()
        runs = []

        for run_id, run_data in runs_index.items():
            run = self.get_run(run_id)
            if not run:
                continue

            if workspace_id and run.workspace_id != workspace_id:
                continue
            if playbook_code and run.playbook_code != playbook_code:
                continue
            if status and run.status != status:
                continue

            runs.append(run)

        # Sort by started_at descending
        runs.sort(key=lambda r: r.started_at, reverse=True)

        return runs[:limit]

    def _save_run(self, run: PlaybookRun) -> None:
        """Save run record"""
        run_path = self.storage.get_run_path(run.run_id)
        run_file = run_path / "run.json"

        with open(run_file, "w", encoding="utf-8") as f:
            json.dump(run.to_dict(), f, indent=2, ensure_ascii=False)

        # Update index
        runs_index = self._load_runs_index()
        runs_index[run.run_id] = {
            "workspace_id": run.workspace_id,
            "playbook_code": run.playbook_code,
            "status": run.status.value,
            "started_at": run.started_at.isoformat()
        }
        self._save_runs_index(runs_index)

    def _load_runs_index(self) -> Dict[str, Any]:
        """Load runs index"""
        if self.runs_index_path.exists():
            try:
                with open(self.runs_index_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load runs index: {e}")
        return {}

    def _save_runs_index(self, index: Dict[str, Any]) -> None:
        """Save runs index"""
        self.runs_index_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.runs_index_path, "w", encoding="utf-8") as f:
            json.dump(index, f, indent=2, ensure_ascii=False)

    # StepRun methods

    def create_step_run(
        self,
        run_id: str,
        step_id: str,
        step_index: int,
        tool_ref: str,
        tool_slot: Optional[str],
        input_hash: str,
        input_data: Dict[str, Any],
        depends_on: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> StepRun:
        """
        Create a new step run

        Args:
            run_id: Parent run ID
            step_id: Step ID from playbook spec
            step_index: Step index in playbook
            tool_ref: Tool reference
            tool_slot: Tool slot (optional)
            input_hash: SHA256 hash of input JSON
            input_data: Input data dictionary
            depends_on: List of step_run_id dependencies
            metadata: Additional metadata

        Returns:
            StepRun instance
        """
        step_run_id = str(uuid.uuid4())
        run_path = self.storage.get_run_path(run_id)
        step_path = run_path / "steps" / f"{step_id}_{step_index}"
        step_path.mkdir(parents=True, exist_ok=True)

        # Save input snapshot
        input_ref = str(step_path / "input.json")
        with open(step_path / "input.json", "w", encoding="utf-8") as f:
            json.dump(input_data, f, indent=2, ensure_ascii=False)

        step_run = StepRun(
            step_run_id=step_run_id,
            run_id=run_id,
            step_id=step_id,
            step_index=step_index,
            tool_ref=tool_ref,
            tool_slot=tool_slot,
            status=StepStatus.PENDING,
            started_at=datetime.now(),
            ended_at=None,
            input_hash=input_hash,
            input_ref=input_ref,
            output_ref=None,
            error_message=None,
            error_trace=None,
            retry_count=0,
            depends_on=depends_on or [],
            metadata=metadata or {}
        )

        # Save step run record
        self._save_step_run(step_run)

        return step_run

    def update_step_run_status(
        self,
        step_run_id: str,
        status: StepStatus,
        output_data: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
        error_trace: Optional[str] = None
    ) -> StepRun:
        """
        Update step run status

        Args:
            step_run_id: Step run ID
            status: New status
            output_data: Output data (for completed steps)
            error_message: Error message (for failed steps)
            error_trace: Error trace (for failed steps)

        Returns:
            Updated StepRun instance
        """
        step_run = self.get_step_run(step_run_id)
        if not step_run:
            raise ValueError(f"Step run {step_run_id} not found")

        step_run.status = status
        step_run.ended_at = datetime.now() if status in [StepStatus.COMPLETED, StepStatus.FAILED] else None

        if output_data:
            run_path = self.storage.get_run_path(step_run.run_id)
            step_path = run_path / "steps" / f"{step_run.step_id}_{step_run.step_index}"
            output_ref = str(step_path / "output.json")
            with open(step_path / "output.json", "w", encoding="utf-8") as f:
                json.dump(output_data, f, indent=2, ensure_ascii=False)
            step_run.output_ref = output_ref

        if error_message:
            step_run.error_message = error_message
            # Save error details
            run_path = self.storage.get_run_path(step_run.run_id)
            step_path = run_path / "steps" / f"{step_run.step_id}_{step_run.step_index}"
            with open(step_path / "error.json", "w", encoding="utf-8") as f:
                json.dump({
                    "error_message": error_message,
                    "error_trace": error_trace
                }, f, indent=2, ensure_ascii=False)

        if error_trace:
            step_run.error_trace = error_trace

        self._save_step_run(step_run)

        return step_run

    def get_step_run(self, step_run_id: str) -> Optional[StepRun]:
        """Get step run by ID"""
        # Load from run directory
        # Step runs are stored in: runs/{run_id}/steps/{step_id}_{step_index}/step.json
        # We need to search all runs to find the step
        runs_index = self._load_runs_index()
        for run_id in runs_index.keys():
            run_path = self.storage.get_run_path(run_id)
            steps_path = run_path / "steps"
            if not steps_path.exists():
                continue

            # Search in all step directories
            for step_dir in steps_path.iterdir():
                if step_dir.is_dir():
                    step_file = step_dir / "step.json"
                    if step_file.exists():
                        try:
                            with open(step_file, "r", encoding="utf-8") as f:
                                data = json.load(f)
                            step_run = StepRun.from_dict(data)
                            if step_run.step_run_id == step_run_id:
                                return step_run
                        except Exception as e:
                            logger.warning(f"Failed to load step from {step_dir}: {e}")

        return None

    def get_run_steps(self, run_id: str) -> List[StepRun]:
        """Get all steps for a run"""
        run_path = self.storage.get_run_path(run_id)
        steps_path = run_path / "steps"

        if not steps_path.exists():
            return []

        steps = []
        for step_dir in steps_path.iterdir():
            if step_dir.is_dir():
                step_file = step_dir / "step.json"
                if step_file.exists():
                    try:
                        with open(step_file, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        steps.append(StepRun.from_dict(data))
                    except Exception as e:
                        logger.warning(f"Failed to load step from {step_dir}: {e}")

        steps.sort(key=lambda s: s.step_index)
        return steps

    def _save_step_run(self, step_run: StepRun) -> None:
        """Save step run record"""
        run_path = self.storage.get_run_path(step_run.run_id)
        step_path = run_path / "steps" / f"{step_run.step_id}_{step_run.step_index}"
        step_path.mkdir(parents=True, exist_ok=True)
        step_file = step_path / "step.json"

        with open(step_file, "w", encoding="utf-8") as f:
            json.dump(step_run.to_dict(), f, indent=2, ensure_ascii=False)

    # Artifact methods

    def create_artifact(
        self,
        workspace_id: str,
        tenant_id: Optional[str],
        kind: ArtifactKind,
        uri: str,
        checksum: str,
        size: int,
        run_id: Optional[str] = None,
        step_run_id: Optional[str] = None,
        mime_type: Optional[str] = None,
        created_by: Optional[str] = None,
        retention_policy: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None
    ) -> Artifact:
        """
        Create a new artifact

        Args:
            workspace_id: Workspace identifier
            tenant_id: Tenant identifier (optional)
            kind: Artifact kind
            uri: Artifact URI (storage path or external URL)
            checksum: SHA256 checksum
            size: Size in bytes
            run_id: Associated run ID (optional)
            step_run_id: Associated step run ID (optional)
            mime_type: MIME type (optional)
            created_by: Creator actor ID (optional)
            retention_policy: Retention policy (optional)
            metadata: Additional metadata
            tags: Tags list

        Returns:
            Artifact instance
        """
        artifact_id = str(uuid.uuid4())
        artifact_path = self.storage.get_artifact_path(artifact_id)

        # Calculate expiration if retention policy provided
        expires_at = None
        if retention_policy:
            # Parse retention policy (e.g., "30d", "1y")
            expires_at = self._calculate_expiration(retention_policy)

        artifact = Artifact(
            artifact_id=artifact_id,
            workspace_id=workspace_id,
            tenant_id=tenant_id,
            run_id=run_id,
            step_run_id=step_run_id,
            kind=kind,
            uri=uri,
            checksum=checksum,
            size=size,
            mime_type=mime_type,
            created_at=datetime.now(),
            created_by=created_by,
            retention_policy=retention_policy,
            expires_at=expires_at,
            metadata=metadata or {},
            tags=tags or []
        )

        # Save artifact record
        self._save_artifact(artifact)

        return artifact

    def get_artifact(self, artifact_id: str) -> Optional[Artifact]:
        """Get artifact by ID"""
        artifact_path = self.storage.get_artifact_path(artifact_id)
        artifact_file = artifact_path / "artifact.json"

        if not artifact_file.exists():
            return None

        try:
            with open(artifact_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return Artifact.from_dict(data)
        except Exception as e:
            logger.error(f"Failed to load artifact {artifact_id}: {e}", exc_info=True)
            return None

    def list_artifacts(
        self,
        workspace_id: Optional[str] = None,
        run_id: Optional[str] = None,
        kind: Optional[ArtifactKind] = None,
        limit: int = 100
    ) -> List[Artifact]:
        """
        List artifacts with filters

        Args:
            workspace_id: Filter by workspace ID
            run_id: Filter by run ID
            kind: Filter by artifact kind
            limit: Maximum number of results

        Returns:
            List of Artifact instances
        """
        artifacts_index = self._load_artifacts_index()
        artifacts = []

        for artifact_id in artifacts_index.keys():
            artifact = self.get_artifact(artifact_id)
            if not artifact:
                continue

            if workspace_id and artifact.workspace_id != workspace_id:
                continue
            if run_id and artifact.run_id != run_id:
                continue
            if kind and artifact.kind != kind:
                continue

            artifacts.append(artifact)

        # Sort by created_at descending
        artifacts.sort(key=lambda a: a.created_at, reverse=True)

        return artifacts[:limit]

    def _save_artifact(self, artifact: Artifact) -> None:
        """Save artifact record"""
        artifact_path = self.storage.get_artifact_path(artifact.artifact_id)
        artifact_file = artifact_path / "artifact.json"

        with open(artifact_file, "w", encoding="utf-8") as f:
            json.dump(artifact.to_dict(), f, indent=2, ensure_ascii=False)

        # Update index
        artifacts_index = self._load_artifacts_index()
        artifacts_index[artifact.artifact_id] = {
            "workspace_id": artifact.workspace_id,
            "run_id": artifact.run_id,
            "kind": artifact.kind.value,
            "created_at": artifact.created_at.isoformat()
        }
        self._save_artifacts_index(artifacts_index)

    def _load_artifacts_index(self) -> Dict[str, Any]:
        """Load artifacts index"""
        if self.artifacts_index_path.exists():
            try:
                with open(self.artifacts_index_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load artifacts index: {e}")
        return {}

    def _save_artifacts_index(self, index: Dict[str, Any]) -> None:
        """Save artifacts index"""
        self.artifacts_index_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.artifacts_index_path, "w", encoding="utf-8") as f:
            json.dump(index, f, indent=2, ensure_ascii=False)

    def _calculate_expiration(self, retention_policy: str) -> datetime:
        """
        Calculate expiration date from retention policy

        Args:
            retention_policy: Retention policy string (e.g., "30d", "1y")

        Returns:
            Expiration datetime
        """
        from datetime import timedelta

        now = datetime.now()

        if retention_policy.endswith("d"):
            days = int(retention_policy[:-1])
            return now + timedelta(days=days)
        elif retention_policy.endswith("w"):
            weeks = int(retention_policy[:-1])
            return now + timedelta(weeks=weeks)
        elif retention_policy.endswith("m"):
            months = int(retention_policy[:-1])
            return now + timedelta(days=months * 30)
        elif retention_policy.endswith("y"):
            years = int(retention_policy[:-1])
            return now + timedelta(days=years * 365)
        else:
            # Default to 30 days
            return now + timedelta(days=30)

    # MeteringEvent methods

    def record_metering_event(
        self,
        run_id: str,
        tenant_id: str,
        workspace_id: str,
        tool_ref: str,
        provider: str,
        units: float,
        unit_type: str,
        cost: float,
        currency: str = "USD",
        step_run_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> MeteringEvent:
        """
        Record a metering event

        Args:
            run_id: Run ID
            tenant_id: Tenant identifier
            workspace_id: Workspace identifier
            tool_ref: Tool reference
            provider: Provider name (e.g., "openai", "anthropic")
            units: Units consumed (e.g., tokens, API calls)
            unit_type: Unit type (e.g., "tokens", "requests")
            cost: Cost in currency
            currency: Currency code (default: "USD")
            step_run_id: Step run ID (optional)
            metadata: Additional metadata

        Returns:
            MeteringEvent instance
        """
        event_id = str(uuid.uuid4())

        event = MeteringEvent(
            event_id=event_id,
            run_id=run_id,
            step_run_id=step_run_id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            tool_ref=tool_ref,
            provider=provider,
            units=units,
            unit_type=unit_type,
            cost=cost,
            currency=currency,
            occurred_at=datetime.now(),
            metadata=metadata or {}
        )

        # Append to metering log (NDJSON format)
        self._append_metering_event(event)

        return event

    def _append_metering_event(self, event: MeteringEvent) -> None:
        """Append metering event to log file"""
        logs_path = self.storage.get_logs_path()
        metering_log = logs_path / "metering.ndjson"

        with open(metering_log, "a", encoding="utf-8") as f:
            f.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")

    def get_metering_events(
        self,
        run_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
        provider: Optional[str] = None,
        limit: int = 1000
    ) -> List[MeteringEvent]:
        """
        Get metering events with filters

        Args:
            run_id: Filter by run ID
            tenant_id: Filter by tenant ID
            workspace_id: Filter by workspace ID
            provider: Filter by provider
            limit: Maximum number of results

        Returns:
            List of MeteringEvent instances
        """
        logs_path = self.storage.get_logs_path()
        metering_log = logs_path / "metering.ndjson"

        if not metering_log.exists():
            return []

        events = []
        try:
            with open(metering_log, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)
                        event = MeteringEvent.from_dict(data)

                        # Apply filters
                        if run_id and event.run_id != run_id:
                            continue
                        if tenant_id and event.tenant_id != tenant_id:
                            continue
                        if workspace_id and event.workspace_id != workspace_id:
                            continue
                        if provider and event.provider != provider:
                            continue

                        events.append(event)
                    except Exception as e:
                        logger.warning(f"Failed to parse metering event: {e}")
        except Exception as e:
            logger.error(f"Failed to read metering log: {e}", exc_info=True)

        # Sort by occurred_at descending
        events.sort(key=lambda e: e.occurred_at, reverse=True)

        return events[:limit]

    # AuditLog methods

    def log_audit(
        self,
        actor_id: str,
        actor_type: str,
        action: str,
        object_type: str,
        object_id: Optional[str] = None,
        object_ref: Optional[str] = None,
        status: str = "success",
        error_message: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> AuditLog:
        """
        Log an audit event

        Args:
            actor_id: Actor identifier
            actor_type: Actor type ("user", "service", "system")
            action: Action name (e.g., "playbook.run.create")
            object_type: Object type (e.g., "PlaybookRun")
            object_id: Object ID (optional)
            object_ref: Object reference (optional)
            status: Status ("success", "failure", "partial")
            error_message: Error message (optional)
            ip_address: IP address (optional)
            user_agent: User agent (optional)
            metadata: Additional metadata

        Returns:
            AuditLog instance
        """
        event_id = str(uuid.uuid4())

        log = AuditLog(
            event_id=event_id,
            actor_id=actor_id,
            actor_type=actor_type,
            action=action,
            object_type=object_type,
            object_id=object_id,
            object_ref=object_ref,
            status=status,
            error_message=error_message,
            ip_address=ip_address,
            user_agent=user_agent,
            occurred_at=datetime.now(),
            metadata=metadata or {}
        )

        # Append to audit log (NDJSON format)
        self._append_audit_log(log)

        return log

    def _append_audit_log(self, log: AuditLog) -> None:
        """Append audit log to file"""
        logs_path = self.storage.get_logs_path()
        audit_log = logs_path / "audit.ndjson"

        with open(audit_log, "a", encoding="utf-8") as f:
            f.write(json.dumps(log.to_dict(), ensure_ascii=False) + "\n")

    def get_audit_logs(
        self,
        actor_id: Optional[str] = None,
        action: Optional[str] = None,
        object_type: Optional[str] = None,
        object_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 1000
    ) -> List[AuditLog]:
        """
        Get audit logs with filters

        Args:
            actor_id: Filter by actor ID
            action: Filter by action
            object_type: Filter by object type
            object_id: Filter by object ID
            status: Filter by status
            limit: Maximum number of results

        Returns:
            List of AuditLog instances
        """
        logs_path = self.storage.get_logs_path()
        audit_log = logs_path / "audit.ndjson"

        if not audit_log.exists():
            return []

        logs = []
        try:
            with open(audit_log, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)
                        log = AuditLog.from_dict(data)

                        # Apply filters
                        if actor_id and log.actor_id != actor_id:
                            continue
                        if action and log.action != action:
                            continue
                        if object_type and log.object_type != object_type:
                            continue
                        if object_id and log.object_id != object_id:
                            continue
                        if status and log.status != status:
                            continue

                        logs.append(log)
                    except Exception as e:
                        logger.warning(f"Failed to parse audit log: {e}")
        except Exception as e:
            logger.error(f"Failed to read audit log: {e}", exc_info=True)

        # Sort by occurred_at descending
        logs.sort(key=lambda l: l.occurred_at, reverse=True)

        return logs[:limit]

