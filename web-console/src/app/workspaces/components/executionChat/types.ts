export interface ExecutionChatMessage {
  id: string;
  execution_id: string;
  step_id?: string;
  role: 'user' | 'assistant' | 'agent';
  speaker?: string;
  content: string;
  message_type: 'question' | 'note' | 'route_proposal' | 'system_hint';
  created_at: string;
}

export interface PlaybookMetadata {
  playbook_code: string;
  title?: string;
  description?: string;
  supports_execution_chat?: boolean;
  discussion_agent?: string;
  [key: string]: any;
}

export interface ExecutionChatPanelProps {
  executionId: string;
  workspaceId: string;
  apiUrl: string;
  playbookMetadata?: PlaybookMetadata;
  executionStatus?: string;
  runNumber?: number;
  collapsible?: boolean;
  defaultCollapsed?: boolean;
}

export interface QuickPrompt {
  label: string;
  prompt: string;
}
