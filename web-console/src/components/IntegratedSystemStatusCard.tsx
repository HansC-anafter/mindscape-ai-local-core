'use client';

import React, { useState, useEffect, useCallback, useRef } from 'react';
import Link from 'next/link';
import { t } from '@/lib/i18n';
import { getApiBaseUrl } from '@/lib/api-url';

interface AgentInfo {
  id: string;
  name: string;
  status: 'available' | 'unavailable';
  transport?: string | null;  // 'ws', 'polling', 'sampling'
  reason?: string | null;     // 'ws_connected', 'no_ws_client', etc.
  cli_command?: string | null;
}

interface IntegratedSystemStatusProps {
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

// Format provider name for display
const formatProviderName = (provider?: string): string => {
  if (!provider) return '';

  const providerMap: Record<string, string> = {
    'openai': 'OpenAI',
    'anthropic': 'Anthropic',
    'vertex-ai': 'Vertex AI',
    'vertex_ai': 'Vertex AI',
    'local': 'Local',
    'remote_crs': 'Remote CRS',
  };

  return providerMap[provider.toLowerCase()] || provider.charAt(0).toUpperCase() + provider.slice(1).replace(/-/g, ' ').replace(/_/g, ' ');
};

interface HostServiceStatus {
  name: string;
  ok: boolean;
  detail?: string;
}

export default function IntegratedSystemStatusCard({
  systemStatus,
  workspace,
  workspaceId,
  onRefresh
}: IntegratedSystemStatusProps) {
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [bridgeScriptPath, setBridgeScriptPath] = useState<string | null>(null);
  const [showBridgeDialog, setShowBridgeDialog] = useState(false);
  const [copied, setCopied] = useState(false);
  const [copiedAll, setCopiedAll] = useState(false);
  const [hostServices, setHostServices] = useState<HostServiceStatus[]>([]);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);

  const fetchAgents = useCallback(async () => {
    try {
      const apiUrl = getApiBaseUrl();
      // Use workspace-scoped endpoint for accurate per-workspace status
      const res = await fetch(`${apiUrl}/api/v1/workspaces/${workspaceId}/agents`);
      if (res.ok) {
        const data = await res.json();
        setAgents(data.agents || []);
        if (data.bridge_script_path) {
          setBridgeScriptPath(data.bridge_script_path);
        }
      }
    } catch {
      // Silently ignore fetch errors
    }
  }, [workspaceId]);

  const fetchHostServices = useCallback(async () => {
    const apiUrl = getApiBaseUrl();
    const checks: HostServiceStatus[] = [];

    // XTTS service
    try {
      const r = await fetch(`${apiUrl}/api/v1/host/services/xtts/health`, { signal: AbortSignal.timeout(3000) });
      if (r.ok) {
        const d = await r.json();
        checks.push({
          name: 'XTTS Service',
          ok: d.status === 'ok',
          detail: d.model_loaded ? 'model loaded' : 'model not loaded',
        });
      } else {
        checks.push({ name: 'XTTS Service', ok: false, detail: 'unreachable' });
      }
    } catch {
      checks.push({ name: 'XTTS Service', ok: false, detail: 'unreachable' });
    }

    // MCP Gateway (Node process on host)
    try {
      const r = await fetch(`${apiUrl}/api/v1/host/services/mcp-gateway/health`, { signal: AbortSignal.timeout(3000) });
      checks.push({ name: 'MCP Gateway', ok: r.ok, detail: r.ok ? 'running' : 'not running' });
    } catch {
      checks.push({ name: 'MCP Gateway', ok: false, detail: 'unreachable' });
    }

    setHostServices(checks);
    setLastUpdated(new Date());
  }, []);

  const handleManualRefresh = useCallback(async () => {
    setIsRefreshing(true);
    await Promise.all([fetchAgents(), fetchHostServices()]);
    onRefresh?.();
    setIsRefreshing(false);
  }, [fetchAgents, fetchHostServices, onRefresh]);

  useEffect(() => {
    fetchAgents();
    fetchHostServices();
    // Poll every 30s to detect bridge connections
    const interval = setInterval(() => {
      fetchAgents();
      fetchHostServices();
    }, 30_000);
    return () => clearInterval(interval);
  }, [fetchAgents, fetchHostServices]);

  // Update lastUpdated whenever systemStatus changes (driven by Context 60s poll)
  useEffect(() => {
    if (systemStatus) setLastUpdated(new Date());
  }, [systemStatus]);

  const availableCount = agents.filter(a => a.status === 'available').length;

