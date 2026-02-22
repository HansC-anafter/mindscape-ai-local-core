'use client';

import React, { useState, useEffect } from 'react';
// Helper function to get API base URL
// This will be resolved at runtime when component is installed
function getApiBaseUrl(): string {
  if (typeof window !== 'undefined') {
    const protocol = window.location.protocol;
    const hostname = window.location.hostname;
    return `${protocol}//${hostname}:8200`;
  }
  return process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8200';
}

const API_URL = getApiBaseUrl();

interface ChannelBinding {
  id: string;
  workspace_id: string;
  runtime_id: string;
  channel_id: string;
  channel_type: string;
  channel_name?: string;
  agency?: string;
  tenant?: string;
  chainagent?: string;
  binding_config?: {
    push_enabled?: boolean;
    notification_enabled?: boolean;
  };
  status: string;
  metadata?: Record<string, any>;
}

interface RuntimeEnvironment {
  id: string;
  name: string;
  status: string;
  config_url?: string;
  auth_status?: string;
  auth_type?: string;
}

interface Channel {
  id: string;
  channel_id?: string;
  channel_type?: string;
  type?: string;
  name?: string;
  channel_name?: string;
  agency?: string;
  tenant?: string;
  chainagent?: string;
}

interface SiteHubChannelBindingPanelProps {
  workspaceId: string;
}

