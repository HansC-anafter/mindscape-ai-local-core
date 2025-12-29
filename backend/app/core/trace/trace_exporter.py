"""
Trace Exporter

Exports trace graphs in various formats for cloud telemetry ingestion.
"""

import json
import logging
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any

from .trace_schema import TraceGraph, TraceNode, TraceEdge, TraceNodeType, TraceStatus

logger = logging.getLogger(__name__)


class ExportFormat(str, Enum):
    """Supported export formats"""
    JSON = "json"  # Standard JSON format
    OPEN_TELEMETRY = "opentelemetry"  # OpenTelemetry format
    CUSTOM = "custom"  # Custom format for cloud ingestion


class TraceExporter:
    """Exports trace graphs to various formats"""

    def export(
        self,
        trace_graph: TraceGraph,
        format: ExportFormat = ExportFormat.JSON,
        include_metadata: bool = True,
        include_input_output: bool = True,
    ) -> Dict[str, Any]:
        """Export a trace graph to the specified format"""
        if format == ExportFormat.JSON:
            return self._export_json(trace_graph, include_metadata, include_input_output)
        elif format == ExportFormat.OPEN_TELEMETRY:
            return self._export_opentelemetry(trace_graph, include_metadata, include_input_output)
        elif format == ExportFormat.CUSTOM:
            return self._export_custom(trace_graph, include_metadata, include_input_output)
        else:
            raise ValueError(f"Unsupported export format: {format}")

    def export_to_json_string(
        self,
        trace_graph: TraceGraph,
        include_metadata: bool = True,
        include_input_output: bool = True,
        indent: int = 2,
    ) -> str:
        """Export to JSON string"""
        data = self.export(
            trace_graph,
            format=ExportFormat.JSON,
            include_metadata=include_metadata,
            include_input_output=include_input_output,
        )
        return json.dumps(data, indent=indent, default=str)

    def _export_json(
        self,
        trace_graph: TraceGraph,
        include_metadata: bool,
        include_input_output: bool,
    ) -> Dict[str, Any]:
        """Export to standard JSON format"""
        return trace_graph.to_dict()

    def _export_opentelemetry(
        self,
        trace_graph: TraceGraph,
        include_metadata: bool,
        include_input_output: bool,
    ) -> Dict[str, Any]:
        """Export to OpenTelemetry format"""
        spans = []

        for node in trace_graph.nodes:
            span = {
                "traceId": trace_graph.trace_id,
                "spanId": node.node_id,
                "name": node.name,
                "kind": self._map_node_type_to_otel_span_kind(node.node_type),
                "startTimeUnixNano": int(node.start_time.timestamp() * 1_000_000_000),
                "status": {
                    "code": 1 if node.status == TraceStatus.SUCCESS else 2,
                    "message": node.status.value,
                },
            }

            if node.end_time:
                span["endTimeUnixNano"] = int(node.end_time.timestamp() * 1_000_000_000)

            # Add attributes
            attributes = {
                "node.type": node.node_type.value,
                "node.status": node.status.value,
            }

            if include_metadata and node.metadata:
                if node.metadata.workspace_id:
                    attributes["workspace.id"] = node.metadata.workspace_id
                if node.metadata.execution_id:
                    attributes["execution.id"] = node.metadata.execution_id
                if node.metadata.model_name:
                    attributes["model.name"] = node.metadata.model_name
                if node.metadata.capability_profile:
                    attributes["capability.profile"] = node.metadata.capability_profile
                if node.metadata.cost_tokens:
                    attributes["cost.tokens"] = node.metadata.cost_tokens
                if node.metadata.latency_ms:
                    attributes["latency.ms"] = node.metadata.latency_ms

            if include_input_output:
                if node.input_data:
                    attributes["input"] = json.dumps(node.input_data)
                if node.output_data:
                    attributes["output"] = json.dumps(node.output_data)

            span["attributes"] = [{"key": k, "value": {"stringValue": str(v)}} for k, v in attributes.items()]

            # Add parent span ID
            parent_nodes = trace_graph.get_parents(node.node_id)
            if parent_nodes:
                span["parentSpanId"] = parent_nodes[0].node_id

            spans.append(span)

        return {
            "resourceSpans": [
                {
                    "resource": {
                        "attributes": [
                            {"key": "service.name", "value": {"stringValue": "mindscape-ai-local-core"}},
                        ],
                    },
                    "scopeSpans": [
                        {
                            "spans": spans,
                        },
                    ],
                },
            ],
        }

    def _export_custom(
        self,
        trace_graph: TraceGraph,
        include_metadata: bool,
        include_input_output: bool,
    ) -> Dict[str, Any]:
        """Export to custom format for cloud ingestion"""
        nodes_data = []
        edges_data = []

        for node in trace_graph.nodes:
            node_data = {
                "id": node.node_id,
                "type": node.node_type.value,
                "name": node.name,
                "status": node.status.value,
                "start_time": node.start_time.isoformat(),
            }

            if node.end_time:
                node_data["end_time"] = node.end_time.isoformat()
                node_data["duration_ms"] = node.duration_ms()

            if include_metadata and node.metadata:
                node_data["metadata"] = {
                    "workspace_id": node.metadata.workspace_id,
                    "execution_id": node.metadata.execution_id,
                }
                if node.metadata.model_name:
                    node_data["metadata"]["model_name"] = node.metadata.model_name
                if node.metadata.capability_profile:
                    node_data["metadata"]["capability_profile"] = node.metadata.capability_profile
                if node.metadata.cost_tokens:
                    node_data["metadata"]["cost_tokens"] = node.metadata.cost_tokens
                if node.metadata.latency_ms:
                    node_data["metadata"]["latency_ms"] = node.metadata.latency_ms

            if include_input_output:
                if node.input_data:
                    node_data["input"] = node.input_data
                if node.output_data:
                    node_data["output"] = node.output_data

            nodes_data.append(node_data)

        for edge in trace_graph.edges:
            edge_data = {
                "id": edge.edge_id,
                "source": edge.source_node_id,
                "target": edge.target_node_id,
                "type": edge.edge_type.value,
            }
            if edge.label:
                edge_data["label"] = edge.label
            if edge.metadata:
                edge_data["metadata"] = edge.metadata
            edges_data.append(edge_data)

        return {
            "trace_id": trace_graph.trace_id,
            "root_node_id": trace_graph.root_node_id,
            "nodes": nodes_data,
            "edges": edges_data,
            "created_at": trace_graph.created_at.isoformat(),
            "version": trace_graph.version,
        }

    def _map_node_type_to_otel_span_kind(self, node_type: TraceNodeType) -> str:
        """Map TraceNodeType to OpenTelemetry span kind"""
        mapping = {
            TraceNodeType.LLM: "SPAN_KIND_CLIENT",
            TraceNodeType.TOOL: "SPAN_KIND_SERVER",
            TraceNodeType.POLICY: "SPAN_KIND_INTERNAL",
            TraceNodeType.HUMAN: "SPAN_KIND_INTERNAL",
            TraceNodeType.STATE: "SPAN_KIND_INTERNAL",
            TraceNodeType.CHANGESET: "SPAN_KIND_INTERNAL",
            TraceNodeType.GRAPH: "SPAN_KIND_INTERNAL",
        }
        return mapping.get(node_type, "SPAN_KIND_INTERNAL")

    def export_batch(
        self,
        trace_graphs: List[TraceGraph],
        format: ExportFormat = ExportFormat.JSON,
        include_metadata: bool = True,
        include_input_output: bool = True,
    ) -> List[Dict[str, Any]]:
        """Export multiple trace graphs"""
        return [
            self.export(tg, format, include_metadata, include_input_output)
            for tg in trace_graphs
        ]










