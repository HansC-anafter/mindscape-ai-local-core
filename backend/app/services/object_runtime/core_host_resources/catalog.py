"""Catalog definitions for core-owned host resource objects."""

from __future__ import annotations

import copy
from typing import Any

OWNER_PACK = "local_core"

HOST_RESOURCE_LANE_KIND = "host_resource_lane"
WORKSPACE_RESOURCE_ALLOCATION_KIND = "workspace_resource_allocation"
RESOURCE_BUDGET_POLICY_KIND = "resource_budget_policy"
ROUTE_RESERVATION_KIND = "route_reservation"

_INDEXER_BASE = "backend.app.services.object_runtime.core_host_resource_objects"

_BUDGET_POLICIES: list[dict[str, Any]] = [
    {
        "policy_id": "comfyui_visual_iteration_default",
        "label": "ComfyUI Visual Iteration Default",
        "description": "Default bounded budget for agentic ComfyUI visual iteration.",
        "max_iterations": 4,
        "max_outputs": 8,
        "max_parallel_reservations": 1,
        "allowed_lane_kinds": ["comfyui"],
        "requires_route_reservation": True,
    },
    {
        "policy_id": "comfyui_visual_iteration_strict",
        "label": "ComfyUI Visual Iteration Strict",
        "description": "Tighter budget for fixture and smoke validation runs.",
        "max_iterations": 2,
        "max_outputs": 4,
        "max_parallel_reservations": 1,
        "allowed_lane_kinds": ["comfyui"],
        "requires_route_reservation": True,
    },
]

