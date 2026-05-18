from .base import *
from .payload import build_dispatch_payload


class PollingResponseMixin:

    def _build_runtime_exec_response(
        self,
        *,
        execution_id: str,
        result_data: Dict[str, Any],
        elapsed: float,
        recovered_from_db: bool = False,
    ) -> RuntimeExecResponse:
        output = result_data.get("output", "")
        status = result_data.get("status", "completed")
        error = result_data.get("error")
        agent_metadata = {
            "transport": "polling",
            "execution_id": execution_id,
            "status": status,
        }
        if recovered_from_db:
            agent_metadata["recovered_from_db"] = True

        return RuntimeExecResponse(
            success=(status == "completed"),
            output=output or "Task completed.",
            duration_seconds=elapsed,
            exit_code=0 if status == "completed" else -1,
            error=error,
            agent_metadata=agent_metadata,
        )

    def _recover_response_from_db(
        self,
        *,
        execution_id: str,
        elapsed: float,
    ) -> Optional[RuntimeExecResponse]:
        try:
            from backend.app.services.stores.tasks_store import TasksStore
            from backend.app.models.workspace import TaskStatus

            db_task = TasksStore().get_task(execution_id)
            if db_task and db_task.status == TaskStatus.SUCCEEDED:
                logger.info(
                    f"[{self.RUNTIME_NAME}] DB recovery: found completed "
                    f"task {execution_id}"
                )
                result_data = db_task.result or {}
                return self._build_runtime_exec_response(
                    execution_id=execution_id,
                    result_data=result_data,
                    elapsed=elapsed,
                    recovered_from_db=True,
                )
            if db_task and db_task.status == TaskStatus.FAILED:
                logger.info(
                    f"[{self.RUNTIME_NAME}] DB recovery: found failed "
                    f"task {execution_id}"
                )
                return RuntimeExecResponse(
                    success=False,
                    output="",
                    duration_seconds=elapsed,
                    exit_code=1,
                    error=db_task.error or "Task failed (recovered from DB).",
                    agent_metadata={
                        "transport": "polling",
                        "execution_id": execution_id,
                        "status": "failed",
                        "recovered_from_db": True,
                    },
                )
        except Exception as db_err:
            logger.warning(
                f"[{self.RUNTIME_NAME}] DB recovery check failed for "
                f"{execution_id}: {db_err}"
            )

        return None
