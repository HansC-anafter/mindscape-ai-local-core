"""Command Bus service for unified command dispatch."""
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime

from ...models.surface import Command, CommandStatus, SurfaceDefinition
from ...services.playbook_run_executor import PlaybookRunExecutor
from ...database.connection_factory import ConnectionFactory
from ...services.stores.postgres.remaining_stores import (
    PostgresCommandsStore,
    PostgresPlaybookExecutionsStore,
)

# Optional import for gate service (cloud service)
try:
    from services.governance.gate_service import GateService
    GATE_SERVICE_AVAILABLE = True
except ImportError:
    GATE_SERVICE_AVAILABLE = False
    GateService = None

logger = logging.getLogger(__name__)


class SurfaceRegistry:
    """Registry for surface definitions."""

    def __init__(self):
        """Initialize surface registry."""
        self.surfaces: Dict[str, SurfaceDefinition] = {}

    def register_surface(self, surface: SurfaceDefinition) -> SurfaceDefinition:
        """
        Register a surface.

        Args:
            surface: Surface definition to register

        Returns:
            Registered surface
        """
        self.surfaces[surface.surface_id] = surface
        logger.info(f"Registered surface: {surface.surface_id}")
        return surface

    def get_surface(self, surface_id: str) -> Optional[SurfaceDefinition]:
        """
        Get surface by ID.

        Args:
            surface_id: Surface ID

        Returns:
            Surface definition or None if not found
        """
        return self.surfaces.get(surface_id)

    def list_surfaces(self) -> List[SurfaceDefinition]:
        """
        List all registered surfaces.

        Returns:
            List of surface definitions
        """
        return list(self.surfaces.values())


