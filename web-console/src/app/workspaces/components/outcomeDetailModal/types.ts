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

export interface OutcomeDetailModalProps {
  artifact: Artifact | null;
  isOpen: boolean;
  onClose: () => void;
  workspaceId: string;
  apiUrl: string;
}
