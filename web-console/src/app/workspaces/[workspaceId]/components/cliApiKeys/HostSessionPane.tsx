'use client';

import { Plus, RefreshCw, Trash2 } from 'lucide-react';

import {
  codexScopeMeta,
  codexStatusMeta,
  shortKey,
  shortRuntimeId,
} from './codexAccountHomeHelpers';
import type {
  AgentAuthStatusResponse,
  AgentTab,
  CliAgent,
  CodexAccountHomeTarget,
  CodexTargetActionMessage,
  WorkspaceAgentInfo,
} from './types';

interface HostSessionPaneProps {
  addCodexHomeMessage: CodexTargetActionMessage | null;
  addingCodexHome: boolean;
  agent: CliAgent;
  codexAccountHomes: CodexAccountHomeTarget[];
  codexTargetActionLoading: Record<string, string | null>;
  codexTargetActionMessages: Record<string, CodexTargetActionMessage>;
  codexTargetsLoading: boolean;
  loading: boolean;
  newCodexHome: string;
  runtimeInfo: WorkspaceAgentInfo | null;
  showCodexHomeCreator: boolean;
  status?: AgentAuthStatusResponse;
  workspaceId?: string;
  onAddCodexHome: () => void;
  onAgentAuthAction: (
    agentId: Extract<AgentTab, 'codex'>,
    action: 'login' | 'logout',
    target?: CodexAccountHomeTarget
  ) => void;
  onCancelCodexHomeCreator: () => void;
  onCodexProbe: (agentId: Extract<AgentTab, 'codex'>, target: CodexAccountHomeTarget) => void;
  onDeleteCodexHome: (target: CodexAccountHomeTarget) => void;
  onGenerateCodexHome: () => void;
  onLoadAgentAuthStatus: (agentId: AgentTab) => void;
  onLoadCodexAccountHomes: () => void;
  onNewCodexHomeChange: (value: string) => void;
  onOpenCodexHomeCreator: () => void;
}

const messageClassName = (kind: CodexTargetActionMessage['kind']) => {
  if (kind === 'success') {
    return 'border-green-200 bg-green-50 text-green-700 dark:border-green-800 dark:bg-green-900/20 dark:text-green-300';
  }
  if (kind === 'error') {
    return 'border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300';
  }
  return 'border-blue-200 bg-blue-50 text-blue-700 dark:border-blue-800 dark:bg-blue-900/20 dark:text-blue-300';
};

export function HostSessionPane({
  addCodexHomeMessage,
  addingCodexHome,
  agent,
  codexAccountHomes,
  codexTargetActionLoading,
  codexTargetActionMessages,
  codexTargetsLoading,
  loading,
  newCodexHome,
  runtimeInfo,
  showCodexHomeCreator,
  status,
  workspaceId,
  onAddCodexHome,
  onAgentAuthAction,
  onCancelCodexHomeCreator,
  onCodexProbe,
  onDeleteCodexHome,
  onGenerateCodexHome,
  onLoadAgentAuthStatus,
  onLoadCodexAccountHomes,
  onNewCodexHomeChange,
  onOpenCodexHomeCreator,
}: HostSessionPaneProps) {
  return (
    <div className="space-y-4">
      <div className="bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg p-3 space-y-2">
        <p className="text-xs font-medium text-amber-700 dark:text-amber-300">
          {agent.id === 'codex' ? 'Host Session' : 'Host Token'}
        </p>
        <p className="text-xs text-amber-600 dark:text-amber-400">
          {agent.id === 'codex'
            ? 'This uses the real host Codex CLI login state. API keys saved here are only for pure API mode.'
            : 'Claude Code host-token mode is managed on the host. The backend does not fake a login state for it.'}
        </p>
      </div>

      <div className="rounded-lg border border-gray-200 dark:border-gray-700 p-3 space-y-2">
        <div className="flex items-center gap-2 text-xs">
          <span className={`w-2 h-2 rounded-full ${
            runtimeInfo?.status === 'available' ? 'bg-green-500' : 'bg-gray-400'
          }`} />
          <span className="text-gray-700 dark:text-gray-300">
            Runtime surface: {runtimeInfo?.status || 'unknown'}
          </span>
          {runtimeInfo?.transport && (
            <span className="px-1.5 py-0.5 rounded bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400">
              {runtimeInfo.transport}
            </span>
          )}
          {runtimeInfo?.reason && (
            <span className="text-gray-500 dark:text-gray-400">
              {runtimeInfo.reason}
            </span>
          )}
        </div>

        {!workspaceId && (
          <p className="text-xs text-gray-500 dark:text-gray-400">
            Open this panel from a workspace to inspect live host-session status.
          </p>
        )}

        {workspaceId && (
          <>
            <div className="flex items-center gap-2 flex-wrap">
              {agent.id === 'codex' && (
                <button
                  type="button"
                  onClick={onLoadCodexAccountHomes}
                  disabled={codexTargetsLoading}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md border border-gray-300 text-gray-700 hover:bg-gray-50 disabled:opacity-50 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-800"
                >
                  <RefreshCw className={`h-3.5 w-3.5 ${codexTargetsLoading ? 'animate-spin' : ''}`} />
                  {codexTargetsLoading ? 'Refreshing homes...' : 'Refresh Homes'}
                </button>
              )}
              <button
                type="button"
                onClick={() => onLoadAgentAuthStatus(agent.id)}
                disabled={loading || runtimeInfo?.status !== 'available'}
                className="px-3 py-1.5 text-xs font-medium rounded-md border border-gray-300 text-gray-700 hover:bg-gray-50 disabled:opacity-50 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-800"
              >
                {loading ? 'Checking...' : 'Refresh'}
              </button>
            </div>

            {status && (
              <HostStatusPanel status={status} />
            )}

            {agent.id === 'codex' && (
              <CodexAccountHomesPanel
                addCodexHomeMessage={addCodexHomeMessage}
                addingCodexHome={addingCodexHome}
                codexAccountHomes={codexAccountHomes}
                codexTargetActionLoading={codexTargetActionLoading}
                codexTargetActionMessages={codexTargetActionMessages}
                codexTargetsLoading={codexTargetsLoading}
                newCodexHome={newCodexHome}
                showCodexHomeCreator={showCodexHomeCreator}
                onAddCodexHome={onAddCodexHome}
                onAgentAuthAction={onAgentAuthAction}
                onCancelCodexHomeCreator={onCancelCodexHomeCreator}
                onCodexProbe={onCodexProbe}
                onDeleteCodexHome={onDeleteCodexHome}
                onGenerateCodexHome={onGenerateCodexHome}
                onNewCodexHomeChange={onNewCodexHomeChange}
                onOpenCodexHomeCreator={onOpenCodexHomeCreator}
              />
            )}
          </>
        )}
      </div>
    </div>
  );
}

