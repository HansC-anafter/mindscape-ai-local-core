export interface MemoryImpactGraphNode {
  id: string;
  type: string;
  label: string;
  subtitle?: string | null;
  status?: string | null;
  metadata: Record<string, unknown>;
}

export interface MemoryImpactGraphEdge {
  id: string;
  from_node_id: string;
  to_node_id: string;
  kind: string;
  provenance: 'explicit' | 'inferred';
  metadata: Record<string, unknown>;
}

export interface MemoryImpactGraphFocus {
  workspace_id: string;
  session_id: string;
  focus_node_id: string;
  project_id?: string | null;
  thread_id?: string | null;
  execution_id?: string | null;
  execution_ids: string[];
}

export interface MemoryImpactPacketSummary {
  selected_node_count: number;
  route_sections: string[];
  counts_by_type: Record<string, number>;
  selection: Record<string, unknown>;
}

export interface MemoryImpactGraphResponse {
  workspace_id: string;
  session_id: string;
  focus: MemoryImpactGraphFocus;
  packet_summary: MemoryImpactPacketSummary;
  nodes: MemoryImpactGraphNode[];
  edges: MemoryImpactGraphEdge[];
  warnings: string[];
}

export interface MemoryImpactGraphQuery {
  workspaceId: string;
  apiUrl: string;
  sessionId?: string | null;
  executionId?: string | null;
  threadId?: string | null;
}

export interface MemoryImpactVisualNode extends MemoryImpactGraphNode {
  x: number;
  y: number;
  size: number;
  color: string;
  emphasis: 'focus' | 'selected' | 'produced' | 'secondary';
  isFocus: boolean;
  isSelected: boolean;
}

export interface MemoryImpactVisualEdge extends MemoryImpactGraphEdge {
  color: string;
  size: number;
}
