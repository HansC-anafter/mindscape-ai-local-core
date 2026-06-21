from typing import Any, Dict, List, Optional, Tuple

from . import settings
from .models import ValidationResult


def validate_execution(
    session: Any,
    timeout: int,
    base_url: str,
    playbook_code: str,
    capability: str,
) -> List[ValidationResult]:
    """Validate playbook execution with mock data."""
    results = []

    if not settings.LLM_MOCK:
        results.append(
            ValidationResult(
                check_name="execution_mock_mode",
                passed=True,
                message="LLM_MOCK not enabled, skipping execution test",
            )
        )
        return results

    workspace_id, should_continue = _find_or_create_workspace(
        session=session,
        timeout=timeout,
        base_url=base_url,
        playbook_code=playbook_code,
        results=results,
    )
    if not should_continue:
        return results

    should_cleanup = _execute_playbook(
        session=session,
        timeout=timeout,
        base_url=base_url,
        playbook_code=playbook_code,
        workspace_id=workspace_id,
        results=results,
    )
    if should_cleanup and workspace_id:
        _cleanup_workspace(
            session=session,
            timeout=timeout,
            base_url=base_url,
            workspace_id=workspace_id,
            results=results,
        )
    return results


def _find_or_create_workspace(
    session: Any,
    timeout: int,
    base_url: str,
    playbook_code: str,
    results: List[ValidationResult],
) -> Tuple[Optional[str], bool]:
    workspace_id = None
    try:
        resp = session.get(
            f"{base_url}/api/v1/workspaces",
            params={
                "owner_user_id": settings.OWNER_USER_ID,
                "limit": 100,
                "include_system": "true",
            },
            timeout=timeout,
        )
        if resp.status_code == 200:
            workspaces = resp.json()
            if isinstance(workspaces, list):
                for ws in workspaces:
                    if ws.get("title") == f"Validate: {playbook_code}":
                        workspace_id = ws.get("id")
                        results.append(
                            ValidationResult(
                                check_name="execution_find_workspace",
                                passed=True,
                                message=f"Reusing existing workspace: {workspace_id}",
                            )
                        )
                        break

        if not workspace_id:
            resp = session.post(
                f"{base_url}/api/v1/workspaces",
                params={"owner_user_id": settings.OWNER_USER_ID},
                json={
                    "title": f"Validate: {playbook_code}",
                    "description": "Automated validation",
                    "is_system": True,
                },
                timeout=timeout,
            )
            if resp.status_code not in [200, 201]:
                results.append(
                    ValidationResult(
                        check_name="execution_create_workspace",
                        passed=False,
                        message=f"Failed to create workspace: {resp.status_code}",
                    )
                )
                return None, False

            workspace = resp.json()
            workspace_id = workspace.get("id")
            results.append(
                ValidationResult(
                    check_name="execution_create_workspace",
                    passed=True,
                    message=f"Created workspace: {workspace_id}",
                )
            )

    except Exception as e:
        results.append(
            ValidationResult(
                check_name="execution_create_workspace",
                passed=False,
                message=f"Exception: {e}",
            )
        )
        return None, False

    return workspace_id, True


def _execute_playbook(
    session: Any,
    timeout: int,
    base_url: str,
    playbook_code: str,
    workspace_id: str,
    results: List[ValidationResult],
) -> bool:
    try:
        resp = session.post(
            f"{base_url}/api/v1/playbooks/execute/start",
            params={"playbook_code": playbook_code, "workspace_id": workspace_id},
            json={"inputs": {}},
            timeout=timeout,
        )

        if resp.status_code != 200:
            results.append(
                ValidationResult(
                    check_name="execution_api_call",
                    passed=False,
                    message=f"API returned {resp.status_code}: {resp.text[:200]}",
                )
            )
            return False

        result = resp.json()

    except Exception as e:
        results.append(
            ValidationResult(
                check_name="execution_api_call",
                passed=False,
                message=f"Exception: {e}",
            )
        )
        return False

    results.append(
        ValidationResult(
            check_name="execution_api_call",
            passed=True,
            message="API call succeeded",
        )
    )
    _append_execution_status(result, results)
    return True


def _append_execution_status(
    result: Dict[str, Any], results: List[ValidationResult]
) -> None:
    status = result.get("status") or result.get("execution_status")
    execution_id = result.get("execution_id")

    if status == "completed":
        results.append(
            ValidationResult(
                check_name="execution_status_critical",
                passed=True,
                message=(
                    "Playbook completed successfully "
                    f"(execution_id: {execution_id})"
                ),
            )
        )
    elif status == "failed":
        error = result.get("error", "Unknown error")
        steps = result.get("steps", {})
        step_errors = []
        for step_id, step_result in steps.items():
            if isinstance(step_result, dict) and step_result.get("status") == "error":
                step_errors.append(f"{step_id}: {step_result.get('error', 'unknown')}")

        results.append(
            ValidationResult(
                check_name="execution_status_critical",
                passed=False,
                message=f"Playbook failed: {error}",
                details={"step_errors": step_errors},
            )
        )
    else:
        results.append(
            ValidationResult(
                check_name="execution_status_critical",
                passed=True,
                message=f"Playbook status: {status} (execution_id: {execution_id})",
            )
        )


def _cleanup_workspace(
    session: Any,
    timeout: int,
    base_url: str,
    workspace_id: str,
    results: List[ValidationResult],
) -> None:
    try:
        resp = session.get(
            f"{base_url}/api/v1/workspaces/{workspace_id}", timeout=timeout
        )
        if resp.status_code == 200:
            ws_data = resp.json()
            is_validation = ws_data.get("title", "").startswith(
                "Validate:"
            ) or ws_data.get("is_system", False)
            if is_validation:
                delete_resp = session.delete(
                    f"{base_url}/api/v1/workspaces/{workspace_id}",
                    timeout=timeout,
                )
                if delete_resp.status_code in [200, 204]:
                    results.append(
                        ValidationResult(
                            check_name="execution_cleanup_workspace",
                            passed=True,
                            message=(
                                "Cleaned up validation workspace: "
                                f"{workspace_id}"
                            ),
                        )
                    )
                else:
                    results.append(
                        ValidationResult(
                            check_name="execution_cleanup_workspace",
                            passed=True,
                            message=(
                                "Failed to cleanup workspace (non-critical): "
                                f"{delete_resp.status_code}"
                            ),
                        )
                    )
    except Exception as e:
        results.append(
            ValidationResult(
                check_name="execution_cleanup_workspace",
                passed=True,
                message=f"Cleanup exception (non-critical): {e}",
            )
        )