function HostStatusPanel({ status }: { status: AgentAuthStatusResponse }) {
  return (
    <div className={`rounded-md border p-2 text-[11px] ${
      status.status === 'authenticated'
        ? 'border-green-200 dark:border-green-800 bg-green-50/60 dark:bg-green-900/10 text-green-700 dark:text-green-300'
        : status.status === 'manual_required'
          ? 'border-blue-200 dark:border-blue-800 bg-blue-50/60 dark:bg-blue-900/10 text-blue-700 dark:text-blue-300'
          : status.status === 'unavailable'
            ? 'border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900/20 text-gray-600 dark:text-gray-300'
            : 'border-amber-200 dark:border-amber-800 bg-amber-50/60 dark:bg-amber-900/10 text-amber-700 dark:text-amber-300'
    }`}>
      <div className="font-medium">Host auth status: {status.status}</div>
      {status.note && <div className="mt-1">{status.note}</div>}
      {status.output && (
        <pre className="mt-2 whitespace-pre-wrap break-words text-[11px] font-mono">
          {status.output}
        </pre>
      )}
      {status.error && <div className="mt-1">{status.error}</div>}
      {status.manual_command && (
        <div className="mt-2">
          Manual command: <code className="font-mono">{status.manual_command}</code>
        </div>
      )}
    </div>
  );
}

interface CodexAccountHomesPanelProps {
  addCodexHomeMessage: CodexTargetActionMessage | null;
  addingCodexHome: boolean;
  codexAccountHomes: CodexAccountHomeTarget[];
  codexTargetActionLoading: Record<string, string | null>;
  codexTargetActionMessages: Record<string, CodexTargetActionMessage>;
  codexTargetsLoading: boolean;
  newCodexHome: string;
  showCodexHomeCreator: boolean;
  onAddCodexHome: () => void;
  onAgentAuthAction: (
    agentId: Extract<AgentTab, 'codex'>,
    action: 'login' | 'logout',
    target?: CodexAccountHomeTarget
  ) => void;
  onCancelCodexHomeCreator: () => void;
  onCodexProbe: (agentId: Extract<AgentTab, 'codex'>, target: CodexAccountHomeTarget) => void;
  onDeleteCodexHome: (target: CodexAccountHomeTarget) => void;
  onGenerateCodexHome: () => void;
  onNewCodexHomeChange: (value: string) => void;
  onOpenCodexHomeCreator: () => void;
}

