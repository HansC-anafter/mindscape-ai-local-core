'use client';

import React, { useState, useEffect, useCallback } from 'react';
import Link from 'next/link';
import { t } from '@/lib/i18n';
import { getApiBaseUrl } from '@/lib/api-url';

interface AgentInfo {
  id: string;
  name: string;
  status: 'available' | 'unavailable';
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

  const fetchAgents = useCallback(async () => {
    try {
      const apiUrl = getApiBaseUrl();
      const res = await fetch(`${apiUrl}/api/v1/agents`);
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
  }, []);

  useEffect(() => {
    fetchAgents();
    // Poll every 30s to detect bridge connections
    const interval = setInterval(fetchAgents, 30_000);
    return () => clearInterval(interval);
  }, [fetchAgents]);

  const availableCount = agents.filter(a => a.status === 'available').length;

  return (
    <div className="bg-surface-secondary dark:bg-gray-800 border dark:border-gray-700 rounded p-2 shadow-sm">
      {/* Header */}
      <div className="flex items-center justify-between mb-2">
        <h3 className="font-semibold text-primary dark:text-gray-100 text-xs">{t('systemStatusAndTools' as any)}</h3>
        {systemStatus.has_issues && (
          <span className="text-[10px] text-red-600 dark:text-red-400 font-medium">
            {systemStatus.critical_issues_count} {t('issuesCount' as any)}
          </span>
        )}
      </div>

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
              本地 Agent CLI
            </div>
            <button
              onClick={() => setShowBridgeDialog(true)}
              className="text-[10px] text-accent dark:text-blue-400 hover:opacity-80 dark:hover:text-blue-300 underline cursor-pointer"
            >
              如何連線？
            </button>
          </div>
          <div className="space-y-1">
            {agents.map((agent) => (
              <div key={agent.id} className="flex items-center justify-between text-xs">
                <span className="text-secondary dark:text-gray-400">{agent.name}</span>
                <div className="flex items-center gap-1.5">
                  <div className={`w-1.5 h-1.5 rounded-full ${agent.status === 'available'
                    ? 'bg-green-500'
                    : 'bg-gray-400 dark:bg-gray-500'
                    }`} />
                  <span className={`text-xs ${agent.status === 'available'
                    ? 'text-green-600 dark:text-green-400'
                    : 'text-gray-400 dark:text-gray-500'
                    }`}>
                    {agent.status === 'available' ? '已連線' : '未連線'}
                  </span>
                </div>
              </div>
            ))}
          </div>
          {availableCount === 0 && (
            <div className="mt-1.5 px-2 py-1 bg-yellow-50 dark:bg-yellow-900/20 rounded text-[10px] text-yellow-700 dark:text-yellow-400">
              尚無 Agent 連線。請執行 Bridge 腳本以啟動。
            </div>
          )}
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
                  連接本地 Agent CLI
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
                Mindscape 可以調度本地安裝的 CLI Agent（如 Gemini CLI）來執行任務。
                由於 CLI 工具裝在你的電腦上，需要透過 Bridge 腳本將它們連接到系統。
              </p>
            </div>

            {/* Steps */}
            <div className="p-5 space-y-5 overflow-y-auto">
              {/* Step 1: Install CLI */}
              <div>
                <div className="flex items-center gap-2 mb-2">
                  <span className="flex-shrink-0 w-5 h-5 rounded-full bg-blue-600 text-white text-[10px] font-bold flex items-center justify-center">1</span>
                  <span className="text-sm font-medium text-gray-900 dark:text-gray-100">確認已安裝至少一個 CLI Agent</span>
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
                  <span className="text-sm font-medium text-gray-900 dark:text-gray-100">在終端機執行 Bridge 腳本</span>
                </div>
                <div className="ml-7 relative">
                  <pre className="bg-gray-900 text-green-400 rounded-lg p-3 text-xs font-mono overflow-x-auto whitespace-pre-wrap break-all">
                    {bridgeScriptPath
                      ? `${bridgeScriptPath} \\
  --workspace-id ${workspaceId}`
                      : `# Bridge script not found on server\n# Please check scripts/start_cli_bridge.sh`}
                  </pre>
                  <button
                    onClick={() => {
                      if (bridgeScriptPath) {
                        navigator.clipboard.writeText(
                          `${bridgeScriptPath} --workspace-id ${workspaceId}`
                        );
                        setCopied(true);
                        setTimeout(() => setCopied(false), 1500);
                      }
                    }}
                    disabled={!bridgeScriptPath}
                    className={`absolute top-2 right-2 px-2 py-1 text-[10px] rounded transition-colors ${copied
                      ? 'bg-green-700 text-green-200'
                      : bridgeScriptPath
                        ? 'bg-gray-700 hover:bg-gray-600 text-gray-300'
                        : 'bg-gray-800 text-gray-500 cursor-not-allowed'
                      }`}
                  >
                    {copied ? '已複製 ✓' : '複製'}
                  </button>
                </div>
                <p className="ml-7 text-[10px] text-gray-500 dark:text-gray-400 mt-1.5">
                  腳本會自動偵測你電腦上已安裝的 CLI，並建立 WebSocket 連線到 Mindscape 後端。
                </p>
              </div>

              {/* Step 3: Result */}
              <div>
                <div className="flex items-center gap-2 mb-2">
                  <span className="flex-shrink-0 w-5 h-5 rounded-full bg-blue-600 text-white text-[10px] font-bold flex items-center justify-center">3</span>
                  <span className="text-sm font-medium text-gray-900 dark:text-gray-100">連線成功後</span>
                </div>
                <div className="ml-7 text-xs text-gray-600 dark:text-gray-400 space-y-1">
                  <div className="flex items-center gap-1.5">
                    <div className="w-1.5 h-1.5 rounded-full bg-green-500 flex-shrink-0" />
                    <span>上方的 Agent 狀態會自動變為「<span className="text-green-600 dark:text-green-400 font-medium">已連線</span>」</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <div className="w-1.5 h-1.5 rounded-full bg-green-500 flex-shrink-0" />
                    <span>Mindscape 後續的任務會自動分配給已連線的 Agent 執行</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <div className="w-1.5 h-1.5 rounded-full bg-green-500 flex-shrink-0" />
                    <span>Bridge 執行中請保持終端機視窗開啟</span>
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
