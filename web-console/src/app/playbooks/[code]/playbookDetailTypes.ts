export interface Playbook {
  metadata: {
    playbook_code: string;
    version: string;
    locale: string;
    name: string;
    description: string;
    tags: string[];
    entry_agent_type?: string;
    onboarding_task?: string;
    icon?: string;
    required_tools: string[];
    scope?: any;
    owner?: any;
    capability_code?: string;
  };
  sop_content: string;
  user_notes?: string;
  user_meta: {
    favorite?: boolean;
    use_count?: number;
  };
  associated_intents: Array<{
    intent_id: string;
    title: string;
    status?: string;
    priority?: string;
  }>;
  execution_status?: {
    active_executions: Array<{
      execution_id: string;
      status: string;
      started_at?: string;
    }>;
    recent_executions: Array<{
      execution_id: string;
      status: string;
      started_at?: string;
      completed_at?: string;
    }>;
  };
  version_info?: {
    has_personal_variant: boolean;
    default_variant: any;
    system_version: string;
  };
}

export interface PlaybookListItem {
  playbook_code: string;
  name: string;
  description: string;
  icon?: string;
  tags?: string[];
  capability_code?: string;
}

export interface RecentPlaybookView extends PlaybookListItem {
  viewed_at: string;
}

export interface OptimizationSuggestion {
  title: string;
  description: string;
  rationale: string;
  step_number?: number;
  [key: string]: any;
}

export type PlaybookTab = 'info' | 'sop' | 'suggestions' | 'history';
export type VersionSelection = 'system' | 'personal';