export default function SiteHubChannelBindingPanel({ workspaceId }: SiteHubChannelBindingPanelProps) {
  const [bindings, setBindings] = useState<ChannelBinding[]>([]);
  const [runtimes, setRuntimes] = useState<RuntimeEnvironment[]>([]);
  const [channels, setChannels] = useState<Channel[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedRuntimeId, setSelectedRuntimeId] = useState<string | null>(null);
  const [loadingChannels, setLoadingChannels] = useState(false);
  const [showBindingModal, setShowBindingModal] = useState(false);
  const [selectedChannels, setSelectedChannels] = useState<Channel[]>([]);
  const [bindingConfig, setBindingConfig] = useState({
    push_enabled: true,
    notification_enabled: true,
  });
  const [saving, setSaving] = useState(false);

  // Workspace-level runtime config state
  const [configChainagentId, setConfigChainagentId] = useState('');
  const [configSiteKey, setConfigSiteKey] = useState('');
  const [configScope, setConfigScope] = useState<'workspace' | 'global'>('workspace');
  const [configLoading, setConfigLoading] = useState(false);
  const [configSaving, setConfigSaving] = useState(false);
  const [configDirty, setConfigDirty] = useState(false);
  const [showConfig, setShowConfig] = useState(false);
  const [oauthConnecting, setOauthConnecting] = useState(false);

  useEffect(() => {
    loadBindings();
    loadRuntimes();
  }, [workspaceId]);

  // Listen for OAuth popup completion
  useEffect(() => {
    const handleMessage = async (event: MessageEvent) => {
      const data = event.data;
      console.log('[SiteHub-DEBUG] postMessage received:', { origin: event.origin, type: data?.type, hasAccessToken: !!data?.access_token, success: data?.success });

      // Site-Hub domain flow: receives JWT via postMessage
      if (data?.type === 'runtime_oauth_complete') {
        console.log('[SiteHub-DEBUG] runtime_oauth_complete event:', { success: data.success, hasToken: !!data.access_token, hasRefresh: !!data.refresh_token, email: data.email, error: data.error, selectedRuntimeId });
        if (data.success && data.access_token && selectedRuntimeId) {
          try {
            const storeUrl = `${API_URL}/api/v1/runtime-oauth/${selectedRuntimeId}/store-token`;
            console.log('[SiteHub-DEBUG] Calling store-token:', storeUrl);
            // Store the JWT in the runtime via backend
            const resp = await fetch(storeUrl, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                access_token: data.access_token,
                refresh_token: data.refresh_token || '',
                expires_in: data.expires_in || 900,
                email: data.email || '',
              }),
            }
            );
            const respBody = await resp.clone().json().catch(() => ({}));
            console.log('[SiteHub-DEBUG] store-token response:', { status: resp.status, ok: resp.ok, body: respBody });
            if (resp.ok) {
              setOauthConnecting(false);
              console.log('[SiteHub-DEBUG] Token stored OK. Reloading runtimes...');
              loadRuntimes().then(() => {
                if (selectedRuntimeId) {
                  console.log('[SiteHub-DEBUG] Runtimes reloaded. Loading channels for:', selectedRuntimeId);
                  loadChannels(selectedRuntimeId);
                }
              });
            } else {
              const err = respBody;
              setOauthConnecting(false);
              console.error('[SiteHub-DEBUG] store-token FAILED:', err);
              setError(`Token store failed: ${err.detail}`);
            }
          } catch (e: any) {
            console.error('[SiteHub-DEBUG] store-token EXCEPTION:', e);
            setOauthConnecting(false);
            setError(`Token store error: ${e.message}`);
          }
        } else if (!data.success) {
          console.error('[SiteHub-DEBUG] OAuth flow FAILED:', data.error);
          setOauthConnecting(false);
          setError(`OAuth failed: ${data.error || 'Unknown error'}`);
        }
        return;
      }

      // Local-core direct flow (non-Site-Hub runtimes)
      if (data?.type === 'RUNTIME_OAUTH_RESULT') {
        console.log('[SiteHub-DEBUG] RUNTIME_OAUTH_RESULT:', data);
        setOauthConnecting(false);
        if (data.success) {
          loadRuntimes().then(() => {
            if (selectedRuntimeId) loadChannels(selectedRuntimeId);
          });
        } else {
          setError(`OAuth failed: ${data.error || 'Unknown error'}`);
        }
      }
    };
    window.addEventListener('message', handleMessage);
    return () => window.removeEventListener('message', handleMessage);
  }, [selectedRuntimeId]);

  const handleOAuthConnect = () => {
    if (!selectedRuntimeId) return;
    setOauthConnecting(true);
    setError(null);
    const authUrl = `${API_URL}/api/v1/runtime-oauth/${selectedRuntimeId}/authorize`;
    console.log('[SiteHub-DEBUG] Opening OAuth popup:', authUrl);
    const popup = window.open(authUrl, 'oauth_popup', 'width=600,height=700,scrollbars=yes');

    // Poll backend for auth_status change (COOP-safe — no popup communication needed)
    // The sitehub-jwt-landing endpoint stores the token server-side,
    // so we just need to detect when auth_status becomes "connected".
    if (popup) {
      console.log('[SiteHub-DEBUG] Popup opened. Starting auth_status polling...');
      const timer = setInterval(async () => {
        try {
          const resp = await fetch(`${API_URL}/api/v1/runtime-environments`);
          if (resp.ok) {
            const data = await resp.json();
            const runtime = (data.runtimes || []).find((rt: RuntimeEnvironment) => rt.id === selectedRuntimeId);
            if (runtime) {
              console.log('[SiteHub-DEBUG] Polling auth_status:', runtime.auth_status, 'auth_type:', runtime.auth_type);
              if (runtime.auth_status === 'connected' && runtime.auth_type === 'oauth2') {
                console.log('[SiteHub-DEBUG] OAuth COMPLETED via server-side landing! Reloading...');
                clearInterval(timer);
                setOauthConnecting(false);
                loadRuntimes().then(() => {
                  if (selectedRuntimeId) loadChannels(selectedRuntimeId);
                });
              }
            }
          }
        } catch (e) {
          console.warn('[SiteHub-DEBUG] Polling error (will retry):', e);
        }
      }, 2000);

      // Stop polling after 5 minutes
      setTimeout(() => {
        clearInterval(timer);
        setOauthConnecting(false);
        console.log('[SiteHub-DEBUG] Polling timeout (5 min)');
      }, 300000);
    }
  };

  // Load workspace config when runtime changes
  useEffect(() => {
    if (selectedRuntimeId && workspaceId) {
      loadWorkspaceConfig(selectedRuntimeId);
    }
  }, [selectedRuntimeId, workspaceId]);

  const loadWorkspaceConfig = async (runtimeId: string) => {
    try {
      setConfigLoading(true);
      const response = await fetch(
        `${API_URL}/api/v1/workspaces/${workspaceId}/runtime-config/${runtimeId}`
      );
      if (response.ok) {
        const data = await response.json();
        const merged = data.merged_metadata || {};
        const override = data.override;
        setConfigChainagentId(merged.chainagent_id || '');
        setConfigSiteKey(merged.site_key || '');
        setConfigScope(override?.scope || 'workspace');
        setConfigDirty(false);
        // Auto-show config if chainagent_id is missing
        if (!merged.chainagent_id) {
          setShowConfig(true);
        }
      }
    } catch (err) {
      console.error('Failed to load workspace config:', err);
    } finally {
      setConfigLoading(false);
    }
  };

  const saveWorkspaceConfig = async () => {
    if (!selectedRuntimeId) return;
    try {
      setConfigSaving(true);
      const response = await fetch(
        `${API_URL}/api/v1/workspaces/${workspaceId}/runtime-config/${selectedRuntimeId}`,
        {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            scope: configScope,
            config_overrides: {
              chainagent_id: configChainagentId || undefined,
              site_key: configSiteKey || undefined,
            },
          }),
        }
      );
      if (response.ok) {
        setConfigDirty(false);
        // Reload channels with new config
        if (selectedRuntimeId) {
          loadChannels(selectedRuntimeId);
        }
      } else {
        const errData = await response.json().catch(() => ({}));
        setError(errData.detail || 'Failed to save config');
      }
    } catch (err) {
      console.error('Failed to save workspace config:', err);
      setError(err instanceof Error ? err.message : 'Failed to save config');
    } finally {
      setConfigSaving(false);
    }
  };

  const loadBindings = async () => {
    try {
      setLoading(true);
      setError(null);
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 5000); // 5 second timeout

      const response = await fetch(`${API_URL}/api/v1/capabilities/site_hub_integration/channel-bindings?workspace_id=${workspaceId}`, {
        signal: controller.signal,
      });
      clearTimeout(timeoutId);

      if (response.ok) {
        const data = await response.json();
        setBindings(data.bindings || []);
      } else if (response.status === 404) {
        // 404 is expected if no bindings exist yet - silently handle
        setBindings([]);
        if (process.env.NODE_ENV === 'development') {
          console.debug('[SiteHubChannelBindingPanel] No channel bindings endpoint found, using empty list');
        }
      } else {
        setError('Failed to load channel bindings');
      }
    } catch (err: any) {
      if (err.name === 'AbortError') {
        setError('Request timeout - please try again');
      } else {
        console.error('Failed to load channel bindings:', err);
        setError(err instanceof Error ? err.message : 'Failed to load channel bindings');
      }
    } finally {
      setLoading(false);
    }
  };

  const loadRuntimes = async () => {
    try {
      console.log('[SiteHub-DEBUG] loadRuntimes: fetching...');
      const response = await fetch(`${API_URL}/api/v1/runtime-environments`);
      if (response.ok) {
        const data = await response.json();
        const allRuntimes = data.runtimes || [];
        const siteHubRuntimes = allRuntimes.filter(
          (rt: RuntimeEnvironment) => rt.name.toLowerCase().includes('site-hub') || rt.id.includes('site-hub')
        );
        console.log('[SiteHub-DEBUG] loadRuntimes: total=%d, siteHub=%d', allRuntimes.length, siteHubRuntimes.length);
        siteHubRuntimes.forEach((rt: RuntimeEnvironment) => {
          console.log('[SiteHub-DEBUG]   runtime: id=%s name=%s auth_status=%s auth_type=%s config_url=%s', rt.id, rt.name, rt.auth_status, rt.auth_type, rt.config_url);
        });
        setRuntimes(siteHubRuntimes);
        if (siteHubRuntimes.length > 0) {
          setSelectedRuntimeId(siteHubRuntimes[0].id);
        }
      }
    } catch (err) {
      console.error('[SiteHub-DEBUG] loadRuntimes ERROR:', err);
    }
  };

  const loadChannels = async (runtimeId: string) => {
    if (!runtimeId) return;

    try {
      setLoadingChannels(true);
      setError(null);

      // Add timeout to prevent hanging
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 15000); // 15 second timeout

      const toolUrl = `${API_URL}/api/v1/tools/execute?profile_id=${workspaceId}`;
      const toolBody = {
        tool_name: 'site_hub_integration.site_hub_get_console_kit_channels',
        arguments: {
          runtime_id: runtimeId,
          workspace_id: workspaceId,
        },
      };
      console.log('[SiteHub-DEBUG] loadChannels: calling tool API:', toolUrl, JSON.stringify(toolBody));
      const startTime = Date.now();

      // Call the tool via API - use unified tool execution endpoint
      const response = await fetch(toolUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(toolBody),
        signal: controller.signal,
      });

      clearTimeout(timeoutId);
      const elapsed = Date.now() - startTime;
      console.log('[SiteHub-DEBUG] loadChannels: response status=%d, elapsed=%dms', response.status, elapsed);

      if (response.ok) {
        const data = await response.json();
        console.log('[SiteHub-DEBUG] loadChannels: response body:', JSON.stringify(data).substring(0, 1000));
        // Tool execution API returns: { success, tool_name, result: { success, channels: [...] } }
        if (data.success && data.result) {
          // channels may be at data.result.channels or data.result.result.channels
          const channelsData = data.result.result || data.result;
          if (channelsData.channels) {
            console.log('[SiteHub-DEBUG] loadChannels: SUCCESS, %d channels', channelsData.channels.length);
            setChannels(channelsData.channels);
          } else if (channelsData.success === false) {
            if (channelsData.auth_expired) {
              console.warn('[SiteHub-DEBUG] loadChannels: auth expired, triggering re-auth');
              setError('OAuth 認證已過期，請重新連結 Google 帳戶');
              // Reload runtimes to pick up updated auth_status
              loadRuntimes();
            } else {
              console.error('[SiteHub-DEBUG] loadChannels: tool returned error:', channelsData.error);
              setError(channelsData.error || 'Failed to load channels');
            }
            setChannels([]);
          } else {
            console.error('[SiteHub-DEBUG] loadChannels: unexpected result shape:', JSON.stringify(data.result).substring(0, 500));
            setError('Unexpected response format');
            setChannels([]);
          }
        } else {
          const errorMsg = data.result?.error || data.error || 'Failed to load channels';
          console.error('[SiteHub-DEBUG] loadChannels: execution failed:', errorMsg, data);
          setError(errorMsg);
          setChannels([]);
        }
      } else if (response.status === 404) {
        console.warn('[SiteHub-DEBUG] loadChannels: 404 - endpoint not found');
        setChannels([]);
      } else {
        const errorData = await response.json().catch(() => ({}));
        console.error('[SiteHub-DEBUG] loadChannels: HTTP error:', response.status, errorData);
        setError(errorData.detail || 'Failed to load channels');
        setChannels([]);
      }
    } catch (err: any) {
      if (err.name === 'AbortError') {
        console.error('[SiteHub-DEBUG] loadChannels: TIMEOUT (15s)');
        setError('載入 Channels 超時，請稍後再試');
        setChannels([]); // Clear channels on timeout
      } else {
        console.error('[SiteHub-DEBUG] loadChannels: EXCEPTION:', err);
        setError(err instanceof Error ? err.message : 'Failed to load channels');
      }
    } finally {
      setLoadingChannels(false);
    }
  };

  const handleRuntimeChange = (runtimeId: string) => {
    setSelectedRuntimeId(runtimeId);
    setChannels([]);
    if (runtimeId) {
      loadChannels(runtimeId);
    }
  };

  const handleBindChannel = async () => {
    if (selectedChannels.length === 0 || !selectedRuntimeId) return;

    try {
      setSaving(true);
      setError(null);

      const errors: string[] = [];
      for (const ch of selectedChannels) {
        const response = await fetch(`${API_URL}/api/v1/capabilities/site_hub_integration/channel-bindings`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            workspace_id: workspaceId,
            runtime_id: selectedRuntimeId,
            channel_id: ch.channel_id || ch.id,
            channel_type: ch.channel_type || ch.type || 'unknown',
            channel_name: ch.channel_name || ch.name,
            agency: ch.agency,
            tenant: ch.tenant,
            chainagent: ch.chainagent,
            binding_config: bindingConfig,
          }),
        });

        if (!response.ok) {
          const errorData = await response.json().catch(() => ({}));
          errors.push(errorData.detail || `Failed to bind ${ch.channel_name || ch.name || ch.id}`);
        }
      }

      if (errors.length > 0) {
        setError(errors.join('; '));
      } else {
        setShowBindingModal(false);
        setSelectedChannels([]);
        await loadBindings();
      }
    } catch (err) {
      console.error('Failed to bind channel:', err);
      setError(err instanceof Error ? err.message : 'Failed to bind channel');
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteBinding = async (bindingId: string) => {
    if (!confirm('確定要刪除此 Channel 綁定嗎？')) return;

    try {
      const response = await fetch(`${API_URL}/api/v1/capabilities/site_hub_integration/channel-bindings/${bindingId}`, {
        method: 'DELETE',
      });

      if (response.ok) {
        await loadBindings();
      } else {
        setError('Failed to delete binding');
      }
    } catch (err) {
      console.error('Failed to delete binding:', err);
      setError(err instanceof Error ? err.message : 'Failed to delete binding');
    }
  };

  if (loading && bindings.length === 0) {
    return (
      <div className="p-4">
        <div className="text-gray-500 dark:text-gray-400">載入中...</div>
      </div>
    );
  }

  return (
    <>
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
              Site-Hub Channel 綁定
            </h3>
            <p className="text-sm text-gray-600 dark:text-gray-400">
              管理 Site-Hub Channel 與工作空間的綁定關係
            </p>
          </div>
          <button
            onClick={() => {
              if (selectedRuntimeId) {
                loadChannels(selectedRuntimeId);
              }
              setShowBindingModal(true);
            }}
            disabled={!selectedRuntimeId || runtimes.length === 0}
            className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors"
          >
            綁定 Channel
          </button>
        </div>

        {error && (
          <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-3">
            <p className="text-sm text-red-700 dark:text-red-300">{error}</p>
          </div>
        )}

        {/* Runtime Selection */}
        {runtimes.length > 0 && (
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              選擇 Site-Hub Runtime
            </label>
            <select
              value={selectedRuntimeId || ''}
              onChange={(e) => handleRuntimeChange(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
            >
              <option value="">-- 選擇 Runtime --</option>
              {runtimes.map((runtime) => (
                <option key={runtime.id} value={runtime.id}>
                  {runtime.name} ({runtime.status})
                </option>
              ))}
            </select>
          </div>
        )}

        {/* Workspace Runtime Config */}
        {selectedRuntimeId && (
          <div className="border border-gray-200 dark:border-gray-700 rounded-lg">
            <button
              onClick={() => setShowConfig(!showConfig)}
              className="w-full flex items-center justify-between px-4 py-3 text-sm font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors rounded-lg"
            >
              <span>⚙️ Runtime 設定 {configChainagentId ? '(已設定)' : '(未設定)'}</span>
              <span className="text-xs">{showConfig ? '▲' : '▼'}</span>
            </button>
            {showConfig && (
              <div className="px-4 pb-4 space-y-3 border-t border-gray-200 dark:border-gray-700">
                {configLoading ? (
                  <div className="text-sm text-gray-500 py-2">載入設定中...</div>
                ) : (
                  <>
                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                        ChainAgent ID
                      </label>
                      <input
                        type="text"
                        value={configChainagentId}
                        onChange={(e) => { setConfigChainagentId(e.target.value); setConfigDirty(true); }}
                        placeholder="ChainAgent UUID"
                        className="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                      />
                      <p className="mt-1 text-xs text-gray-400">從 Site-Hub Console 取得</p>
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                        Site Key
                      </label>
                      <input
                        type="text"
                        value={configSiteKey}
                        onChange={(e) => { setConfigSiteKey(e.target.value); setConfigDirty(true); }}
                        placeholder="openseo-basic-anafter-co-..."
                        className="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                        適用範圍
                      </label>
                      <div className="flex gap-4">
                        <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
                          <input
                            type="radio"
                            name="configScope"
                            value="workspace"
                            checked={configScope === 'workspace'}
                            onChange={() => { setConfigScope('workspace'); setConfigDirty(true); }}
                          />
                          僅此工作區
                        </label>
                        <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
                          <input
                            type="radio"
                            name="configScope"
                            value="global"
                            checked={configScope === 'global'}
                            onChange={() => { setConfigScope('global'); setConfigDirty(true); }}
                          />
                          全域 (所有工作區共用)
                        </label>
                      </div>
                      <p className="mt-1 text-xs text-gray-400">
                        工作區設定優先於全域設定
                      </p>
                    </div>
                    {configDirty && (
                      <div className="flex justify-end gap-2 pt-1">
                        <button
                          onClick={() => { if (selectedRuntimeId) loadWorkspaceConfig(selectedRuntimeId); }}
                          className="px-3 py-1.5 text-sm rounded-md border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700"
                        >
                          取消
                        </button>
                        <button
                          onClick={saveWorkspaceConfig}
                          disabled={configSaving}
                          className="px-3 py-1.5 text-sm rounded-md bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50"
                        >
                          {configSaving ? '儲存中...' : '儲存設定'}
                        </button>
                      </div>
                    )}
                  </>
                )}
              </div>
            )}
          </div>
        )}

        {/* Google OAuth Authentication */}
        {selectedRuntimeId && (() => {
          const selectedRuntime = runtimes.find(r => r.id === selectedRuntimeId);
          const authStatus = selectedRuntime?.auth_status || 'disconnected';
          const isConnected = authStatus === 'connected';
          const isExpired = authStatus === 'expired';
          return (
            <div className={`border rounded-lg p-4 ${isExpired ? 'border-orange-400 dark:border-orange-600 bg-orange-50 dark:bg-orange-900/10' : 'border-gray-200 dark:border-gray-700'}`}>
              <div className="flex items-center justify-between">
                <div>
                  <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300">
                    Google OAuth 認證
                  </h4>
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                    {isConnected
                      ? '已連結 — Registry API 認證可用'
                      : isExpired
                        ? '⚠️ 認證已過期 — 請重新連結以載入 Channels'
                        : '尚未連結 — 需要 Google OAuth 認證才能載入 Channels'}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <span className={`inline-block w-2 h-2 rounded-full ${isConnected ? 'bg-green-500' : isExpired ? 'bg-orange-400 animate-pulse' : 'bg-red-400'
                    }`} />
                  <span className="text-xs text-gray-500 dark:text-gray-400">
                    {isConnected ? '已連結' : isExpired ? '已過期' : '未連結'}
                  </span>
                </div>
              </div>
              <button
                onClick={handleOAuthConnect}
                disabled={oauthConnecting}
                className={`mt-3 w-full flex items-center justify-center gap-2 px-4 py-2 text-sm font-medium rounded-md transition-colors ${isConnected
                  ? 'border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700'
                  : isExpired
                    ? 'bg-orange-500 text-white hover:bg-orange-600'
                    : 'bg-blue-600 text-white hover:bg-blue-700'
                  } disabled:opacity-50`}
              >
                {oauthConnecting
                  ? '連結中...'
                  : isConnected
                    ? '重新連結 Google'
                    : isExpired
                      ? '🔄 重新連結 Google（認證已過期）'
                      : '連結 Google 帳戶'}
              </button>
            </div>
          );
        })()}

        {runtimes.length === 0 && (
          <div className="bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-lg p-4">
            <div className="flex items-start justify-between">
              <div className="flex-1">
                <p className="text-sm text-yellow-700 dark:text-yellow-300 mb-2">
                  尚未註冊 Site-Hub Runtime。請先執行 setup playbook 來註冊 runtime。
                </p>
              </div>
              <button
                onClick={async () => {
                  try {
                    const response = await fetch(`${API_URL}/api/v1/playbooks/execute/start?playbook_code=site_hub_setup&workspace_id=${workspaceId}&profile_id=default-user`, {
                      method: 'POST',
                      headers: { 'Content-Type': 'application/json' },
                      body: JSON.stringify({ inputs: {} })
                    });
                    if (response.ok) {
                      const data = await response.json();
                      window.location.href = `/workspaces/${workspaceId}/playbooks/site_hub_setup?execution_id=${data.execution_id}`;
                    } else {
                      const error = await response.json().catch(() => ({ detail: 'Failed to start playbook' }));
                      setError(error.detail || 'Failed to start setup playbook');
                    }
                  } catch (err) {
                    setError(err instanceof Error ? err.message : 'Failed to start setup playbook');
                  }
                }}
                className="ml-4 px-4 py-2 bg-yellow-600 text-white rounded-md hover:bg-yellow-700 transition-colors text-sm whitespace-nowrap"
              >
                執行 Setup
              </button>
            </div>
          </div>
        )}

        {/* Bindings List */}
        {bindings.length === 0 ? (
          <div className="text-center py-8 text-gray-500 dark:text-gray-400">
            <p>尚未綁定任何 Channel</p>
            <p className="text-sm mt-2">點擊「綁定 Channel」開始設定</p>
          </div>
        ) : (
          <div className="space-y-3">
            {bindings.map((binding) => (
              <div
                key={binding.id}
                className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg p-4"
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-2">
                      <span className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                        {binding.channel_name || binding.channel_id}
                      </span>
                      <span className="text-xs px-2 py-1 bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 rounded">
                        {binding.channel_type}
                      </span>
                      {binding.status === 'active' && (
                        <span className="text-xs px-2 py-1 bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300 rounded">
                          啟用
                        </span>
                      )}
                    </div>
                    <div className="space-y-1 text-sm text-gray-600 dark:text-gray-400">
                      {binding.agency && (
                        <div>
                          <span className="font-medium">Agency:</span> {binding.agency}
                        </div>
                      )}
                      {binding.tenant && (
                        <div>
                          <span className="font-medium">Tenant:</span> {binding.tenant}
                        </div>
                      )}
                      {binding.chainagent && (
                        <div>
                          <span className="font-medium">ChainAgent:</span> {binding.chainagent}
                        </div>
                      )}
                      {binding.binding_config && (
                        <div className="mt-2">
                          <span className="font-medium">設定:</span>
                          <div className="ml-4 space-y-1">
                            {binding.binding_config.push_enabled && (
                              <div className="text-xs">✓ 推送啟用</div>
                            )}
                            {binding.binding_config.notification_enabled && (
                              <div className="text-xs">✓ 通知啟用</div>
                            )}
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                  <button
                    onClick={() => handleDeleteBinding(binding.id)}
                    className="px-3 py-1.5 text-sm text-red-600 dark:text-red-400 hover:text-red-700 dark:hover:text-red-300 font-medium"
                  >
                    刪除
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Binding Modal */}
      {showBindingModal && (
        <div
          className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50"
          onClick={(e) => {
            if (e.target === e.currentTarget) {
              setShowBindingModal(false);
              setSelectedChannels([]);
            }
          }}
        >
          <div className="bg-white dark:bg-gray-800 rounded-lg p-6 max-w-2xl w-full mx-4 max-h-[90vh] overflow-y-auto relative">
            {/* Close button - always enabled, even during loading */}
            <button
              onClick={() => {
                setShowBindingModal(false);
                setSelectedChannels([]);
                setLoadingChannels(false); // Reset loading state when closing
                setChannels([]); // Clear channels when closing
              }}
              className="absolute top-4 right-4 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors z-10"
              aria-label="Close"
              disabled={false} // Always allow closing
            >
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>

            <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4 pr-8">
              綁定 Site-Hub Channel
            </h3>

            {loadingChannels ? (
              <div className="text-center py-8 text-gray-500 dark:text-gray-400">
                <div className="mb-4">載入 Channels...</div>
                {error && (
                  <div className="mt-4 text-sm text-red-600 dark:text-red-400">
                    {error}
                  </div>
                )}
                <button
                  onClick={() => {
                    setShowBindingModal(false);
                    setSelectedChannels([]);
                    setLoadingChannels(false);
                    setChannels([]);
                  }}
                  className="mt-4 px-4 py-2 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-md transition-colors"
                >
                  取消載入並關閉
                </button>
              </div>
            ) : channels.length === 0 ? (
              <div className="space-y-4">
                <div className="text-center py-8 text-gray-500 dark:text-gray-400">
                  <p>No channels found</p>
                  <p className="text-sm mt-2">Please configure Site Key and ChainAgent ID in Settings → Runtime Environments → Site-Hub</p>
                </div>
                <div className="flex justify-end pt-4 border-t">
                  <button
                    onClick={() => {
                      setShowBindingModal(false);
                      setSelectedChannels([]);
                    }}
                    className="px-4 py-2 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-md transition-colors"
                  >
                    關閉
                  </button>
                </div>
              </div>
            ) : (
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    選擇 Channel
                  </label>
                  <div className="space-y-2 max-h-60 overflow-y-auto">
                    {channels.map((channel) => {
                      const isSelected = selectedChannels.some(c => c.id === channel.id);
                      return (
                        <div
                          key={channel.id}
                          onClick={() => {
                            setSelectedChannels(prev =>
                              isSelected
                                ? prev.filter(c => c.id !== channel.id)
                                : [...prev, channel]
                            );
                          }}
                          className={`p-3 border rounded-lg cursor-pointer transition-colors ${isSelected
                            ? 'border-blue-500 bg-blue-50 dark:bg-blue-900/20'
                            : 'border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600'
                            }`}
                        >
                          <div className="flex items-center gap-3">
                            <input
                              type="checkbox"
                              checked={isSelected}
                              readOnly
                              className="rounded text-blue-600 pointer-events-none"
                            />
                            <div className="flex-1">
                              <div className="font-medium text-gray-900 dark:text-gray-100">
                                {channel.channel_name || channel.name || channel.channel_id || channel.id}
                              </div>
                              <div className="text-sm text-gray-600 dark:text-gray-400 mt-1">
                                {channel.agency && <span>Agency: {channel.agency} </span>}
                                {channel.tenant && <span>Tenant: {channel.tenant} </span>}
                                {channel.chainagent && <span>ChainAgent: {channel.chainagent}</span>}
                              </div>
                              <div className="text-xs text-gray-500 dark:text-gray-500 mt-1">
                                類型: {channel.channel_type || channel.type || 'unknown'}
                              </div>
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>

                {selectedChannels.length > 0 && (
                  <div className="space-y-3">
                    <div>
                      <label className="flex items-center gap-2">
                        <input
                          type="checkbox"
                          checked={bindingConfig.push_enabled}
                          onChange={(e) =>
                            setBindingConfig({ ...bindingConfig, push_enabled: e.target.checked })
                          }
                          className="rounded"
                        />
                        <span className="text-sm text-gray-700 dark:text-gray-300">啟用推送</span>
                      </label>
                    </div>
                    <div>
                      <label className="flex items-center gap-2">
                        <input
                          type="checkbox"
                          checked={bindingConfig.notification_enabled}
                          onChange={(e) =>
                            setBindingConfig({
                              ...bindingConfig,
                              notification_enabled: e.target.checked,
                            })
                          }
                          className="rounded"
                        />
                        <span className="text-sm text-gray-700 dark:text-gray-300">啟用通知</span>
                      </label>
                    </div>
                  </div>
                )}

                <div className="flex justify-end gap-2 pt-4 border-t">
                  <button
                    onClick={() => {
                      setShowBindingModal(false);
                      setSelectedChannels([]);
                    }}
                    className="px-4 py-2 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-md transition-colors"
                  >
                    取消
                  </button>
                  <button
                    onClick={handleBindChannel}
                    disabled={selectedChannels.length === 0 || saving}
                    className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors"
                  >
                    {saving ? '綁定中...' : `綁定${selectedChannels.length > 0 ? ` (${selectedChannels.length})` : ''}`}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
}

