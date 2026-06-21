export interface Playbook {
  playbook_code: string;
  version: string;
  locale: string;
  name: string;
  description: string;
  tags: string[];
  icon?: string;
  entry_agent_type?: string;
  onboarding_task?: string;
  required_tools: string[];
  kind?: string;
  scope?: 'system' | 'tenant' | 'profile' | 'workspace';
  capability_code?: string;
  user_meta: {
    favorite: boolean;
    use_count: number;
  };
  has_personal_variant?: boolean;
  default_variant_name?: string;
  workspace_usage_count?: number;
  pinned_workspaces?: Array<{
    id: string;
    title: string;
    pinned_at?: string;
  }>;
}

export type PlaybooksByCapability = Record<string, Playbook[]>;
