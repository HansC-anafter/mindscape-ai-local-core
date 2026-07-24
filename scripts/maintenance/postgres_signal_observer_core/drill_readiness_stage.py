"""Bounded readiness-stage aggregation and exact receipt projection."""

from __future__ import annotations

from typing import Any, Callable, Mapping


def empty_stage() -> dict[str, Any]:
    return {
        "attempted": False,
        "attempt_count": 0,
        "success_count": 0,
        "passed": False,
        "last_result": None,
    }


def empty_psql_stage(empty_stage: Mapping[str, Any]) -> dict[str, Any]:
    return {
        **empty_stage,
        "prior_terminal_attempt_index": None,
        "prior_terminal_result": None,
    }


def replace_psql_result(
    stage: dict[str, Any], result: Mapping[str, Any]
) -> None:
    previous = stage["last_result"]
    if isinstance(previous, Mapping) and previous.get("status") in {
        "terminal_nonzero",
        "result_invalid",
    }:
        stage["prior_terminal_attempt_index"] = stage["attempt_count"] - 1
        stage["prior_terminal_result"] = dict(previous)
    stage["last_result"] = dict(result)
    if result.get("status") == "terminal_zero":
        stage["prior_terminal_attempt_index"] = None
        stage["prior_terminal_result"] = None


def project_readiness_stage(
    stage_name: str,
    source: object,
    *,
    role: str,
    project_result: Callable[..., dict[str, Any] | None],
    capture_keys: frozenset[str],
) -> dict[str, Any] | None:
    if not isinstance(source, Mapping):
        return None
    attempted = source.get("attempted")
    attempts = source.get("attempt_count")
    successes = source.get("success_count")
    passed = source.get("passed")
    raw_result = source.get("last_result")
    result = project_result(stage_name, raw_result, role=role)
    prior_index = source.get("prior_terminal_attempt_index")
    raw_prior = source.get("prior_terminal_result")
    prior = (
        project_result(stage_name, raw_prior, role=role)
        if raw_prior is not None
        else None
    )
    psql_prior_valid = bool(
        stage_name != "psql_select_one"
        or role != "postgres"
        or (
            set(source)
            == {
                "attempted",
                "attempt_count",
                "success_count",
                "passed",
                "last_result",
                "prior_terminal_attempt_index",
                "prior_terminal_result",
            }
            and (
                (
                    (passed is True or (type(attempts) is int and attempts <= 1))
                    and prior_index is None
                    and raw_prior is None
                )
                or (
                    passed is False
                    and type(attempts) is int
                    and attempts >= 2
                    and type(prior_index) is int
                    and prior_index == attempts - 1
                    and isinstance(raw_prior, Mapping)
                    and prior is not None
                    and prior.get("status") in {"terminal_nonzero", "result_invalid"}
                    and set(raw_prior) == set(prior)
                    and (
                        prior.get("status") != "terminal_nonzero"
                        or (
                            isinstance(raw_prior.get("terminal_capture"), Mapping)
                            and set(raw_prior["terminal_capture"]) == capture_keys
                        )
                    )
                )
            )
        )
    )
    if (
        type(attempted) is not bool
        or type(attempts) is not int
        or type(successes) is not int
        or type(passed) is not bool
        or attempts < 0
        or not 0 <= successes <= attempts
        or attempted != (attempts > 0)
        or passed != (successes > 0)
        or (
            result is not None
            and result.get("status") == "terminal_zero"
            and successes == 0
        )
        or (
            stage_name != "container_readback"
            and result is not None
            and result.get("status") != "terminal_zero"
            and successes >= attempts
        )
        or (attempted and result is None)
        or (not attempted and raw_result is not None)
        or not psql_prior_valid
        or (
            role == "pgbouncer"
            and set(source)
            != {"attempted", "attempt_count", "success_count", "passed", "last_result"}
        )
        or (
            role == "pgbouncer"
            and isinstance(raw_result, Mapping)
            and isinstance(result, Mapping)
            and set(raw_result) != set(result)
        )
    ):
        return None
    return {
        "attempted": attempted,
        "attempt_count": attempts,
        "success_count": successes,
        "passed": passed,
        "last_result": result,
        **(
            {
                "prior_terminal_attempt_index": prior_index,
                "prior_terminal_result": prior,
            }
            if stage_name == "psql_select_one" and role == "postgres"
            else {}
        ),
    }