_CORE_CATALOG_ENTRIES: list[dict[str, Any]] = [
    {
        "owner_pack": OWNER_PACK,
        "object_kind": HOST_RESOURCE_LANE_KIND,
        "display_name": "Host Resource Lane",
        "canonical_schema": "local_core.host_resources.HostResourceLane",
        "id_field": "lane_id",
        "summary_fields": [
            "lane_id",
            "label",
            "kind",
            "state",
            "resource_flavor",
        ],
        "supports": ["summary", "detail", "relations", "actions", "graph_projection"],
        "granularity": "workspace",
        "selector_families": ["object_root"],
        "indexer_backend": f"{_INDEXER_BASE}:sync_host_resource_lane_index",
        "mention_fields": ["lane_id", "label", "kind", "resource_flavor"],
        "owner_surface_patterns": ["/api/v1/host-resources/lanes"],
        "resolver_capabilities": {
            "summary": True,
            "detail": False,
            "relations": False,
            "actions": True,
        },
        "resolver_backends": {
            "summary_backend": f"{_INDEXER_BASE}:resolve_host_resource_lane_summary",
            "detail_backend": None,
            "relations_backend": None,
            "actions_backend": f"{_INDEXER_BASE}:resolve_host_resource_lane_actions",
        },
        "meeting_projection_capabilities": {"available": False, "verbs": []},
        "materializer_capabilities": {
            "available": False,
            "verbs": [],
            "write_modes": [],
            "output_types": [],
        },
        "graph_projection_capabilities": {
            "available": True,
            "node_kinds": ["host_resource_lane"],
            "relation_kinds": ["allocates_capacity_for", "requires_reservation"],
        },
        "affordances": [
            {
                "verb": "preview_route_intent",
                "label": "Preview route intent",
                "description": "Build a non-destructive host resource route preview for this lane.",
                "object_kinds": [HOST_RESOURCE_LANE_KIND],
                "input_schema": {"type": "object"},
                "output_schema": {"type": "object"},
                "required_roles": ["target"],
                "write_modes": ["read_only"],
                "planner_backend": f"{_INDEXER_BASE}:plan_preview_route_intent",
                "executor_backend": f"{_INDEXER_BASE}:execute_preview_route_intent",
            }
        ],
    },
    {
        "owner_pack": OWNER_PACK,
        "object_kind": WORKSPACE_RESOURCE_ALLOCATION_KIND,
        "display_name": "Workspace Resource Allocation",
        "canonical_schema": "local_core.host_resources.WorkspaceResourceAllocation",
        "id_field": "allocation_id",
        "summary_fields": [
            "allocation_id",
            "workspace_id",
            "lane_id",
            "state",
            "max_parallel_task_claims",
        ],
        "supports": ["summary", "detail", "relations", "graph_projection"],
        "granularity": "workspace",
        "selector_families": ["object_root"],
        "indexer_backend": f"{_INDEXER_BASE}:sync_workspace_resource_allocation_index",
        "mention_fields": [
            "allocation_id",
            "lane_id",
            "label",
            "queue_shard",
            "task_family",
        ],
        "owner_surface_patterns": ["/api/v1/host-resources/workspace-allocations"],
        "resolver_capabilities": {
            "summary": True,
            "detail": False,
            "relations": False,
            "actions": False,
        },
        "resolver_backends": {
            "summary_backend": f"{_INDEXER_BASE}:resolve_workspace_resource_allocation_summary",
            "detail_backend": None,
            "relations_backend": None,
            "actions_backend": None,
        },
        "meeting_projection_capabilities": {"available": False, "verbs": []},
        "materializer_capabilities": {
            "available": False,
            "verbs": [],
            "write_modes": [],
            "output_types": [],
        },
        "graph_projection_capabilities": {
            "available": True,
            "node_kinds": ["workspace_resource_allocation"],
            "relation_kinds": ["allocates_lane"],
        },
        "affordances": [],
    },
    {
        "owner_pack": OWNER_PACK,
        "object_kind": RESOURCE_BUDGET_POLICY_KIND,
        "display_name": "Resource Budget Policy",
        "canonical_schema": "local_core.host_resources.ResourceBudgetPolicy",
        "id_field": "policy_id",
        "summary_fields": [
            "policy_id",
            "label",
            "max_iterations",
            "max_outputs",
            "requires_route_reservation",
        ],
        "supports": ["summary", "detail", "relations", "graph_projection"],
        "granularity": "workspace",
        "selector_families": ["object_root"],
        "indexer_backend": f"{_INDEXER_BASE}:sync_resource_budget_policy_index",
        "mention_fields": ["policy_id", "label", "description"],
        "owner_surface_patterns": ["/api/v1/workspace/{workspace_id}/object-runtime/catalog"],
        "resolver_capabilities": {
            "summary": True,
            "detail": False,
            "relations": False,
            "actions": False,
        },
        "resolver_backends": {
            "summary_backend": f"{_INDEXER_BASE}:resolve_resource_budget_policy_summary",
            "detail_backend": None,
            "relations_backend": None,
            "actions_backend": None,
        },
        "meeting_projection_capabilities": {"available": False, "verbs": []},
        "materializer_capabilities": {
            "available": False,
            "verbs": [],
            "write_modes": [],
            "output_types": [],
        },
        "graph_projection_capabilities": {
            "available": True,
            "node_kinds": ["resource_budget_policy"],
            "relation_kinds": ["bounds_resource_run"],
        },
        "affordances": [],
    },
    {
        "owner_pack": OWNER_PACK,
        "object_kind": ROUTE_RESERVATION_KIND,
        "display_name": "Route Reservation",
        "canonical_schema": "local_core.host_resources.RouteReservation",
        "id_field": "reservation_id",
        "summary_fields": [
            "reservation_id",
            "state",
            "target_lane",
            "expires_at",
            "workspace_id",
        ],
        "supports": ["summary", "detail", "relations", "graph_projection"],
        "granularity": "workspace",
        "selector_families": ["object_root"],
        "indexer_backend": f"{_INDEXER_BASE}:sync_route_reservation_index",
        "mention_fields": ["reservation_id", "target_lane", "state"],
        "owner_surface_patterns": ["/api/v1/host-resources/route-reservations"],
        "resolver_capabilities": {
            "summary": True,
            "detail": False,
            "relations": False,
            "actions": False,
        },
        "resolver_backends": {
            "summary_backend": f"{_INDEXER_BASE}:resolve_route_reservation_summary",
            "detail_backend": None,
            "relations_backend": None,
            "actions_backend": None,
        },
        "meeting_projection_capabilities": {"available": False, "verbs": []},
        "materializer_capabilities": {
            "available": False,
            "verbs": [],
            "write_modes": [],
            "output_types": [],
        },
        "graph_projection_capabilities": {
            "available": True,
            "node_kinds": ["route_reservation"],
            "relation_kinds": ["reserves_lane"],
        },
        "affordances": [],
    },
]


def list_budget_policies() -> list[dict[str, Any]]:
    return copy.deepcopy(_BUDGET_POLICIES)


def list_core_object_catalog_entries() -> list[dict[str, Any]]:
    return copy.deepcopy(_CORE_CATALOG_ENTRIES)


__all__ = [
    "OWNER_PACK",
    "HOST_RESOURCE_LANE_KIND",
    "WORKSPACE_RESOURCE_ALLOCATION_KIND",
    "RESOURCE_BUDGET_POLICY_KIND",
    "ROUTE_RESERVATION_KIND",
    "list_budget_policies",
    "list_core_object_catalog_entries",
]
