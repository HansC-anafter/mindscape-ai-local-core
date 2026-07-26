'use client';

import React, { useEffect, useState } from 'react';
import { useSearchParams } from 'next/navigation';

import { useT } from '../../../../lib/i18n';
import { Card } from '../Card';
import { InlineAlert } from '../InlineAlert';
import { ConnectionStatusSection } from './socialMediaProviderSettings/ConnectionStatusSection';
import { DiscoveredToolsSection } from './socialMediaProviderSettings/DiscoveredToolsSection';
import { LineConnectionModeSection } from './socialMediaProviderSettings/LineConnectionModeSection';
import { OAuthConfigurationSection } from './socialMediaProviderSettings/OAuthConfigurationSection';
import { RemoteConfigurationSection } from './socialMediaProviderSettings/RemoteConfigurationSection';
import { WorkspaceProviderSettingsPanels } from './socialMediaProviderSettings/WorkspaceProviderSettingsPanels';
import { getOAuthCallbackUrl, SOCIAL_MEDIA_PLATFORMS } from './socialMediaProviderSettings/constants';
import {
  deleteSocialConnection,
  getOAuthAuthorizationUrl,
  loadSocialConnection,
  loadSocialConnectionTools,
  loadSocialProviderSettingsPanels,
  saveOAuthConnection,
  saveRemoteConnection,
} from './socialMediaProviderSettings/resourceActions';
import type {
  OAuthConfig,
  RegisteredTool,
  RemoteConfig,
  SettingsExtensionPanel,
  SocialMediaConnection,
  SocialMediaProviderSettingsProps,
} from './socialMediaProviderSettings/types';

const defaultOAuthConfig = (provider: string): OAuthConfig => ({
  client_id: '',
  client_secret: '',
  redirect_uri: getOAuthCallbackUrl(provider),
});

const defaultRemoteConfig = (): RemoteConfig => ({
  cluster_url: '',
  channel_id: '',
  api_token: '',
});