class CommandBus:
    """Central command bus for all surfaces."""

    def __init__(self, db_path: str = None):
        """
        Initialize command bus.

        Args:
            db_path: Optional database path (defaults to standard location)
        """
        if db_path is not None:
            logger.warning("CommandBus ignores db_path in Postgres-only mode.")
        db_type = ConnectionFactory().get_db_type()
        if db_type != "postgres":
            raise RuntimeError(
                "SQLite is no longer supported for CommandBus. Configure PostgreSQL."
            )
        self.store = PostgresCommandsStore()
        self.executions_store = PostgresPlaybookExecutionsStore()
        self.playbook_executor = PlaybookRunExecutor()
        self.gate_service = GateService() if GATE_SERVICE_AVAILABLE else None

    async def dispatch_command(self, command: Command) -> Dict[str, Any]:
        """
        Dispatch a command from any surface.

        Args:
            command: Command to dispatch

        Returns:
            Command dispatch result
        """
        # Ensure metadata exists for BYOP/BYOL tracking
        if not command.metadata:
            command.metadata = {}

        # Auto-extract and record BYOP/BYOL fields if present in parameters
        # This allows commands to pass pack_id/card_id via parameters, which will be recorded
        if command.parameters:
            byop_fields = ["pack_id", "card_id", "scope", "playbook_version"]
            for field in byop_fields:
                if field in command.parameters and field not in command.metadata:
                    command.metadata[field] = command.parameters[field]

        # Record command with metadata
        self.store.create_command(command)

        if command.requires_approval:
            command.status = CommandStatus.PENDING
            logger.info(f"Command {command.command_id} requires approval, status set to PENDING")
            return {
                "command_id": command.command_id,
                "status": "pending_approval",
                "message": "Command requires approval"
            }

        return await self._execute_command(command)

    async def approve_command(self, command_id: str) -> Dict[str, Any]:
        """
        Approve a pending command.

        Args:
            command_id: Command ID to approve

        Returns:
            Command execution result
        """
        command = self.store.get_command(command_id)
        if not command:
            raise ValueError(f"Command {command_id} not found")

        if command.status != CommandStatus.PENDING:
            raise ValueError(f"Command {command_id} is not pending (current status: {command.status})")

        command.status = CommandStatus.APPROVED
        self.store.update_command(command_id, {"status": CommandStatus.APPROVED})
        logger.info(f"Command {command_id} approved, executing...")
        return await self._execute_command(command)

    async def reject_command(self, command_id: str, reason: Optional[str] = None) -> Dict[str, Any]:
        """
        Reject a pending command.

        Args:
            command_id: Command ID to reject
            reason: Optional rejection reason

        Returns:
            Rejection confirmation
        """
        command = self.commands.get(command_id)
        if not command:
            raise ValueError(f"Command {command_id} not found")

        if command.status != CommandStatus.PENDING:
            raise ValueError(f"Command {command_id} is not pending (current status: {command.status})")

        command.status = CommandStatus.REJECTED
        self.store.update_command(command_id, {"status": CommandStatus.REJECTED})
        logger.info(f"Command {command_id} rejected: {reason}")
        return {
            "command_id": command_id,
            "status": "rejected",
            "reason": reason
        }

    async def _execute_command(self, command: Command) -> Dict[str, Any]:
        """
        Execute a command.

        Args:
            command: Command to execute

        Returns:
            Execution result
        """
        command.status = CommandStatus.RUNNING
        self.store.update_command(command.command_id, {"status": CommandStatus.RUNNING})
        logger.info(f"Executing command {command.command_id} with intent_code: {command.intent_code}")

        try:
            result = await self.playbook_executor.execute_playbook_run(
                playbook_code=command.intent_code,
                profile_id=command.actor_id,
                inputs=command.parameters,
                workspace_id=command.workspace_id,
                target_language=None,
                variant_id=None
            )

            # Record BYOP/BYOL fields to trace metadata after execution
            # Extract BYOP/BYOL fields from command.metadata
            execution_id = result.get("execution_id") or result.get("result", {}).get("execution_id")
            if execution_id and command.metadata:
                byop_fields = ["pack_id", "card_id", "scope", "playbook_version"]
                byop_metadata = {
                    field: command.metadata[field]
                    for field in byop_fields
                    if field in command.metadata
                }

                if byop_metadata:
                    # Persist BYOP/BYOL fields to execution trace metadata
                    try:
                        self.executions_store.update_execution_metadata(execution_id, byop_metadata)
                        logger.info(
                            f"Command {command.command_id} BYOP/BYOL metadata persisted to execution {execution_id}: {byop_metadata}"
                        )
                    except Exception as e:
                        logger.warning(
                            f"Failed to persist BYOP/BYOL metadata to execution {execution_id}: {e}"
                        )
                        # Fallback: metadata is still in command.metadata and can be retrieved via command_id

            execution_id = result.get("execution_id") or result.get("result", {}).get("execution_id")
            if execution_id:
                command.execution_id = execution_id

            command.status = CommandStatus.COMPLETED
            self.store.update_command(
                command.command_id,
                {
                    "status": CommandStatus.COMPLETED,
                    "execution_id": execution_id
                }
            )
            logger.info(f"Command {command.command_id} completed successfully")

            # Create gates if gate service is available and command requires approval
            if self.gate_service and command.requires_approval:
                self._create_gates_for_execution(
                    execution_id=execution_id,
                    command=command,
                    result=result
                )

            return {
                "command_id": command.command_id,
                "execution_id": execution_id,
                "status": "completed",
                "result": result
            }

        except Exception as e:
            command.status = CommandStatus.FAILED
            self.store.update_command(command.command_id, {"status": CommandStatus.FAILED})
            logger.error(f"Command {command.command_id} failed: {e}", exc_info=True)
            raise

    def get_command(self, command_id: str) -> Optional[Command]:
        """
        Get command by ID.

        Args:
            command_id: Command ID

        Returns:
            Command or None if not found
        """
        return self.store.get_command(command_id)

    def list_commands(
        self,
        workspace_id: Optional[str] = None,
        status: Optional[CommandStatus] = None,
        limit: int = 50
    ) -> list[Command]:
        """
        List commands with filters.

        Args:
            workspace_id: Optional workspace filter
            status: Optional status filter
            limit: Maximum number of results

        Returns:
            List of commands
        """
        return self.store.list_commands(workspace_id=workspace_id, status=status, limit=limit)

    def _create_gates_for_execution(
        self,
        execution_id: str,
        command: Command,
        result: Dict[str, Any]
    ) -> None:
        """
        Create gates for execution if needed.

        Args:
            execution_id: Execution ID
            command: Command that triggered execution
            result: Execution result
        """
        if not self.gate_service:
            return

        # Check if execution has artifacts that need approval
        artifacts = result.get("artifacts", [])
        if not artifacts:
            return

        # Get owner from command metadata
        owner_user_id = command.metadata.get("owner_user_id")
        required_role = "owner" if owner_user_id else "approver"

        for artifact in artifacts:
            artifact_id = artifact.get("artifact_id") or artifact.get("id")
            if not artifact_id:
                continue

            gate = self.gate_service.create_gate(
                execution_id=execution_id,
                trigger={
                    "type": "artifact_ready",
                    "artifact_id": artifact_id
                },
                required_role=required_role,
                required_user_id=owner_user_id,
                candidate_output={
                    "artifact_id": artifact_id,
                    "provenance": {
                        "command_id": command.command_id,
                        "source_surface": command.source_surface,
                        "lens_stack": command.metadata.get("lens_stack", []),
                        "policy_set_id": command.metadata.get("policy_set_id")
                    }
                }
            )
            logger.info(f"Created gate {gate['gate_id']} for artifact {artifact_id}")
