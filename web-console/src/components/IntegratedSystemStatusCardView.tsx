import React from 'react';
import Link from 'next/link';

import { useT } from '@/lib/i18n';

import type { AgentInfo, HostServiceStatus, IntegratedSystemStatusProps } from './integratedSystemStatusTypes';
import {
  COPIED_CHECK_LABEL,
  DEFAULT_UNIX_BRIDGE_COMMAND,
  DEFAULT_WINDOWS_BRIDGE_COMMAND,
  formatProviderName,
  formatTime,
  GO_TO_SETTINGS_ARROW,
  LOCAL_AGENT_INSTALL_COMMANDS,
  MACOS_LINUX_SETUP_LABEL,
  REFRESH_SYSTEM_STATUS_TITLE,
  UPDATED_AT_LABEL,
  WINDOWS_SETUP_LABEL,
} from './integratedSystemStatusTypes';

interface IntegratedSystemStatusCardViewProps extends IntegratedSystemStatusProps {
  agents: AgentInfo[];
  bridgeScriptPath: string | null;
  copied: boolean;
  copiedAll: boolean;
  hostServices: HostServiceStatus[];
  isRefreshing: boolean;
  lastUpdated: Date | null;
  showBridgeDialog: boolean;
  availableCount: number;
  onCopyUnixCommand: () => void;
  onCopyWindowsCommand: () => void;
  onHideBridgeDialog: () => void;
  onManualRefresh: () => void;
  onShowBridgeDialog: () => void;
}

const agentStatusView = (agent: AgentInfo) => {
  const isWsConnected = agent.status === 'available' && agent.transport === 'ws';
  const noWsClient = agent.status === 'unavailable' && agent.reason === 'no_ws_client';

  if (isWsConnected) {
    return {
      dotColor: 'bg-green-500',
      textColor: 'text-green-600 dark:text-green-400',
      label: 'Connected (WS)',
    };
  }

  if (noWsClient) {
    return {
      dotColor: 'bg-yellow-500',
      textColor: 'text-yellow-600 dark:text-yellow-400',
      label: 'Disconnected -- Start Bridge',
    };
  }

  return {
    dotColor: 'bg-gray-400 dark:bg-gray-500',
    textColor: 'text-gray-400 dark:text-gray-500',
    label: 'Disconnected',
  };
};