export function SocialMediaProviderSettings({ provider, workspaceId, onBack }: SocialMediaProviderSettingsProps) {
  const t = useT();
  const searchParams = useSearchParams();
  const [connection, setConnection] = useState<SocialMediaConnection | null>(null);
  const [tools, setTools] = useState<RegisteredTool[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [connecting, setConnecting] = useState(false);
  const [loadingTools, setLoadingTools] = useState(false);
  const [savingConfig, setSavingConfig] = useState(false);
  const [settingsPanels, setSettingsPanels] = useState<SettingsExtensionPanel[]>([]);
  const [loadingSettingsPanels, setLoadingSettingsPanels] = useState(false);
  const [connectionMode, setConnectionMode] = useState<'local' | 'remote'>('local');
  const [oauthConfig, setOauthConfig] = useState<OAuthConfig>(defaultOAuthConfig(provider));
  const [remoteConfig, setRemoteConfig] = useState<RemoteConfig>(defaultRemoteConfig);

  const platform = SOCIAL_MEDIA_PLATFORMS[provider];
  const isLine = provider === 'line';
  const isPackWorkspaceProvider = provider === 'youtube' || settingsPanels.length > 0;
  const platformLabel = platform?.label || provider;

  useEffect(() => {
    const loadProviderSettingsPanels = async () => {
      try {
        setLoadingSettingsPanels(true);
        setSettingsPanels(await loadSocialProviderSettingsPanels(provider, workspaceId));
      } catch (err) {
        console.warn('Failed to load social media provider settings panels:', err);
        setSettingsPanels([]);
      } finally {
        setLoadingSettingsPanels(false);
      }
    };
    void loadProviderSettingsPanels();
  }, [provider, workspaceId]);

  useEffect(() => {
    if (provider === 'youtube') {
      setConnection(null);
      setTools([]);
      setLoading(false);
      return;
    }

    const oauthSuccess = searchParams?.get('oauth_success' as any);
    const oauthError = searchParams?.get('oauth_error' as any);
    const callbackProvider = searchParams?.get('provider' as any);

    if (oauthSuccess === '1' && callbackProvider === provider) {
      setSuccess(t('socialMediaConnected' as any));
      const newUrl = new URL(window.location.href);
      newUrl.searchParams.delete('oauth_success');
      newUrl.searchParams.delete('connection_id');
      window.history.replaceState({}, '', newUrl.toString());
      void loadConnection();
    } else if (oauthError === '1' && callbackProvider === provider) {
      const errorDesc = searchParams?.get('error_description' as any) || 'Unknown error';
      setError(`OAuth failed: ${errorDesc}`);
      const newUrl = new URL(window.location.href);
      newUrl.searchParams.delete('oauth_error');
      newUrl.searchParams.delete('error_description');
      window.history.replaceState({}, '', newUrl.toString());
      void loadConnection();
    } else {
      void loadConnection();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [provider]);

  const loadConnection = async () => {
    try {
      setLoading(true);
      const conn = await loadSocialConnection(provider);
      setConnection(conn);
      if (conn) {
        if (conn.connection_type === 'remote') {
          setConnectionMode('remote');
          setRemoteConfig({
            cluster_url: conn.remote_cluster_url || '',
            channel_id: conn.remote_connection_id || '',
            api_token: '',
          });
        } else {
          setConnectionMode('local');
          setOauthConfig({
            client_id: conn.config?.client_id || '',
            client_secret: '',
            redirect_uri: conn.config?.redirect_uri || getOAuthCallbackUrl(provider),
          });
        }
        await loadTools(conn.id);
      } else {
        setTools([]);
        setConnectionMode('local');
        setOauthConfig(defaultOAuthConfig(provider));
        setRemoteConfig(defaultRemoteConfig());
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load connection');
    } finally {
      setLoading(false);
    }
  };

  const loadTools = async (connectionId: string) => {
    try {
      setLoadingTools(true);
      setTools(await loadSocialConnectionTools(connectionId));
    } catch (err) {
      console.warn('Failed to load tools:', err);
      setTools([]);
    } finally {
      setLoadingTools(false);
    }
  };

  const handleSaveOAuthConfig = async () => {
    if (!oauthConfig.client_id || !oauthConfig.client_secret) {
      setError('Client ID and Client Secret are required');
      return;
    }

    try {
      setSavingConfig(true);
      setError(null);
      await saveOAuthConnection(provider, platformLabel, connection, oauthConfig);
      await loadConnection();
      setSuccess('OAuth configuration saved');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save OAuth configuration');
    } finally {
      setSavingConfig(false);
    }
  };

  const handleSaveRemoteConfig = async () => {
    if (!remoteConfig.cluster_url || !remoteConfig.channel_id) {
      setError('Cloud Remote Tools URL and Channel ID are required');
      return;
    }

    try {
      setSavingConfig(true);
      setError(null);
      await saveRemoteConnection(provider, platformLabel, connection, remoteConfig);
      await loadConnection();
      setSuccess('Cloud Remote Tools configuration saved');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save Cloud Remote Tools configuration');
    } finally {
      setSavingConfig(false);
    }
  };

  const handleConnect = async () => {
    try {
      setConnecting(true);
      setError(null);
      if (!connection?.config?.client_id || !connection?.config?.client_secret) {
        setError('Please save OAuth configuration first (Client ID and Client Secret)');
        setConnecting(false);
        return;
      }
      window.location.href = await getOAuthAuthorizationUrl(provider, connection);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start OAuth flow');
      setConnecting(false);
    }
  };

  const handleDisconnect = async () => {
    if (!confirm(t('socialMediaDisconnectConfirm' as any))) {
      return;
    }

    try {
      if (!connection) {
        throw new Error('Connection not found');
      }
      await deleteSocialConnection(connection.id);
      setSuccess(t('socialMediaNotConnected' as any));
      await loadConnection();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to disconnect');
    }
  };

  if (!platform) {
    return (
      <Card>
        <InlineAlert type="error" message={`Unknown provider: ${provider}`} />
      </Card>
    );
  }

  if (loading) {
    return (
      <Card>
        <div className="text-center py-8">{t('loading' as any)}</div>
      </Card>
    );
  }

  const isConnected = connection?.is_active && connection?.is_validated;
  const PlatformIcon = platform.Icon;

  return (
    <Card>
      <div className="mb-6">
        <button
          onClick={onBack}
          className="text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100 mb-4 flex items-center gap-1"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
          {t('back' as any)}
        </button>
        <div className="flex items-center gap-3 mb-2">
          <div className={`w-12 h-12 rounded-lg border border-gray-200 dark:border-gray-700 flex items-center justify-center ${platform.color} bg-gray-50 dark:bg-gray-800`}>
            <PlatformIcon className="w-6 h-6" />
          </div>
          <div>
            <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100">
              {t(platform.label as any)}
            </h2>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              {t('socialMediaIntegrationDescription' as any)}
            </p>
          </div>
        </div>
      </div>

      {error && <InlineAlert type="error" message={error} onDismiss={() => setError(null)} />}
      {success && <InlineAlert type="success" message={success} onDismiss={() => setSuccess(null)} />}

      <div className="space-y-6">
        {provider === 'youtube' && !workspaceId && (
          <InlineAlert
            type="warning"
            message="Open YouTube settings from a workspace. Global shared YouTube credentials are not supported."
          />
        )}

        <WorkspaceProviderSettingsPanels
          loading={loadingSettingsPanels}
          panels={settingsPanels}
          workspaceId={workspaceId}
        />

        {isLine && !isPackWorkspaceProvider && (
          <LineConnectionModeSection
            connectionMode={connectionMode}
            onConnectionModeChange={setConnectionMode}
          />
        )}

        {!isPackWorkspaceProvider && (!isLine || connectionMode === 'local') && (
          <OAuthConfigurationSection
            connection={connection}
            oauthConfig={oauthConfig}
            provider={provider}
            savingConfig={savingConfig}
            onOauthConfigChange={setOauthConfig}
            onSave={handleSaveOAuthConfig}
          />
        )}

        {isLine && !isPackWorkspaceProvider && connectionMode === 'remote' && (
          <RemoteConfigurationSection
            connection={connection}
            remoteConfig={remoteConfig}
            savingConfig={savingConfig}
            onRemoteConfigChange={setRemoteConfig}
            onSave={handleSaveRemoteConfig}
          />
        )}

        {!isPackWorkspaceProvider && (
          <ConnectionStatusSection
            connection={connection}
            connecting={connecting}
            isConnected={Boolean(isConnected)}
            onConnect={handleConnect}
            onDisconnect={handleDisconnect}
          />
        )}

        {!isPackWorkspaceProvider && isConnected && connection && (
          <DiscoveredToolsSection loadingTools={loadingTools} tools={tools} />
        )}
      </div>
    </Card>
  );
}
