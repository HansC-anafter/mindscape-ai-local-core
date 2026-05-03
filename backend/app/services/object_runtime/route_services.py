"""Compatibility facade for object runtime route services."""

from __future__ import annotations

from typing import Any

from backend.app.services.object_runtime import dependencies as _dependencies
from backend.app.services.object_runtime import common as _common
from backend.app.services.object_runtime import summary_service as _summary_service
from backend.app.services.object_runtime import catalog_service as _catalog_service
from backend.app.services.object_runtime import action_helpers as _action_helpers
from backend.app.services.object_runtime import action_service as _action_service
from backend.app.services.object_runtime import selection_service as _selection_service
from backend.app.services.object_runtime import meeting_projection as _meeting_projection
from backend.app.services.object_runtime import materialization_service as _materialization_service
from backend.app.services.object_runtime import meeting_attach_service as _meeting_attach_service
from backend.app.services.object_runtime import graph_service as _graph_service

_MODULES = [
    _dependencies,
    _common,
    _summary_service,
    _catalog_service,
    _action_helpers,
    _action_service,
    _selection_service,
    _meeting_projection,
    _materialization_service,
    _meeting_attach_service,
    _graph_service,
]

_ALIAS_OWNERS = {
    '_action_relation_kind_for_role': [_action_helpers],
    '_attach_action': [_selection_service],
    '_build_actions': [_selection_service],
    '_build_catalog_summary': [_summary_service],
    '_build_materializer_context_objects': [_meeting_projection],
    '_build_object_action_closure_relations': [_action_helpers],
    '_build_object_action_plan': [_action_helpers],
    '_build_object_action_plan_relations': [_action_helpers],
    '_build_object_ref': [_common],
    '_build_object_summary': [_summary_service],
    '_build_session_attachment_metadata': [_meeting_attach_service],
    '_closure_relation_kind_for_role': [_action_helpers],
    '_coerce_guidance_ref': [_graph_service],
    '_coerce_materialized_ref_payload': [_common],
    '_coerce_materializer_errors': [_common],
    '_coerce_read_object_ref': [_common],
    '_coerce_relation_target_ref': [_graph_service],
    '_coerce_request_plan': [_common],
    '_coerce_route_list': [_common],
    '_coerce_summary_from_backend_payload': [_summary_service],
    '_default_meeting_projection_payload': [_meeting_projection],
    '_default_mention_token': [_catalog_service],
    '_ensure_workspace_exists': [_dependencies],
    '_entry_supports_affordance': [_action_helpers],
    '_execute_materializer_backend': [_materialization_service],
    '_extract_invoke_affordance_payload': [_action_helpers],
    '_extract_invoke_entries': [_action_helpers],
    '_extract_invoke_plan_payload': [_action_helpers],
    '_first_text': [_summary_service],
    '_get_meeting_session_store': [_dependencies],
    '_get_object_catalog_registry': [_dependencies],
    '_get_object_instance_registry_store': [_dependencies],
    '_get_object_meeting_attachment_service': [_dependencies],
    '_get_object_relation_registry_store': [_dependencies],
    '_get_tasks_store': [_dependencies],
    '_get_workspace_store': [_dependencies],
    '_invoke_backend_callable': [_common],
    '_materialize_target_outcome': [_materialization_service],
    '_normalize_graph_relations': [_graph_service],
    '_normalize_guidance_cards': [_graph_service],
    '_normalize_materializer_outcome': [_materialization_service],
    '_open_owner_surface_action': [_selection_service],
    '_pack_id_from_entries': [_action_helpers],
    '_parse_mindscape_uri': [_common],
    '_persist_object_action_invocation_task': [_action_helpers],
    '_recommend_action': [_selection_service],
    '_relation_record_to_graph_relation': [_graph_service],
    '_resolve_attach_ref': [_meeting_projection],
    '_resolve_graph_projection': [_graph_service],
    '_resolve_local_core_root': [_dependencies],
    '_resolve_meeting_projection_payload': [_meeting_projection],
    '_resolve_runtime_summary': [_summary_service],
    '_score_mention_record': [_catalog_service],
    '_select_action_affordance': [_action_helpers],
    '_select_graph_projection_backend': [_graph_service],
    '_select_materializer_backend': [_materialization_service],
    '_select_meeting_projection_backend': [_meeting_projection],
    '_select_summary_backend': [_summary_service],
    '_split_object_uri': [_common],
    '_string_list': [_common],
    '_text': [_common],
    '_to_catalog_entry': [_common],
    '_to_mention_completion_item': [_catalog_service],
    '_upsert_meeting_session_metadata': [_meeting_attach_service],
    '_validate_catalog_object_ref': [_common],
    '_validate_object_ref_identity': [_common],
    '_validate_selection_hints': [_selection_service],
    'get_object_index_sync_service': [_catalog_service],
    'get_object_index_sync_status': [_catalog_service],
}

for _name, _owners in _ALIAS_OWNERS.items():
    globals()[_name] = getattr(_owners[0], _name)


def _sync_module_aliases() -> None:
    for name in _ALIAS_OWNERS:
        value = globals()[name]
        for module in _MODULES:
            if hasattr(module, name):
                setattr(module, name, value)


def _wrap(module: Any, name: str):
    async def _wrapped(*args: Any, **kwargs: Any):
        _sync_module_aliases()
        return await getattr(module, name)(*args, **kwargs)

    _wrapped.__name__ = name
    return _wrapped

get_workspace_object_catalog = _wrap(_catalog_service, 'get_workspace_object_catalog')
index_workspace_objects = _wrap(_catalog_service, 'index_workspace_objects')
sync_workspace_object_index = _wrap(_catalog_service, 'sync_workspace_object_index')
get_workspace_object_index_sync_status = _wrap(_catalog_service, 'get_workspace_object_index_sync_status')
index_workspace_object_relations = _wrap(_catalog_service, 'index_workspace_object_relations')
search_workspace_object_relations = _wrap(_catalog_service, 'search_workspace_object_relations')
search_workspace_objects = _wrap(_catalog_service, 'search_workspace_objects')
read_workspace_object = _wrap(_catalog_service, 'read_workspace_object')
complete_workspace_objects = _wrap(_catalog_service, 'complete_workspace_objects')
plan_workspace_object_action = _wrap(_action_service, 'plan_workspace_object_action')
invoke_workspace_object_action = _wrap(_action_service, 'invoke_workspace_object_action')
close_workspace_object_action = _wrap(_action_service, 'close_workspace_object_action')
resolve_workspace_selection = _wrap(_selection_service, 'resolve_workspace_selection')
attach_objects_to_meeting = _wrap(_meeting_attach_service, 'attach_objects_to_meeting')
materialize_object_outcome = _wrap(_materialization_service, 'materialize_object_outcome')
project_object_graph = _wrap(_graph_service, 'project_object_graph')

__all__ = sorted(set(list(_ALIAS_OWNERS) + ['get_workspace_object_catalog', 'index_workspace_objects', 'sync_workspace_object_index', 'get_workspace_object_index_sync_status', 'index_workspace_object_relations', 'search_workspace_object_relations', 'search_workspace_objects', 'read_workspace_object', 'complete_workspace_objects', 'plan_workspace_object_action', 'invoke_workspace_object_action', 'close_workspace_object_action', 'resolve_workspace_selection', 'attach_objects_to_meeting', 'materialize_object_outcome', 'project_object_graph'] + ["_sync_module_aliases"]))