export function IntegratedSystemStatusCardView({
  agents,
  availableCount,
  bridgeScriptPath,
  copied,
  copiedAll,
  hostServices,
  isRefreshing,
  lastUpdated,
  showBridgeDialog,
  systemStatus,
  workspace,
  workspaceId,
  onCopyUnixCommand,
  onCopyWindowsCommand,
  onHideBridgeDialog,
  onManualRefresh,
  onShowBridgeDialog,
}: IntegratedSystemStatusCardViewProps) {
  const t = useT();
  return (
    <div className="bg-surface-secondary dark:bg-gray-800 border dark:border-gray-700 rounded p-2 shadow-sm">
      <div className="flex items-center justify-between mb-2">
        <h3 className="font-semibold text-primary dark:text-gray-100 text-xs">{t('systemStatusAndTools' as any)}</h3>
        <div className="flex items-center gap-2">
          {systemStatus.has_issues && (
            <span className="text-[10px] text-red-600 dark:text-red-400 font-medium">
              {systemStatus.critical_issues_count} {t('issuesCount' as any)}
            </span>
          )}
          <button
            onClick={onManualRefresh}
            disabled={isRefreshing}
            title={REFRESH_SYSTEM_STATUS_TITLE}
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
          {UPDATED_AT_LABEL} {formatTime(lastUpdated)}
        </div>
      )}

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

      {agents.length > 0 && (
        <div className="mt-2 pt-2 border-t dark:border-gray-700">
          <div className="flex items-center justify-between mb-1">
            <div className="text-[10px] text-secondary dark:text-gray-400">Local Agent CLI</div>
            <button
              onClick={onShowBridgeDialog}
              className="text-[10px] text-accent dark:text-blue-400 hover:opacity-80 dark:hover:text-blue-300 underline cursor-pointer"
            >
              How to connect?
            </button>
          </div>
          <div className="space-y-1">
            {agents.map((agent) => {
              const status = agentStatusView(agent);
              return (
                <div key={agent.id} className="flex items-center justify-between text-xs">
                  <span className="text-secondary dark:text-gray-400">{agent.name}</span>
                  <div className="flex items-center gap-1.5">
                    <div className={`w-1.5 h-1.5 rounded-full ${status.dotColor}`} />
                    <span className={`text-xs ${status.textColor}`}>{status.label}</span>
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

      <div className="mt-2 pt-2 border-t dark:border-gray-700">
        <Link
          href="/settings"
          className="text-[10px] text-accent dark:text-blue-400 hover:opacity-80 dark:hover:text-blue-300 underline"
        >
          {t('goToSettings' as any)} {GO_TO_SETTINGS_ARROW}
        </Link>
      </div>

      {showBridgeDialog && (
        <div
          className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-[60] p-4"
          onClick={onHideBridgeDialog}
        >
          <div
            className="bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-lg w-full max-h-[85vh] flex flex-col"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="p-5 border-b dark:border-gray-700 flex-shrink-0">
              <div className="flex items-center justify-between">
                <h3 className="text-base font-semibold text-gray-900 dark:text-gray-100">
                  Connect Local Agent CLI
                </h3>
                <button
                  onClick={onHideBridgeDialog}
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

            <div className="p-5 space-y-5 overflow-y-auto">
              <div>
                <div className="flex items-center gap-2 mb-2">
                  <span className="flex-shrink-0 w-5 h-5 rounded-full bg-blue-600 text-white text-[10px] font-bold flex items-center justify-center">1</span>
                  <span className="text-sm font-medium text-gray-900 dark:text-gray-100">Make sure at least one CLI Agent is installed</span>
                </div>
                <div className="ml-7 bg-gray-50 dark:bg-gray-700/50 rounded-lg p-3 space-y-1.5">
                  {LOCAL_AGENT_INSTALL_COMMANDS.map(({ name, cmd }) => (
                    <div key={name} className="flex items-center justify-between text-xs">
                      <span className="text-gray-700 dark:text-gray-300 font-medium">{name}</span>
                      <code className="text-[10px] bg-gray-200 dark:bg-gray-600 text-gray-600 dark:text-gray-300 px-1.5 py-0.5 rounded font-mono">{cmd}</code>
                    </div>
                  ))}
                </div>
              </div>

              <div>
                <div className="flex items-center gap-2 mb-2">
                  <span className="flex-shrink-0 w-5 h-5 rounded-full bg-blue-600 text-white text-[10px] font-bold flex items-center justify-center">2</span>
                  <span className="text-sm font-medium text-gray-900 dark:text-gray-100">Run the Bridge script in your terminal</span>
                </div>
                <div className="ml-7 mb-3 border border-blue-200 dark:border-blue-800 rounded-lg p-2.5">
                  <div className="text-sm font-bold text-blue-700 dark:text-blue-300 mb-1.5">{WINDOWS_SETUP_LABEL}</div>
                  <div className="relative">
                    <pre className="bg-gray-900 text-green-400 rounded p-2 text-[10px] font-mono overflow-x-auto whitespace-pre-wrap break-all">
                      {DEFAULT_WINDOWS_BRIDGE_COMMAND}
                    </pre>
                    <button
                      onClick={onCopyWindowsCommand}
                      className={`absolute top-1.5 right-1.5 px-2 py-0.5 text-[9px] rounded transition-colors ${copiedAll
                        ? 'bg-green-700 text-green-200'
                        : 'bg-gray-700 hover:bg-gray-600 text-gray-300'
                        }`}
                    >
                      {copiedAll ? COPIED_CHECK_LABEL : 'Copy'}
                    </button>
                  </div>
                </div>
                <div className="ml-7 border border-gray-200 dark:border-gray-600 rounded-lg p-2.5">
                  <div className="text-sm font-bold text-gray-700 dark:text-gray-300 mb-1.5">{MACOS_LINUX_SETUP_LABEL}</div>
                  <div className="relative">
                    <pre className="bg-gray-900 text-green-400 rounded p-2 text-[10px] font-mono overflow-x-auto whitespace-pre-wrap break-all">
                      {bridgeScriptPath ? `${bridgeScriptPath} --all` : DEFAULT_UNIX_BRIDGE_COMMAND}
                    </pre>
                    <button
                      onClick={onCopyUnixCommand}
                      className={`absolute top-1.5 right-1.5 px-2 py-0.5 text-[9px] rounded transition-colors ${copied
                        ? 'bg-green-700 text-green-200'
                        : 'bg-gray-700 hover:bg-gray-600 text-gray-300'
                        }`}
                    >
                      {copied ? COPIED_CHECK_LABEL : 'Copy'}
                    </button>
                  </div>
                </div>
                <p className="ml-7 text-[10px] text-gray-500 dark:text-gray-400 mt-1.5">
                  <code>--all</code> / <code>-All</code> connects all workspaces. Or use <code>--workspace-id {workspaceId}</code> for this workspace only.
                </p>
              </div>

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