function CodexAccountHomesPanel(props: CodexAccountHomesPanelProps) {
  const {
    addCodexHomeMessage,
    addingCodexHome,
    codexAccountHomes,
    codexTargetsLoading,
    newCodexHome,
    showCodexHomeCreator,
    onAddCodexHome,
    onCancelCodexHomeCreator,
    onGenerateCodexHome,
    onNewCodexHomeChange,
    onOpenCodexHomeCreator,
  } = props;

  return (
    <div className="space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-xs font-semibold text-gray-800 dark:text-gray-200">
            Account homes
          </div>
          <div className="mt-1 text-[11px] leading-4 text-gray-500 dark:text-gray-400">
            Scope is read from OpenAI token claims. Login is rejected when the selected row and returned account identity do not match.
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <button
            type="button"
            onClick={onOpenCodexHomeCreator}
            className="inline-flex items-center gap-1.5 rounded-md bg-gray-900 px-2.5 py-1.5 text-[11px] font-medium text-white hover:bg-gray-800 dark:bg-gray-100 dark:text-gray-900 dark:hover:bg-white"
          >
            <Plus className="h-3.5 w-3.5" />
            Add Home
          </button>
          <span className="rounded-full border border-gray-200 px-2 py-0.5 text-[11px] font-medium text-gray-600 dark:border-gray-700 dark:text-gray-300">
            {codexAccountHomes.length} targets
          </span>
        </div>
      </div>

      {showCodexHomeCreator && (
        <div className="rounded-md border border-blue-200 bg-blue-50/60 p-3 dark:border-blue-800 dark:bg-blue-900/10">
          <label className="block text-[11px] font-semibold text-blue-800 dark:text-blue-200">
            New local CODEX_HOME path
          </label>
          <p className="mt-1 text-[11px] text-blue-700 dark:text-blue-300">
            This is a local account-home directory, not an email field. After Login completes, email, account key, and scope are read from the OpenAI token claims.
          </p>
          <div className="mt-2 flex flex-col gap-2 lg:flex-row">
            <input
              type="text"
              value={newCodexHome}
              placeholder="/Users/shock/.mindscape/runtime/codex-home-pool/accounts/acct-..."
              onChange={(event) => onNewCodexHomeChange(event.target.value)}
              className="min-w-0 flex-1 rounded-md border border-blue-200 bg-white px-3 py-2 font-mono text-xs text-gray-900 outline-none focus:border-blue-500 dark:border-blue-800 dark:bg-gray-950 dark:text-gray-100"
            />
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={onGenerateCodexHome}
                disabled={addingCodexHome}
                className="rounded-md border border-blue-200 bg-white px-3 py-2 text-xs font-medium text-blue-700 hover:bg-blue-50 disabled:opacity-50 dark:border-blue-800 dark:bg-gray-950 dark:text-blue-300 dark:hover:bg-blue-900/20"
              >
                Generate
              </button>
              <button
                type="button"
                onClick={onAddCodexHome}
                disabled={addingCodexHome || !newCodexHome.trim()}
                className="rounded-md bg-blue-600 px-3 py-2 text-xs font-medium text-white hover:bg-blue-700 disabled:opacity-50"
              >
                {addingCodexHome ? 'Adding...' : 'Create'}
              </button>
              <button
                type="button"
                onClick={onCancelCodexHomeCreator}
                disabled={addingCodexHome}
                className="rounded-md border border-gray-300 bg-white px-3 py-2 text-xs font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50 dark:border-gray-700 dark:bg-gray-950 dark:text-gray-300 dark:hover:bg-gray-900"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {addCodexHomeMessage && (
        <div className={`rounded-md border px-3 py-2 text-[11px] ${messageClassName(addCodexHomeMessage.kind)}`}>
          {addCodexHomeMessage.text}
        </div>
      )}

      {codexAccountHomes.length === 0 ? (
        <p className="text-xs text-gray-500 dark:text-gray-400">
          {codexTargetsLoading ? 'Loading account homes...' : 'No account-home targets found.'}
        </p>
      ) : (
        <div className="space-y-2.5">
          {codexAccountHomes.map((target) => (
            <CodexAccountHomeRow key={target.runtime_id || target.account_key || target.codex_home} target={target} {...props} />
          ))}
        </div>
      )}
    </div>
  );
}

function CodexAccountHomeRow({
  codexTargetActionLoading,
  codexTargetActionMessages,
  onAgentAuthAction,
  onCodexProbe,
  onDeleteCodexHome,
  target,
}: CodexAccountHomesPanelProps & { target: CodexAccountHomeTarget }) {
  const targetKey = target.runtime_id || target.account_key || target.codex_home;
  const targetAction = codexTargetActionLoading[targetKey];
  const actionMessage = codexTargetActionMessages[targetKey];
  const errorCode = target.last_probe_error_code || target.last_error_code;
  const statusMeta = codexStatusMeta(target);
  const StatusIcon = statusMeta.icon;
  const scopeMeta = codexScopeMeta(target);
  const ScopeIcon = scopeMeta.icon;
  const tokenState = target.has_refresh
    ? 'refresh token present'
    : target.has_access
      ? 'access token only'
      : 'no token material';
  const homeName = target.codex_home.split('/').filter(Boolean).slice(-1)[0] || target.codex_home;

  return (
    <div className={`rounded-md border p-3 ${statusMeta.row}`}>
      <div className="grid gap-3 lg:grid-cols-[minmax(0,1.7fr)_minmax(150px,0.65fr)_minmax(170px,0.75fr)_auto] lg:items-start">
        <div className="min-w-0 space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <div className="truncate text-sm font-semibold text-gray-900 dark:text-gray-100">
              {target.login_email || target.runtime_id}
            </div>
            <span className="rounded-full border border-gray-200 bg-white px-2 py-0.5 text-[11px] font-mono text-gray-500 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-400">
              {homeName}
            </span>
          </div>
          <div className="font-mono text-[11px] text-gray-500 dark:text-gray-400">
            {shortRuntimeId(target.runtime_id)}
          </div>
          {target.account_key && (
            <div className="font-mono text-[11px] text-gray-600 dark:text-gray-300" title={target.account_key}>
              account_key {shortKey(target.account_key)}
            </div>
          )}
        </div>

        <div className={`inline-flex min-w-0 items-center gap-2 rounded-md border px-2.5 py-2 text-xs ${scopeMeta.badge}`}>
          <ScopeIcon className="h-4 w-4 shrink-0" />
          <div className="min-w-0">
            <div className="truncate font-semibold">{scopeMeta.label}</div>
            <div className="truncate text-[11px] opacity-80">{scopeMeta.sublabel}</div>
          </div>
        </div>

        <div className={`inline-flex min-w-0 items-center gap-2 rounded-md border px-2.5 py-2 text-xs ${statusMeta.badge}`}>
          <StatusIcon className="h-4 w-4 shrink-0" />
          <div className="min-w-0">
            <div className="truncate font-semibold">{statusMeta.label}</div>
            <div className="truncate text-[11px] opacity-80">{statusMeta.detail}</div>
          </div>
        </div>

        <div className="flex items-center gap-1.5 lg:justify-end">
          <button
            type="button"
            onClick={() => onCodexProbe('codex', target)}
            disabled={!!targetAction}
            className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-medium rounded-md border border-gray-300 bg-white text-gray-700 hover:bg-gray-50 disabled:opacity-50 dark:border-gray-600 dark:bg-gray-900 dark:text-gray-300 dark:hover:bg-gray-800"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${targetAction === 'probe' ? 'animate-spin' : ''}`} />
            {targetAction === 'probe' ? 'Checking...' : 'Check'}
          </button>
          <button
            type="button"
            onClick={() => onAgentAuthAction('codex', 'login', target)}
            disabled={!!targetAction}
            className="px-3 py-1.5 text-xs font-medium rounded-md bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {targetAction === 'login' ? 'Logging in...' : 'Login'}
          </button>
          <button
            type="button"
            onClick={() => onAgentAuthAction('codex', 'logout', target)}
            disabled={!!targetAction}
            className="px-3 py-1.5 text-xs font-medium rounded-md border border-gray-300 bg-white text-gray-700 hover:bg-gray-50 disabled:opacity-50 dark:border-gray-600 dark:bg-gray-900 dark:text-gray-300 dark:hover:bg-gray-800"
          >
            {targetAction === 'logout' ? 'Logging out...' : 'Logout'}
          </button>
          <button
            type="button"
            onClick={() => onDeleteCodexHome(target)}
            disabled={!!targetAction || !target.runtime_id}
            title="Delete account home"
            aria-label={`Delete account home ${homeName}`}
            className="inline-flex h-[30px] w-[30px] items-center justify-center rounded-md border border-red-200 bg-white text-red-600 hover:bg-red-50 disabled:opacity-50 dark:border-red-900/70 dark:bg-gray-900 dark:text-red-300 dark:hover:bg-red-950/30"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
      <div className="mt-3 grid gap-2 text-[11px] text-gray-500 dark:text-gray-400 sm:grid-cols-2 lg:grid-cols-4">
        <span>{tokenState}</span>
        {target.last_probe_success_at && <span>passed {target.last_probe_success_at}</span>}
        {errorCode && <span className="text-amber-700 dark:text-amber-300">error {errorCode}</span>}
        {target.cooldown_until && <span>cooldown {target.cooldown_until}</span>}
        {target.account_organization_id && (
          <span className="truncate font-mono" title={target.account_organization_id}>
            org {shortKey(target.account_organization_id)}
          </span>
        )}
      </div>
      {actionMessage && (
        <div className={`mt-3 rounded-md border px-3 py-2 text-[11px] ${messageClassName(actionMessage.kind)}`}>
          {actionMessage.text}
        </div>
      )}
    </div>
  );
}