  const formatTime = (d: Date) =>
    d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });

  return (
    <div className="bg-surface-secondary dark:bg-gray-800 border dark:border-gray-700 rounded p-2 shadow-sm">
      {/* Header */}
      <div className="flex items-center justify-between mb-2">
        <h3 className="font-semibold text-primary dark:text-gray-100 text-xs">{t('systemStatusAndTools' as any)}</h3>
        <div className="flex items-center gap-2">
          {systemStatus.has_issues && (
            <span className="text-[10px] text-red-600 dark:text-red-400 font-medium">
              {systemStatus.critical_issues_count} {t('issuesCount' as any)}
            </span>
          )}
          <button
            onClick={handleManualRefresh}
            disabled={isRefreshing}
            title="刷新系統狀態"
            className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 transition-colors disabled:opacity-50"
          >
            <svg
              className={`w-3 h-3 ${isRefreshing ? 'animate-spin' : ''}`}
              fill="none" stroke="currentColor" viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
          </button>
        </div>
      </div>
      {lastUpdated && (
        <div className="text-[9px] text-gray-400 dark:text-gray-500 mb-1.5 text-right">
          更新於 {formatTime(lastUpdated)}
        </div>
      )}

      {/* Core System Status */}
      <div className="space-y-1.5 text-xs mb-2">
        <div className="flex items-center justify-between">
          <span className="text-secondary dark:text-gray-400 text-xs">{t('llmConnectionStatus' as any)}</span>
          <div className="flex items-center gap-1.5">
            {systemStatus.llm_configured ? (
              <svg className="w-3 h-3 text-green-500 dark:text-green-400" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
              </svg>
            ) : (
              <svg className="w-3 h-3 text-red-500 dark:text-red-400" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
              </svg>
            )}
            <span className={`text-xs ${systemStatus.llm_configured ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
              {systemStatus.llm_configured
                ? formatProviderName(systemStatus.llm_provider) || t('available' as any)
                : t('notConfigured' as any)}
            </span>
          </div>
        </div>

        <div className="flex items-center justify-between">
          <span className="text-secondary dark:text-gray-400 text-xs">{t('vectorDB' as any)}</span>
          <div className="flex items-center gap-1.5">
            <svg className="w-3 h-3 text-green-500 dark:text-green-400" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
            </svg>
            <span className={`text-xs ${systemStatus.vector_db_connected ? 'text-green-600 dark:text-green-400' : 'text-yellow-600 dark:text-yellow-400'}`}>
              {systemStatus.vector_db_connected ? t('connected' as any) : t('notConnected' as any)}
            </span>
          </div>
        </div>
      </div>

      {/* Local Agent CLI Section */}
      {agents.length > 0 && (
        <div className="mt-2 pt-2 border-t dark:border-gray-700">
          <div className="flex items-center justify-between mb-1">
            <div className="text-[10px] text-secondary dark:text-gray-400">
              Local Agent CLI
            </div>
            <button
              onClick={() => setShowBridgeDialog(true)}
              className="text-[10px] text-accent dark:text-blue-400 hover:opacity-80 dark:hover:text-blue-300 underline cursor-pointer"
            >
              How to connect?
            </button>
          </div>
          <div className="space-y-1">
            {agents.map((agent) => {
              const isWsConnected = agent.status === 'available' && agent.transport === 'ws';
              const noWsClient = agent.status === 'unavailable' && agent.reason === 'no_ws_client';

              let dotColor = 'bg-gray-400 dark:bg-gray-500';
              let textColor = 'text-gray-400 dark:text-gray-500';
              let label = 'Disconnected';

              if (isWsConnected) {
                dotColor = 'bg-green-500';
                textColor = 'text-green-600 dark:text-green-400';
                label = 'Connected (WS)';
              } else if (noWsClient) {
                dotColor = 'bg-yellow-500';
                textColor = 'text-yellow-600 dark:text-yellow-400';
                label = 'Disconnected -- Start Bridge';
              }

              return (
                <div key={agent.id} className="flex items-center justify-between text-xs">
                  <span className="text-secondary dark:text-gray-400">{agent.name}</span>
                  <div className="flex items-center gap-1.5">
                    <div className={`w-1.5 h-1.5 rounded-full ${dotColor}`} />
                    <span className={`text-xs ${textColor}`}>
                      {label}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
          {availableCount === 0 && (
            <div className="mt-1.5 px-2 py-1 bg-yellow-50 dark:bg-yellow-900/20 rounded text-[10px] text-yellow-700 dark:text-yellow-400">
              No agents connected. Run the Bridge script to get started.
            </div>
          )}
        </div>
      )}

      {/* Host Services */}
      {hostServices.length > 0 && (
        <div className="mt-2 pt-2 border-t dark:border-gray-700">
          <div className="text-[10px] text-secondary dark:text-gray-400 mb-1">Host Services</div>
          <div className="space-y-1">
            {hostServices.map((svc) => (
              <div key={svc.name} className="flex items-center justify-between text-xs">
                <span className="text-secondary dark:text-gray-400">{svc.name}</span>
                <div className="flex items-center gap-1.5">
                  <div className={`w-1.5 h-1.5 rounded-full ${svc.ok ? 'bg-green-500' : 'bg-gray-400 dark:bg-gray-500'}`} />
                  <span className={`text-xs ${svc.ok ? 'text-green-600 dark:text-green-400' : 'text-gray-400 dark:text-gray-500'}`}>
                    {svc.detail || (svc.ok ? 'running' : 'offline')}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Workspace Settings (if any) */}
      {(workspace.primary_project_id || workspace.default_playbook_id || workspace.default_locale) && (
        <div className="mt-2 pt-2 border-t dark:border-gray-700">
          <div className="text-[10px] text-secondary dark:text-gray-400 mb-1">{t('workspaceSettingsStatus' as any)}</div>
          {workspace.primary_project_id && (
            <div className="mb-1.5">
              <div className="text-[10px] text-secondary dark:text-gray-400 mb-0.5">{t('primaryProject' as any)}</div>
              <div className="text-xs text-primary dark:text-gray-100">{workspace.primary_project_id}</div>
            </div>
          )}
          {workspace.default_playbook_id && (
            <div className="mb-1.5">
              <div className="text-[10px] text-secondary dark:text-gray-400 mb-0.5">{t('defaultPlaybook' as any)}</div>
              <div className="text-xs text-primary dark:text-gray-100">{workspace.default_playbook_id}</div>
            </div>
          )}
          {workspace.default_locale && (
            <div className="mb-1.5">
              <div className="text-[10px] text-secondary dark:text-gray-400 mb-0.5">{t('locale' as any)}</div>
              <div className="text-xs text-primary dark:text-gray-100">{workspace.default_locale}</div>
            </div>
          )}
        </div>
      )}

      {/* Footer Link */}
      <div className="mt-2 pt-2 border-t dark:border-gray-700">
        <Link
          href="/settings"
          className="text-[10px] text-accent dark:text-blue-400 hover:opacity-80 dark:hover:text-blue-300 underline"
        >
          {t('goToSettings' as any)} →
        </Link>
      </div>

      {/* Bridge Setup Dialog */}
      {showBridgeDialog && (
        <div
          className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-[60] p-4"
          onClick={() => setShowBridgeDialog(false)}
        >
          <div
            className="bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-lg w-full max-h-[85vh] flex flex-col"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Header */}
            <div className="p-5 border-b dark:border-gray-700 flex-shrink-0">
              <div className="flex items-center justify-between">
                <h3 className="text-base font-semibold text-gray-900 dark:text-gray-100">
                  Connect Local Agent CLI
                </h3>
                <button
                  onClick={() => setShowBridgeDialog(false)}
                  className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-200"
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                Mindscape can dispatch locally installed CLI agents (e.g. Gemini CLI) to execute tasks.
                Since CLI tools are installed on your machine, a Bridge script is needed to connect them to the system.
              </p>
            </div>

            {/* Steps */}
            <div className="p-5 space-y-5 overflow-y-auto">
              {/* Step 1: Install CLI */}
              <div>
                <div className="flex items-center gap-2 mb-2">
                  <span className="flex-shrink-0 w-5 h-5 rounded-full bg-blue-600 text-white text-[10px] font-bold flex items-center justify-center">1</span>
                  <span className="text-sm font-medium text-gray-900 dark:text-gray-100">Make sure at least one CLI Agent is installed</span>
                </div>
                <div className="ml-7 bg-gray-50 dark:bg-gray-700/50 rounded-lg p-3 space-y-1.5">
                  {[
                    { name: 'Gemini CLI', cmd: 'npm i -g @google/gemini-cli' },
                    { name: 'Claude Code', cmd: 'npm i -g @anthropic-ai/claude-code' },
                    { name: 'Codex CLI', cmd: 'npm i -g @openai/codex' },
                    { name: 'OpenClaw', cmd: 'pip install openclaw' },
                  ].map(({ name, cmd }) => (
                    <div key={name} className="flex items-center justify-between text-xs">
                      <span className="text-gray-700 dark:text-gray-300 font-medium">{name}</span>
                      <code className="text-[10px] bg-gray-200 dark:bg-gray-600 text-gray-600 dark:text-gray-300 px-1.5 py-0.5 rounded font-mono">{cmd}</code>
                    </div>
                  ))}
                </div>
              </div>

              {/* Step 2: Run bridge */}
              <div>
                <div className="flex items-center gap-2 mb-2">
                  <span className="flex-shrink-0 w-5 h-5 rounded-full bg-blue-600 text-white text-[10px] font-bold flex items-center justify-center">2</span>
                  <span className="text-sm font-medium text-gray-900 dark:text-gray-100">Run the Bridge script in your terminal</span>
                </div>
                {/* Windows (PowerShell) */}
                <div className="ml-7 mb-3 border border-blue-200 dark:border-blue-800 rounded-lg p-2.5">
                  <div className="text-sm font-bold text-blue-700 dark:text-blue-300 mb-1.5">🪟 Windows (PowerShell)</div>
                  <div className="relative">
                    <pre className="bg-gray-900 text-green-400 rounded p-2 text-[10px] font-mono overflow-x-auto whitespace-pre-wrap break-all">
                      {`.\u005Cscripts\u005Cstart_cli_bridge.ps1 -All`}
                    </pre>
                    <button
                      onClick={() => {
                        navigator.clipboard.writeText(`.\\scripts\\start_cli_bridge.ps1 -All`);
                        setCopiedAll(true);
                        setTimeout(() => setCopiedAll(false), 1500);
                      }}
                      className={`absolute top-1.5 right-1.5 px-2 py-0.5 text-[9px] rounded transition-colors ${copiedAll
                        ? 'bg-green-700 text-green-200'
                        : 'bg-gray-700 hover:bg-gray-600 text-gray-300'
                        }`}
                    >
                      {copiedAll ? 'Copied ✓' : 'Copy'}
                    </button>
                  </div>
                </div>
                {/* macOS / Linux */}
                <div className="ml-7 border border-gray-200 dark:border-gray-600 rounded-lg p-2.5">
                  <div className="text-sm font-bold text-gray-700 dark:text-gray-300 mb-1.5">🍎 macOS / Linux</div>
                  <div className="relative">
                    <pre className="bg-gray-900 text-green-400 rounded p-2 text-[10px] font-mono overflow-x-auto whitespace-pre-wrap break-all">
                      {bridgeScriptPath
                        ? `${bridgeScriptPath} --all`
                        : `./scripts/start_cli_bridge.sh --all`}
                    </pre>
                    <button
                      onClick={() => {
                        const cmd = bridgeScriptPath
                          ? `${bridgeScriptPath} --all`
                          : `./scripts/start_cli_bridge.sh --all`;
                        navigator.clipboard.writeText(cmd);
                        setCopied(true);
                        setTimeout(() => setCopied(false), 1500);
                      }}
                      className={`absolute top-1.5 right-1.5 px-2 py-0.5 text-[9px] rounded transition-colors ${copied
                        ? 'bg-green-700 text-green-200'
                        : 'bg-gray-700 hover:bg-gray-600 text-gray-300'
                        }`}
                    >
                      {copied ? 'Copied ✓' : 'Copy'}
                    </button>
                  </div>
                </div>
                <p className="ml-7 text-[10px] text-gray-500 dark:text-gray-400 mt-1.5">
                  <code>--all</code> / <code>-All</code> connects all workspaces. Or use <code>--workspace-id {workspaceId}</code> for this workspace only.
                </p>
              </div>

              {/* Step 3: Result */}
              <div>
                <div className="flex items-center gap-2 mb-2">
                  <span className="flex-shrink-0 w-5 h-5 rounded-full bg-blue-600 text-white text-[10px] font-bold flex items-center justify-center">3</span>
                  <span className="text-sm font-medium text-gray-900 dark:text-gray-100">Once connected</span>
                </div>
                <div className="ml-7 text-xs text-gray-600 dark:text-gray-400 space-y-1">
                  <div className="flex items-center gap-1.5">
                    <div className="w-1.5 h-1.5 rounded-full bg-green-500 flex-shrink-0" />
                    <span>The agent status above will automatically change to "<span className="text-green-600 dark:text-green-400 font-medium">Connected</span>"</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <div className="w-1.5 h-1.5 rounded-full bg-green-500 flex-shrink-0" />
                    <span>Mindscape will automatically dispatch tasks to connected agents</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <div className="w-1.5 h-1.5 rounded-full bg-green-500 flex-shrink-0" />
                    <span>Keep the terminal window open while the Bridge is running</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
