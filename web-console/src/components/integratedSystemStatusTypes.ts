export interface AgentInfo {
  id: string;
  name: string;
  status: 'available' | 'unavailable';
  transport?: string | null;
  reason?: string | null;
  cli_command?: string | null;
}

export interface IntegratedSystemStatusProps {
  systemStatus: {
    llm_configured: boolean;
    llm_provider?: string;
    vector_db_connected: boolean;
    tools: Record<string, {
      connected: boolean;
      status: string;
      connection_count?: number;
    }>;
    critical_issues_count: number;
    has_issues: boolean;
  };
  workspace: {
    primary_project_id?: string;
    default_playbook_id?: string;
    default_locale?: string;
  };
  workspaceId: string;
  onRefresh?: () => void;
}

export interface HostServiceStatus {
  name: string;
  ok: boolean;
  detail?: string;
}

export interface AgentsStatusSnapshot {
  agents: AgentInfo[];
  bridgeScriptPath: string | null;
}

export const POLL_INTERVAL_MS = 30_000;
export const HOST_SERVICE_TIMEOUT_MS = 3_000;
export const COPY_RESET_MS = 1_500;

export const DEFAULT_WINDOWS_BRIDGE_COMMAND = '.\\scripts\\start_cli_bridge.ps1 -All';
export const DEFAULT_UNIX_BRIDGE_COMMAND = './scripts/start_cli_bridge.sh --all';

export const REFRESH_SYSTEM_STATUS_TITLE = '\u5237\u65b0\u7cfb\u7d71\u72c0\u614b';
export const UPDATED_AT_LABEL = '\u66f4\u65b0\u65bc';
export const GO_TO_SETTINGS_ARROW = '\u2192';
export const COPIED_CHECK_LABEL = 'Copied \u2713';
export const WINDOWS_SETUP_LABEL = '\u{1FA9F} Windows (PowerShell)';
export const MACOS_LINUX_SETUP_LABEL = '\u{1F34E} macOS / Linux';

export const LOCAL_AGENT_INSTALL_COMMANDS = [
  { name: 'Gemini CLI', cmd: 'npm i -g @google/gemini-cli' },
  { name: 'Claude Code', cmd: 'npm i -g @anthropic-ai/claude-code' },
  { name: 'Codex CLI', cmd: 'npm i -g @openai/codex' },
  { name: 'OpenClaw', cmd: 'pip install openclaw' },
] as const;

export const formatProviderName = (provider?: string): string => {
  if (!provider) return '';

  const providerMap: Record<string, string> = {
    openai: 'OpenAI',
    anthropic: 'Anthropic',
    'vertex-ai': 'Vertex AI',
    vertex_ai: 'Vertex AI',
    local: 'Local',
    remote_crs: 'Remote CRS',
  };

  return providerMap[provider.toLowerCase()] ||
    provider.charAt(0).toUpperCase() + provider.slice(1).replace(/-/g, ' ').replace(/_/g, ' ');
};

export const formatTime = (date: Date) =>
  date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
