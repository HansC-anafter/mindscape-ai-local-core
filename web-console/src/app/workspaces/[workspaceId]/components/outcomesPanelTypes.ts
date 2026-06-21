export interface Artifact {
  id: string;
  workspace_id: string;
  intent_id?: string;
  task_id?: string;
  execution_id?: string;
  playbook_code: string;
  artifact_type: string;
  title: string;
  summary: string;
  content: any;
  storage_ref?: string;
  sync_state?: string;
  primary_action_type: string;
  metadata: any;
  created_at: string;
  updated_at: string;
}

export interface OutcomesPanelProps {
  workspaceId: string;
  apiUrl: string;
  onArtifactClick?: (artifact: Artifact) => void;
}

export interface MatchingCapabilityComponent {
  key: string;
  capabilityCode: string;
  componentCode: string;
  description?: string;
}

export interface SandboxModalState {
  show: boolean;
  sandboxId: string | null;
  initialFile: string | null;
  executionId: string | null;
}

export interface ArtifactDisplayInfo {
  filePath: string | null;
  fileName: string;
  executionId: string | null;
  formattedDate: string;
}

export interface SandboxOpenTarget {
  sandboxId: string;
  relativeFilePath: string;
  executionId: string;
}
