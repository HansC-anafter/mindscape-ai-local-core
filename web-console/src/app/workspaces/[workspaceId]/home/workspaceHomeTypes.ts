export interface IntentCard {
  title: string;
  description: string;
  priority: 'high' | 'medium' | 'low';
}

export interface ToolConnectionDisplay {
  tool_type: string;
  danger_level: string;
  default_readonly: boolean;
  allowed_roles: string[];
}

export interface WorkspaceInstruction {
  persona?: string;
  goals?: string[];
  anti_goals?: string[];
  style_rules?: string[];
  domain_context?: string;
}

export interface LaunchpadData {
  brief: string | null;
  instruction?: WorkspaceInstruction | null;
  initial_intents: IntentCard[];
  first_playbook: string | null;
  tool_connections: ToolConnectionDisplay[];
  launch_status: string;
  starter_kit_type?: string;
}

export type WorkspaceCreationMethod = 'quick' | 'llm-guided';
export type WorkspaceSeedType = 'text' | 'file' | 'urls';
export type WorkspaceWizardStep = 'method' | 'seed' | 'preview' | 'complete';

export interface WorkspaceWizardData {
  method?: WorkspaceCreationMethod;
  title?: string;
  description?: string;
  seedType?: WorkspaceSeedType;
  seedPayload?: unknown;
}

export interface WorkspaceHomeWorkspace {
  id?: string | number;
  title?: string;
  description?: string | null;
  launch_status?: string | null;
}

export interface WorkspaceHomeDerivedState {
  launchStatus: string;
  hasActualContent: boolean;
  isPending: boolean;
  isReady: boolean;
  hasContent: boolean;
}

export interface CreatedWorkspace {
  id: string | number;
}
