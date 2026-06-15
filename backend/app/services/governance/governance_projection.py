"""Projection helpers for governance store query results."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Tuple

DeserializeJson = Callable[..., Any]


def _mapping(row: Any) -> Mapping[str, Any]:
    return row._mapping if hasattr(row, "_mapping") else row


def _temporal_value(value: Any) -> str:
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def parse_iso_datetime(
    value: Optional[str],
    *,
    logger: logging.Logger,
) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        logger.warning(f"Invalid datetime filter: {value} ({exc})")
        return None


def calculate_rate(rejected: Optional[int], total: Optional[int]) -> float:
    if not total:
        return 0.0
    return (float(rejected or 0) / float(total)) * 100.0


def map_decision_row(
    row: Any,
    *,
    deserialize_json: DeserializeJson,
) -> Dict[str, Any]:
    data = _mapping(row)
    metadata_payload = deserialize_json(data.get("metadata"), default={})
    timestamp_val = data.get("timestamp")
    return {
        "decision_id": data.get("decision_id"),
        "timestamp": _temporal_value(timestamp_val),
        "layer": data.get("layer"),
        "approved": bool(data.get("approved")),
        "reason": data.get("reason"),
        "playbook_code": data.get("playbook_code"),
        "metadata": metadata_payload or {},
    }


def map_execution_decision_row(
    row: Any,
    *,
    deserialize_json: DeserializeJson,
) -> Dict[str, Any]:
    data = _mapping(row)
    decision = map_decision_row(row, deserialize_json=deserialize_json)
    decision.update(
        {
            "workspace_id": data.get("workspace_id"),
            "execution_id": data.get("execution_id"),
        }
    )
    return decision


def build_cost_usage_summary(
    current_usage: float,
    trend_rows: Iterable[Any],
    breakdown_playbook_rows: Iterable[Any],
    breakdown_model_rows: Iterable[Any],
) -> Tuple[float, List[Dict[str, Any]], Dict[str, Any]]:
    trend = [
        {"date": _temporal_value(row[0]), "cost": float(row[1])}
        for row in trend_rows
    ]
    breakdown = {
        "by_playbook": {row[0]: float(row[1]) for row in breakdown_playbook_rows},
        "by_model": {row[0]: float(row[1]) for row in breakdown_model_rows},
    }
    return float(current_usage), trend, breakdown


def build_governance_metrics(
    rejection_rows: Iterable[Any],
    cost_trend_rows: Iterable[Any],
    violation_rows: Iterable[Any],
    preflight_rows: Iterable[Any],
    *,
    deserialize_json: DeserializeJson,
) -> Tuple[Dict[str, float], List[Dict[str, Any]], Dict[str, Any], Dict[str, int]]:
    layer_totals: Dict[str, int] = {}
    layer_rejected: Dict[str, int] = {}
    for row in rejection_rows:
        layer_totals[row[0]] = int(row[1] or 0)
        layer_rejected[row[0]] = int(row[2] or 0)

    rejection_rate = {
        "cost": calculate_rate(layer_rejected.get("cost"), layer_totals.get("cost")),
        "node": calculate_rate(layer_rejected.get("node"), layer_totals.get("node")),
        "policy": calculate_rate(layer_rejected.get("policy"), layer_totals.get("policy")),
        "preflight": calculate_rate(
            layer_rejected.get("preflight"),
            layer_totals.get("preflight"),
        ),
        "overall": calculate_rate(sum(layer_rejected.values()), sum(layer_totals.values())),
    }

    cost_trend = [
        {"date": _temporal_value(row[0]), "cost": float(row[1])}
        for row in cost_trend_rows
    ]

    violation_frequency = {
        "policy": {
            "role_violation": 0,
            "data_domain_violation": 0,
            "pii_violation": 0,
        },
        "node": {
            "blacklist": 0,
            "risk_label": 0,
            "throttle": 0,
        },
    }
    for row in violation_rows:
        layer = row[0]
        reason = (row[1] or "").lower()
        count = int(row[2] or 0)
        if layer == "policy" and "role" in reason:
            violation_frequency["policy"]["role_violation"] += count
        elif layer == "policy" and "domain" in reason:
            violation_frequency["policy"]["data_domain_violation"] += count
        elif layer == "policy" and "pii" in reason:
            violation_frequency["policy"]["pii_violation"] += count
        elif layer == "node" and "blacklist" in reason:
            violation_frequency["node"]["blacklist"] += count
        elif layer == "node" and "risk" in reason:
            violation_frequency["node"]["risk_label"] += count
        elif layer == "node" and ("throttle" in reason or "limit" in reason):
            violation_frequency["node"]["throttle"] += count

    preflight_failure_reasons = {
        "missing_inputs": 0,
        "missing_credentials": 0,
        "environment_issues": 0,
    }
    for row in preflight_rows:
        metadata_payload = deserialize_json(row[0], default={})
        count = int(row[1] or 0)
        if metadata_payload.get("missing_inputs"):
            preflight_failure_reasons["missing_inputs"] += count
        if metadata_payload.get("missing_credentials"):
            preflight_failure_reasons["missing_credentials"] += count
        if metadata_payload.get("environment_issues"):
            preflight_failure_reasons["environment_issues"] += count

    return rejection_rate, cost_trend, violation_frequency, preflight_failure_reasons
