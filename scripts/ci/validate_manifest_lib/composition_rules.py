from typing import Any, Dict, List

from .models import ValidationError
from .patterns import (
    AOL_BACKEND_PATTERN,
    RUNTIME_LOCK_TOKEN_PATTERN,
    _manifest_error,
    _manifest_warning,
)


def _validate_pack_backend(
    *,
    capability_code: str,
    field: str,
    backend: object,
    errors: List[ValidationError],
    warnings: List[ValidationError],
) -> None:
    if not isinstance(backend, str) or not AOL_BACKEND_PATTERN.match(backend):
        errors.append(
            _manifest_error(
                capability_code,
                field,
                "backend must be a pack-owned backend import path",
            )
        )
        return
    module_path, _symbol = backend.split(":", 1)
    if capability_code and not (
        module_path.startswith(f"capabilities.{capability_code}.")
        or module_path.startswith(f"app.capabilities.{capability_code}.")
    ):
        warnings.append(
            _manifest_warning(
                capability_code,
                field,
                f"backend does not appear to be owned by pack '{capability_code}'",
            )
        )


def _validate_composition_graph_nodes(
    manifest: Dict[str, Any],
    capability_code: str,
    errors: List[ValidationError],
    warnings: List[ValidationError],
) -> None:
    contract = manifest.get("composition_graph_nodes")
    if contract is None:
        return
    if not isinstance(contract, dict):
        errors.append(
            _manifest_error(
                capability_code,
                "composition_graph_nodes",
                "composition_graph_nodes must be an object",
            )
        )
        return
    if contract.get("enabled") is not True:
        return
    nodes = contract.get("nodes")
    if not isinstance(nodes, list):
        errors.append(
            _manifest_error(
                capability_code,
                "composition_graph_nodes.nodes",
                "composition_graph_nodes.nodes must be a list",
            )
        )
        return
    for index, node in enumerate(nodes):
        field_prefix = f"composition_graph_nodes.nodes[{index}]"
        if not isinstance(node, dict):
            errors.append(
                _manifest_error(
                    capability_code,
                    field_prefix,
                    "node must be an object",
                )
            )
            continue
        if node.get("id") == "object_reference":
            errors.append(
                _manifest_error(
                    capability_code,
                    f"{field_prefix}.id",
                    "pack node id cannot be object_reference",
                )
            )
        _validate_composition_graph_node_ports(
            capability_code,
            field_prefix,
            node.get("input_ports"),
            "input",
            errors,
        )
        _validate_composition_graph_node_ports(
            capability_code,
            field_prefix,
            node.get("output_ports"),
            "output",
            errors,
        )
        payload_schema = node.get("payload_schema", {})
        if payload_schema is not None and not isinstance(payload_schema, dict):
            errors.append(
                _manifest_error(
                    capability_code,
                    f"{field_prefix}.payload_schema",
                    "payload_schema must be an object",
                )
            )
        executor = node.get("executor")
        if not isinstance(executor, dict):
            errors.append(
                _manifest_error(
                    capability_code,
                    f"{field_prefix}.executor",
                    "executor must be an object",
                )
            )
        else:
            _validate_pack_backend(
                capability_code=capability_code,
                field=f"{field_prefix}.executor.backend",
                backend=executor.get("backend"),
                errors=errors,
                warnings=warnings,
            )
        option_sources = node.get("option_sources", {})
        if option_sources is not None:
            if not isinstance(option_sources, dict):
                errors.append(
                    _manifest_error(
                        capability_code,
                        f"{field_prefix}.option_sources",
                        "option_sources must be an object",
                    )
                )
            else:
                for option_field, option_source in option_sources.items():
                    option_prefix = f"{field_prefix}.option_sources.{option_field}"
                    if not isinstance(option_source, dict):
                        errors.append(
                            _manifest_error(
                                capability_code,
                                option_prefix,
                                "option source must be an object",
                            )
                        )
                        continue
                    _validate_pack_backend(
                        capability_code=capability_code,
                        field=f"{option_prefix}.backend",
                        backend=option_source.get("backend"),
                        errors=errors,
                        warnings=warnings,
                    )
        runtime_lock = node.get("runtime_lock")
        if runtime_lock is not None:
            if not isinstance(runtime_lock, dict):
                errors.append(
                    _manifest_error(
                        capability_code,
                        f"{field_prefix}.runtime_lock",
                        "runtime_lock must be an object",
                    )
                )
            else:
                if runtime_lock.get("max_parallel") != 1:
                    errors.append(
                        _manifest_error(
                            capability_code,
                            f"{field_prefix}.runtime_lock.max_parallel",
                            "runtime_lock.max_parallel must be 1",
                        )
                    )
                key_template = runtime_lock.get("key_template")
                if not isinstance(key_template, str) or not key_template.strip():
                    errors.append(
                        _manifest_error(
                            capability_code,
                            f"{field_prefix}.runtime_lock.key_template",
                            "runtime_lock.key_template must be a non-empty string",
                        )
                    )
                else:
                    _validate_runtime_lock_template(
                        capability_code,
                        f"{field_prefix}.runtime_lock.key_template",
                        key_template,
                        errors,
                    )


def _validate_composition_graph_node_ports(
    capability_code: str,
    field_prefix: str,
    ports: object,
    direction: str,
    errors: List[ValidationError],
) -> None:
    if not isinstance(ports, list):
        errors.append(
            _manifest_error(
                capability_code,
                f"{field_prefix}.{direction}_ports",
                f"{direction}_ports must be a list",
            )
        )
        return
    for port_index, port in enumerate(ports):
        port_prefix = f"{field_prefix}.{direction}_ports[{port_index}]"
        if not isinstance(port, dict):
            errors.append(
                _manifest_error(
                    capability_code,
                    port_prefix,
                    "port must be an object",
                )
            )
            continue
        if port.get("direction") != direction:
            errors.append(
                _manifest_error(
                    capability_code,
                    f"{port_prefix}.direction",
                    f"port direction must be {direction}",
                )
            )


def _validate_runtime_lock_template(
    capability_code: str,
    field: str,
    key_template: str,
    errors: List[ValidationError],
) -> None:
    for match in RUNTIME_LOCK_TOKEN_PATTERN.finditer(key_template):
        token = match.group(1)
        if token == "workspace_id":
            continue
        if token.startswith("payload.") and token.removeprefix("payload."):
            continue
        errors.append(
            _manifest_error(
                capability_code,
                field,
                "runtime_lock.key_template only supports {workspace_id} and {payload.<field>} tokens",
            )
        )
