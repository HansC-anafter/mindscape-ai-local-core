'use client';

import { useCallback, useState } from 'react';

import { getApiBaseUrl } from '@/lib/api-url';

import {
  CODEX_INCONCLUSIVE_ERROR_CODES,
  CODEX_LOGIN_TIMEOUT_MS,
  CODEX_LOGOUT_TIMEOUT_MS,
  CODEX_PROBE_TIMEOUT_MS,
  errorMessageFromPayload,
  fetchWithTimeout,
  isAbortError,
  newCodexAccountHomePath,
  probeErrorCodeFromPayload,
} from './codexAccountHomeHelpers';
import type {
  AgentAuthActionResponse,
  AgentAuthStatusResponse,
  AgentTab,
  CliAgent,
  CodexAccountHomeTarget,
  CodexAccountHomeTargetsResponse,
  CodexTargetActionMessage,
  WorkspaceAgentInfo,
  WorkspaceAgentListResponse,
} from './types';

interface UseCodexAccountHomesControllerParams {
  workspaceId?: string;
  agentMap: Record<AgentTab, CliAgent>;
  setError: (message: string | null) => void;
}

const targetKeyFor = (target: CodexAccountHomeTarget) =>
  target.runtime_id || target.account_key || target.codex_home;

export function useCodexAccountHomesController({
  workspaceId,
  agentMap,
  setError,
}: UseCodexAccountHomesControllerParams) {
  const [workspaceAgents, setWorkspaceAgents] = useState<Record<string, WorkspaceAgentInfo>>({});
  const [authStatuses, setAuthStatuses] = useState<Record<string, AgentAuthStatusResponse>>({});
  const [authStatusLoading, setAuthStatusLoading] = useState<Record<string, boolean>>({});
  const [codexAccountHomes, setCodexAccountHomes] = useState<CodexAccountHomeTarget[]>([]);
  const [codexTargetsLoading, setCodexTargetsLoading] = useState(false);
  const [codexTargetActionLoading, setCodexTargetActionLoading] = useState<Record<string, string | null>>({});
  const [codexTargetActionMessages, setCodexTargetActionMessages] = useState<Record<string, CodexTargetActionMessage>>({});
  const [showCodexHomeCreator, setShowCodexHomeCreator] = useState(false);
  const [newCodexHome, setNewCodexHome] = useState('');
  const [addingCodexHome, setAddingCodexHome] = useState(false);
  const [addCodexHomeMessage, setAddCodexHomeMessage] = useState<CodexTargetActionMessage | null>(null);

  const loadWorkspaceAgents = useCallback(async () => {
    if (!workspaceId) {
      setWorkspaceAgents({});
      return;
    }
    try {
      const base = getApiBaseUrl();
      const resp = await fetch(`${base}/api/v1/workspaces/${workspaceId}/agents`);
      if (!resp.ok) return;
      const data: WorkspaceAgentListResponse = await resp.json();
      const nextMap: Record<string, WorkspaceAgentInfo> = {};
      for (const agent of data.agents || []) {
        nextMap[agent.id] = agent;
      }
      setWorkspaceAgents(nextMap);
    } catch {
      setWorkspaceAgents({});
    }
  }, [workspaceId]);

  const loadAgentAuthStatus = useCallback(async (agentId: AgentTab) => {
    const agent = agentMap[agentId];
    if (!workspaceId || !agent?.runtimeAgentId) return;
    setAuthStatusLoading((prev) => ({ ...prev, [agentId]: true }));
    try {
      const base = getApiBaseUrl();
      const resp = await fetch(
        `${base}/api/v1/workspaces/${workspaceId}/agents/${agent.runtimeAgentId}/auth-status`
      );
      if (!resp.ok) {
        const payload = await resp.json().catch(() => ({}));
        throw new Error((payload as Record<string, string>).detail || 'Failed to load auth status');
      }
      const data: AgentAuthStatusResponse = await resp.json();
      setAuthStatuses((prev) => ({ ...prev, [agentId]: data }));
    } catch (e: unknown) {
      setAuthStatuses((prev) => ({
        ...prev,
        [agentId]: {
          agent_id: agent.runtimeAgentId || agent.id,
          workspace_id: workspaceId,
          available: false,
          mode: agentId === 'claude' ? 'host_token' : 'host_session',
          status: 'error',
          error: e instanceof Error ? e.message : 'Failed to load auth status',
          login_supported: agentId === 'codex',
          logout_supported: agentId === 'codex',
        },
      }));
    } finally {
      setAuthStatusLoading((prev) => ({ ...prev, [agentId]: false }));
    }
  }, [agentMap, workspaceId]);

  const loadCodexAccountHomes = useCallback(async () => {
    const codexAgent = agentMap.codex;
    if (!workspaceId || !codexAgent?.runtimeAgentId) {
      setCodexAccountHomes([]);
      return;
    }
    setCodexTargetsLoading(true);
    try {
      const base = getApiBaseUrl();
      const resp = await fetch(
        `${base}/api/v1/workspaces/${workspaceId}/agents/${codexAgent.runtimeAgentId}/account-homes`
      );
      if (!resp.ok) {
        const payload = await resp.json().catch(() => ({}));
        throw new Error((payload as Record<string, string>).detail || 'Failed to load Codex account homes');
      }
      const data: CodexAccountHomeTargetsResponse = await resp.json();
      setCodexAccountHomes(data.targets || []);
    } catch (e: unknown) {
      setCodexAccountHomes([]);
      setError(e instanceof Error ? e.message : 'Failed to load Codex account homes');
    } finally {
      setCodexTargetsLoading(false);
    }
  }, [agentMap, setError, workspaceId]);

  const openCodexHomeCreator = useCallback(() => {
    setNewCodexHome((prev) => prev.trim() || newCodexAccountHomePath(codexAccountHomes));
    setAddCodexHomeMessage(null);
    setShowCodexHomeCreator(true);
  }, [codexAccountHomes]);

  const generateCodexHomePath = useCallback(() => {
    setNewCodexHome(newCodexAccountHomePath(codexAccountHomes));
  }, [codexAccountHomes]);

  const handleAddCodexHome = useCallback(async () => {
    if (!workspaceId) {
      setAddCodexHomeMessage({ kind: 'error', text: 'Workspace context is required.' });
      return;
    }
    const codexHome = newCodexHome.trim().replace(/\/+$/, '');
    if (!codexHome) {
      setAddCodexHomeMessage({ kind: 'error', text: 'Account-home path is required.' });
      return;
    }
    setAddingCodexHome(true);
    setAddCodexHomeMessage(null);
    setError(null);
    try {
      const base = getApiBaseUrl();
      const resp = await fetch(`${base}/api/v1/workspaces/${workspaceId}/agents/codex_cli/account-homes`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ codex_home: codexHome }),
      });
      const payload = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        throw new Error(errorMessageFromPayload(payload, 'Failed to add Codex account home'));
      }
      setNewCodexHome('');
      setShowCodexHomeCreator(false);
      setAddCodexHomeMessage({
        kind: 'success',
        text: 'Account home created. Use Login on the new row; email and scope will be filled from the completed OpenAI login.',
      });
      await loadCodexAccountHomes();
    } catch (e: unknown) {
      const message = e instanceof Error ? e.message : 'Failed to add Codex account home';
      setAddCodexHomeMessage({ kind: 'error', text: message });
      setError(message);
    } finally {
      setAddingCodexHome(false);
    }
  }, [loadCodexAccountHomes, newCodexHome, setError, workspaceId]);

  const handleCodexProbe = useCallback(async (
    agentId: Extract<AgentTab, 'codex'>,
    target: CodexAccountHomeTarget,
    options?: { afterLogin?: boolean }
  ) => {
    const agent = agentMap[agentId];
    if (!workspaceId || !agent.runtimeAgentId) {
      setError('Workspace runtime context is required for Codex token checks.');
      return false;
    }
    if (!target || (!target.runtime_id && !target.account_key && !target.codex_home)) {
      setError('Select a Codex account-home target before checking token usability.');
      return false;
    }
    const targetKey = targetKeyFor(target);
    setCodexTargetActionLoading((prev) => ({ ...prev, [targetKey]: 'probe' }));
    setCodexTargetActionMessages((prev) => ({
      ...prev,
      [targetKey]: {
        kind: 'info',
        text: options?.afterLogin
          ? 'Login command completed. Checking whether this token is usable now.'
          : 'Checking whether this account-home token is usable now.',
      },
    }));
    setError(null);
    try {
      const base = getApiBaseUrl();
      const resp = await fetchWithTimeout(
        `${base}/api/v1/workspaces/${workspaceId}/agents/${agent.runtimeAgentId}/account-homes/probe`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            runtime_id: target.runtime_id,
            account_key: target.account_key,
            codex_home: target.codex_home,
          }),
        },
        CODEX_PROBE_TIMEOUT_MS
      );
      const payload = await resp.json().catch(() => ({
        agent_id: agent.runtimeAgentId!,
        workspace_id: workspaceId,
        action: 'probe',
        success: false,
        output: '',
        error: 'Token check failed',
      }));
      if (!resp.ok) {
        throw new Error(errorMessageFromPayload(payload, 'Token check failed'));
      }
      const typedPayload = payload as AgentAuthActionResponse;
      const probeErrorCode = probeErrorCodeFromPayload(typedPayload);
      const probeWasInconclusive = CODEX_INCONCLUSIVE_ERROR_CODES.has(probeErrorCode);
      const resultMessage = typedPayload.success
        ? 'Token probe passed. This account-home is usable.'
        : probeWasInconclusive
          ? `Token probe was inconclusive: ${errorMessageFromPayload(typedPayload, 'unknown_error')}. This was not marked as auth failure.`
          : `Token probe failed: ${errorMessageFromPayload(typedPayload, 'unknown_error')}`;
      setCodexTargetActionMessages((prev) => ({
        ...prev,
        [targetKey]: {
          kind: typedPayload.success ? 'success' : probeWasInconclusive ? 'info' : 'error',
          text: resultMessage,
        },
      }));
      if (!typedPayload.success && !probeWasInconclusive) {
        setError(resultMessage);
      }
      await loadCodexAccountHomes();
      return typedPayload.success;
    } catch (e: unknown) {
      const message = isAbortError(e)
        ? 'Token probe timed out or was interrupted. The row was unlocked; refresh homes to re-check the account state.'
        : e instanceof Error
          ? e.message
          : 'Token check failed';
      setCodexTargetActionMessages((prev) => ({
        ...prev,
        [targetKey]: { kind: 'error', text: message },
      }));
      setError(message);
      await loadCodexAccountHomes();
      return false;
    } finally {
      setCodexTargetActionLoading((prev) => ({ ...prev, [targetKey]: null }));
    }
  }, [agentMap, loadCodexAccountHomes, setError, workspaceId]);

  const handleAgentAuthAction = useCallback(async (
    agentId: Extract<AgentTab, 'codex'>,
    action: 'login' | 'logout',
    target?: CodexAccountHomeTarget
  ) => {
    const agent = agentMap[agentId];
    if (!workspaceId || !agent.runtimeAgentId) {
      setError('Workspace runtime context is required for host-session actions.');
      return;
    }
    if (!target || (!target.runtime_id && !target.account_key && !target.codex_home)) {
      setError('Select a Codex account-home target before login or logout.');
      return;
    }
    const targetKey = targetKeyFor(target);
    setCodexTargetActionLoading((prev) => ({ ...prev, [targetKey]: action }));
    setCodexTargetActionMessages((prev) => ({
      ...prev,
      [targetKey]: {
        kind: 'info',
        text: action === 'login'
          ? 'Login started. Complete the browser flow for this account-home target.'
          : 'Logout started for this account-home target.',
      },
    }));
    setError(null);
    try {
      const base = getApiBaseUrl();
      const resp = await fetchWithTimeout(
        `${base}/api/v1/workspaces/${workspaceId}/agents/${agent.runtimeAgentId}/${action}`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            runtime_id: target.runtime_id,
            account_key: target.account_key,
            codex_home: target.codex_home,
          }),
        },
        action === 'login' ? CODEX_LOGIN_TIMEOUT_MS : CODEX_LOGOUT_TIMEOUT_MS
      );
      const payload = await resp.json().catch(() => ({
        agent_id: agent.runtimeAgentId!,
        workspace_id: workspaceId,
        action,
        success: false,
        output: '',
        error: `${action} failed`,
      }));
      if (!resp.ok) {
        throw new Error(errorMessageFromPayload(payload, `Failed to ${action}`));
      }
      const typedPayload = payload as AgentAuthActionResponse;
      if (typedPayload.success === false) {
        throw new Error(errorMessageFromPayload(typedPayload, `Failed to ${action}`));
      }
      setCodexTargetActionMessages((prev) => ({
        ...prev,
        [targetKey]: {
          kind: 'success',
          text: action === 'login'
            ? 'Login command completed. Checking whether this token is usable now.'
            : 'Logout command completed. Refreshing this account-home status.',
        },
      }));
      if (action === 'login') {
        setCodexAccountHomes((prev) => prev.map((item) => {
          if (targetKeyFor(item) !== targetKey) return item;
          return {
            ...item,
            probe_state: 'unknown',
            last_probe_error_code: null,
            last_error_code: null,
          };
        }));
        await handleCodexProbe(agentId, target, { afterLogin: true });
      } else {
        await loadCodexAccountHomes();
      }
      await loadAgentAuthStatus(agentId);
    } catch (e: unknown) {
      const message = isAbortError(e)
        ? `${action === 'login' ? 'Login' : 'Logout'} request timed out or was interrupted. The row was unlocked; refresh homes to re-check the account state.`
        : e instanceof Error
          ? e.message
          : `Failed to ${action}`;
      setCodexTargetActionMessages((prev) => ({
        ...prev,
        [targetKey]: { kind: 'error', text: message },
      }));
      setError(message);
    } finally {
      setCodexTargetActionLoading((prev) => ({ ...prev, [targetKey]: null }));
    }
  }, [agentMap, handleCodexProbe, loadAgentAuthStatus, loadCodexAccountHomes, setError, workspaceId]);

  const handleDeleteCodexHome = useCallback(async (target: CodexAccountHomeTarget) => {
    if (!workspaceId) {
      setError('Workspace runtime context is required to delete a Codex account home.');
      return;
    }
    if (!target.runtime_id) {
      setError('This Codex account-home row has no runtime ID.');
      return;
    }
    const targetKey = targetKeyFor(target);
    const homeName = target.codex_home.split('/').filter(Boolean).slice(-1)[0] || target.codex_home;
    const label = target.login_email || homeName;
    if (!window.confirm(`Delete Codex account home ${label}? This removes the runtime row and its managed local account-home directory.`)) {
      return;
    }
    setCodexTargetActionLoading((prev) => ({ ...prev, [targetKey]: 'delete' }));
    setCodexTargetActionMessages((prev) => ({
      ...prev,
      [targetKey]: { kind: 'info', text: 'Deleting this account-home target.' },
    }));
    setError(null);
    try {
      const base = getApiBaseUrl();
      const resp = await fetch(
        `${base}/api/v1/workspaces/${workspaceId}/agents/codex_cli/account-homes/${encodeURIComponent(target.runtime_id)}`,
        { method: 'DELETE' }
      );
      const payload = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        throw new Error(errorMessageFromPayload(payload, 'Failed to delete Codex account home'));
      }
      setAddCodexHomeMessage({
        kind: 'success',
        text: `Deleted account home ${homeName}.`,
      });
      await loadCodexAccountHomes();
      await loadAgentAuthStatus('codex');
    } catch (e: unknown) {
      const message = e instanceof Error ? e.message : 'Failed to delete Codex account home';
      setCodexTargetActionMessages((prev) => ({
        ...prev,
        [targetKey]: { kind: 'error', text: message },
      }));
      setError(message);
    } finally {
      setCodexTargetActionLoading((prev) => ({ ...prev, [targetKey]: null }));
    }
  }, [loadAgentAuthStatus, loadCodexAccountHomes, setError, workspaceId]);

  return {
    addCodexHomeMessage,
    addingCodexHome,
    authStatusLoading,
    authStatuses,
    codexAccountHomes,
    codexTargetActionLoading,
    codexTargetActionMessages,
    codexTargetsLoading,
    generateCodexHomePath,
    handleAddCodexHome,
    handleAgentAuthAction,
    handleCodexProbe,
    handleDeleteCodexHome,
    loadAgentAuthStatus,
    loadCodexAccountHomes,
    loadWorkspaceAgents,
    newCodexHome,
    openCodexHomeCreator,
    setNewCodexHome,
    setShowCodexHomeCreator,
    showCodexHomeCreator,
    workspaceAgents,
  };
}
