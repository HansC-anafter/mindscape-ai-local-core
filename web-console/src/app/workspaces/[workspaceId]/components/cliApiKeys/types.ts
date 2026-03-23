'use client';

export interface PoolAccount {
  id: string;
  email: string | null;
  auth_status: string;
  pool_enabled: boolean;
  pool_priority: number;
  cooldown_until: string | null;
  last_used_at: string | null;
  last_error_code: string | null;
}

export interface ExecutorSpec {
  runtime_id: string;
  display_name: string;
  is_primary: boolean;
  config?: Record<string, any>;
  priority: number;
}

export interface WorkspaceGcaStatus {
  requested_workspace_id: string;
  effective_workspace_id: string;
  auth_workspace_id: string | null;
  source_workspace_id: string | null;
  selection_reason: string;
  selection_trace: Array<Record<string, any>>;
  policy_mode: 'pinned_runtime' | 'pool_rotation';
  preferred_runtime_id: string | null;
  resolved_runtime_id: string | null;
  resolved_email: string | null;
  resolved_status: 'available' | 'cooldown' | 'unavailable';
  cooldown_until: string | null;
  next_reset_at: string | null;
  available_count: number;
  cooling_count: number;
  pool_count: number;
  error: string | null;
}

export interface WorkspaceAgentInfo {
  id: string;
  name: string;
  description: string;
  status: 'available' | 'unavailable' | 'error';
  version: string;
  risk_level: string;
  cli_command?: string | null;
  transport?: string | null;
  reason?: string | null;
}

export interface WorkspaceAgentListResponse {
  agents: WorkspaceAgentInfo[];
}

export interface AgentAuthStatusResponse {
  agent_id: string;
  workspace_id: string;
  available: boolean;
  transport?: string | null;
  reason?: string | null;
  mode: string;
  status: string;
  note?: string | null;
  output?: string | null;
  error?: string | null;
  login_supported: boolean;
  logout_supported: boolean;
  manual_command?: string | null;
}

export interface AgentAuthActionResponse {
  agent_id: string;
  workspace_id: string;
  action: string;
  success: boolean;
  output: string;
  error?: string | null;
  note?: string | null;
}

export type AgentTab = 'gemini' | 'claude' | 'codex';
export type AgentMode = 'api' | 'gca' | 'host_session' | 'host_token';

export interface ModeOption {
  value: AgentMode;
  label: string;
}

export interface CliAgent {
  id: AgentTab;
  label: string;
  settingsKey: string;
  placeholder: string;
  guideUrl: string;
  guideSteps: string[];
  icon: string;
  modeSettingKey: string;
  modeOptions: ModeOption[];
  runtimeAgentId?: string;
}

export const CLI_AGENTS: CliAgent[] = [
  {
    id: 'gemini',
    label: 'Gemini CLI',
    settingsKey: 'gemini_api_key',
    placeholder: 'AIzaSy...',
    guideUrl: 'https://aistudio.google.com/apikey',
    guideSteps: [
      'Open Google AI Studio',
      'Click "Create API Key"',
      'Select or create a GCP project',
      'Copy the generated key and paste it below',
    ],
    icon: '✦',
    modeSettingKey: 'gemini_cli_auth_mode',
    modeOptions: [
      { value: 'gca', label: 'Google Account (GCA)' },
      { value: 'api', label: '純 API' },
    ],
  },
  {
    id: 'claude',
    label: 'Claude Code',
    settingsKey: 'claude_api_key',
    placeholder: 'sk-ant-...',
    guideUrl: 'https://console.anthropic.com/settings/keys',
    guideSteps: [
      'Open Anthropic Console',
      'Go to Settings → API Keys',
      'Click "Create Key" and copy it',
      'Paste the key below',
    ],
    icon: '◈',
    modeSettingKey: 'claude_code_cli_auth_mode',
    modeOptions: [
      { value: 'host_token', label: 'Host Token' },
      { value: 'api', label: '純 API' },
    ],
    runtimeAgentId: 'claude_code_cli',
  },
  {
    id: 'codex',
    label: 'Codex CLI',
    settingsKey: 'openai_api_key',
    placeholder: 'sk-...',
    guideUrl: 'https://platform.openai.com/api-keys',
    guideSteps: [
      'Open OpenAI Platform',
      'Go to API Keys page',
      'Click "Create new secret key"',
      'Copy and paste the key below',
    ],
    icon: '⬡',
    modeSettingKey: 'codex_cli_auth_mode',
    modeOptions: [
      { value: 'host_session', label: 'Host Session' },
      { value: 'api', label: '純 API' },
    ],
    runtimeAgentId: 'codex_cli',
  },
];

export const DEFAULT_AGENT_MODES: Record<AgentTab, AgentMode> = {
  gemini: 'api',
  claude: 'api',
  codex: 'api',
};
