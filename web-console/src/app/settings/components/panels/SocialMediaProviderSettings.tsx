'use client';

import React, { useState, useEffect } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import { t } from '../../../../lib/i18n';
import { Card } from '../Card';
import { InlineAlert } from '../InlineAlert';
import {
  TwitterIcon,
  FacebookIcon,
  InstagramIcon,
  LinkedInIcon,
  YouTubeIcon,
  LineIcon,
} from '../SocialMediaIcons';

import { getApiBaseUrl } from '../../../../lib/api-url';

const API_URL = getApiBaseUrl();
const PROFILE_ID = 'default-user';

interface SocialMediaConnection {
  id: string;
  name: string;
  tool_type: string;
  is_active: boolean;
  is_validated: boolean;
  oauth_token?: string;
  last_validated_at?: string;
  connection_type?: 'local' | 'remote';
  remote_cluster_url?: string;
  remote_connection_id?: string;
  config?: {
    client_id?: string;
    client_secret?: string;
    redirect_uri?: string;
  };
}

interface RegisteredTool {
  tool_id: string;
  site_id: string;
  provider: string;
  display_name: string;
  category: string;
  description: string;
  danger_level: string;
  enabled: boolean;
  read_only: boolean;
}

const SOCIAL_MEDIA_PLATFORMS: Record<string, { label: string; Icon: React.ComponentType<{ className?: string }>; color: string }> = {
  twitter: { label: 'twitterIntegration', Icon: TwitterIcon, color: 'text-blue-500' },
  facebook: { label: 'facebookIntegration', Icon: FacebookIcon, color: 'text-blue-600' },
  instagram: { label: 'instagramIntegration', Icon: InstagramIcon, color: 'text-pink-500' },
  linkedin: { label: 'linkedinIntegration', Icon: LinkedInIcon, color: 'text-blue-700' },
  youtube: { label: 'youtubeIntegration', Icon: YouTubeIcon, color: 'text-red-600' },
  line: { label: 'lineIntegration', Icon: LineIcon, color: 'text-green-500' },
};

interface SocialMediaProviderSettingsProps {
  provider: string;
  onBack: () => void;
}

export function SocialMediaProviderSettings({ provider, onBack }: SocialMediaProviderSettingsProps) {
  const searchParams = useSearchParams();
  const router = useRouter();
  const [connection, setConnection] = useState<SocialMediaConnection | null>(null);
  const [tools, setTools] = useState<RegisteredTool[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [connecting, setConnecting] = useState(false);
  const [loadingTools, setLoadingTools] = useState(false);
  const [savingConfig, setSavingConfig] = useState(false);

  // Connection mode (only for LINE)
  const [connectionMode, setConnectionMode] = useState<'local' | 'remote'>('local');

  // OAuth configuration form (for local mode)
  const [oauthConfig, setOauthConfig] = useState({
    client_id: '',
    client_secret: '',
    redirect_uri: '',
  });

  // Cloud Remote Tools configuration (for remote mode)
  const [remoteConfig, setRemoteConfig] = useState({
    cluster_url: '',
    channel_id: '',
    api_token: '',
  });

  const platform = SOCIAL_MEDIA_PLATFORMS[provider];
  const isLine = provider === 'line';

  useEffect(() => {
    const oauthSuccess = searchParams?.get('oauth_success');
    const oauthError = searchParams?.get('oauth_error');
    const callbackProvider = searchParams?.get('provider');

    if (oauthSuccess === '1' && callbackProvider === provider) {
      setSuccess(t('socialMediaConnected'));
      // Clear OAuth parameters but keep provider
      const newUrl = new URL(window.location.href);
      newUrl.searchParams.delete('oauth_success');
      newUrl.searchParams.delete('connection_id');
      window.history.replaceState({}, '', newUrl.toString());
      // Load connection after clearing params
      loadConnection();
    } else if (oauthError === '1' && callbackProvider === provider) {
      const errorDesc = searchParams?.get('error_description') || 'Unknown error';
      setError(`OAuth failed: ${errorDesc}`);
      // Clear OAuth error parameters but keep provider
      const newUrl = new URL(window.location.href);
      newUrl.searchParams.delete('oauth_error');
      newUrl.searchParams.delete('error_description');
      window.history.replaceState({}, '', newUrl.toString());
      // Load connection after clearing params
      loadConnection();
    } else {
      // Normal load (not from OAuth callback)
      loadConnection();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [provider]);

  const loadConnection = async () => {
    try {
      setLoading(true);
      const response = await fetch(
        `${API_URL}/api/v1/tools/connections?profile_id=${PROFILE_ID}&tool_type=${provider}`
      );
      if (!response.ok) {
        throw new Error('Failed to load connection');
      }
      const data: SocialMediaConnection[] = await response.json();
      if (data.length > 0) {
        const conn = data[0];
        setConnection(conn);

        // Determine connection mode from connection
        if (conn.connection_type === 'remote') {
          setConnectionMode('remote');
          setRemoteConfig({
            cluster_url: conn.remote_cluster_url || '',
            channel_id: conn.remote_connection_id || '',
            api_token: '', // Don't show existing token
          });
        } else {
          setConnectionMode('local');
          setOauthConfig({
            client_id: conn.config?.client_id || '',
            client_secret: '', // Don't show existing secret
            redirect_uri: conn.config?.redirect_uri || `${API_URL}/api/v1/tools/oauth/${provider}/callback`,
          });
        }

        // Load discovered tools for this connection
        await loadTools(conn.id);
      } else {
        setConnection(null);
        setTools([]);
        setConnectionMode('local');
        // Set default redirect URI
        setOauthConfig({
          client_id: '',
          client_secret: '',
          redirect_uri: `${API_URL}/api/v1/tools/oauth/${provider}/callback`,
        });
        setRemoteConfig({
          cluster_url: '',
          channel_id: '',
          api_token: '',
        });
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
      // Use the correct endpoint for getting tools by connection
      const response = await fetch(
        `${API_URL}/api/v1/tools/registry?site_id=${connectionId}&profile_id=${PROFILE_ID}`
      );
      if (!response.ok) {
        // If 404 or other error, just set empty tools (connection might not have tools yet)
        if (response.status === 404) {
          setTools([]);
          return;
        }
        throw new Error('Failed to load tools');
      }
      const data: RegisteredTool[] = await response.json();
      setTools(data || []);
    } catch (err) {
      // Don't show error for tools loading, just log it
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

      const updateData: any = {
        config: {
          client_id: oauthConfig.client_id,
          client_secret: oauthConfig.client_secret,
          redirect_uri: oauthConfig.redirect_uri,
        },
      };

      if (connection) {
        const response = await fetch(
          `${API_URL}/api/v1/tools/connections/${connection.id}?profile_id=${PROFILE_ID}`,
          {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(updateData),
          }
        );

        if (!response.ok) {
          throw new Error('Failed to save OAuth configuration');
        }

        await loadConnection();
        setSuccess('OAuth configuration saved');
      } else {
        const response = await fetch(
          `${API_URL}/api/v1/tools/connections?profile_id=${PROFILE_ID}`,
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              tool_type: provider,
              connection_type: 'local',
              name: `${platform.label} Connection`,
              ...updateData,
            }),
          }
        );

        if (!response.ok) {
          throw new Error('Failed to create connection');
        }

        await loadConnection();
        setSuccess('OAuth configuration saved');
      }
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

      const connectionData: any = {
        tool_type: provider,
        connection_type: 'remote',
        name: `${platform.label} Connection (Cloud Remote Tools)`,
        remote_cluster_url: remoteConfig.cluster_url,
        remote_connection_id: remoteConfig.channel_id,
        config: {},
      };

      if (remoteConfig.api_token) {
        connectionData.config.api_token = remoteConfig.api_token;
      }

      if (connection) {
        const response = await fetch(
          `${API_URL}/api/v1/tools/connections/${connection.id}?profile_id=${PROFILE_ID}`,
          {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(connectionData),
          }
        );

        if (!response.ok) {
          throw new Error('Failed to save Cloud Remote Tools configuration');
        }

        await loadConnection();
        setSuccess('Cloud Remote Tools configuration saved');
      } else {
        const response = await fetch(
          `${API_URL}/api/v1/tools/connections?profile_id=${PROFILE_ID}`,
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(connectionData),
          }
        );

        if (!response.ok) {
          throw new Error('Failed to create connection');
        }

        await loadConnection();
        setSuccess('Cloud Remote Tools configuration saved');
      }
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

      // Check if OAuth config is saved
      if (!connection?.config?.client_id || !connection?.config?.client_secret) {
        setError('Please save OAuth configuration first (Client ID and Client Secret)');
        setConnecting(false);
        return;
      }

      const redirectUri = connection.config.redirect_uri || `${API_URL}/api/v1/tools/oauth/${provider}/callback`;
      const authorizeUrl = `${API_URL}/api/v1/tools/oauth/${provider}/authorize?redirect_uri=${encodeURIComponent(redirectUri)}&profile_id=${PROFILE_ID}&client_id=${encodeURIComponent(connection.config.client_id)}&client_secret=${encodeURIComponent(connection.config.client_secret)}`;

      console.log(`[${provider} OAuth] Requesting authorization URL from: ${authorizeUrl}`);

      const response = await fetch(authorizeUrl);

      if (!response.ok) {
        let errorMessage = 'Failed to get authorization URL';
        try {
          const errorData = await response.json();
          errorMessage = errorData.detail || errorData.message || errorMessage;
          console.error(`[Line OAuth] Error response:`, errorData);
        } catch {
          // If response is not JSON, try to get text
          try {
            const errorText = await response.text();
            if (errorText) {
              errorMessage = errorText;
            }
            console.error(`[Line OAuth] Error text:`, errorText);
          } catch {
            // Fallback to status text
            errorMessage = response.statusText || `HTTP ${response.status}`;
            console.error(`[Line OAuth] HTTP ${response.status}: ${response.statusText}`);
          }
        }
        throw new Error(errorMessage);
      }

      const data = await response.json();
      console.log(`[Line OAuth] Received authorization URL:`, data);

      if (data.authorization_url) {
        console.log(`[Line OAuth] Redirecting to: ${data.authorization_url}`);
        window.location.href = data.authorization_url;
      } else {
        console.error(`[Line OAuth] No authorization_url in response:`, data);
        throw new Error('No authorization URL received');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start OAuth flow');
      setConnecting(false);
    }
  };

  const handleDisconnect = async () => {
    if (!confirm(t('socialMediaDisconnectConfirm'))) {
      return;
    }

    try {
      if (!connection) {
        throw new Error('Connection not found');
      }

      const response = await fetch(
        `${API_URL}/api/v1/tools/connections/${connection.id}?profile_id=${PROFILE_ID}`,
        { method: 'DELETE' }
      );

      if (!response.ok) {
        throw new Error('Failed to disconnect');
      }

      setSuccess(t('socialMediaNotConnected'));
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
        <div className="text-center py-8">{t('loading')}</div>
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
          {t('back')}
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
              {t('socialMediaIntegrationDescription')}
            </p>
          </div>
        </div>
      </div>

      {error && <InlineAlert type="error" message={error} onDismiss={() => setError(null)} />}
      {success && <InlineAlert type="success" message={success} onDismiss={() => setSuccess(null)} />}

      <div className="space-y-6">
        {/* Connection Mode Selection (LINE only) */}
        {isLine && (
          <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-4">
            <h3 className="font-medium text-gray-900 dark:text-gray-100 mb-4">
              {t('lineConnectionMode')}
            </h3>
            <div className="space-y-3">
              <label className="flex items-start gap-3 p-3 border border-gray-200 dark:border-gray-700 rounded-md cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800/50">
                <input
                  type="radio"
                  name="connectionMode"
                  value="local"
                  checked={connectionMode === 'local'}
                  onChange={(e) => setConnectionMode(e.target.value as 'local' | 'remote')}
                  className="mt-1"
                />
                <div className="flex-1">
                  <div className="font-medium text-gray-900 dark:text-gray-100">
                    {t('lineDirectConnection')}
                  </div>
                  <div className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                    {t('lineDirectConnectionDescription')}
                  </div>
                </div>
              </label>
              <label className="flex items-start gap-3 p-3 border border-gray-200 dark:border-gray-700 rounded-md cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800/50">
                <input
                  type="radio"
                  name="connectionMode"
                  value="remote"
                  checked={connectionMode === 'remote'}
                  onChange={(e) => setConnectionMode(e.target.value as 'local' | 'remote')}
                  className="mt-1"
                />
                <div className="flex-1">
                  <div className="font-medium text-gray-900 dark:text-gray-100">
                    {t('lineCloudRemoteTools')}
                  </div>
                  <div className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                    {t('lineCloudRemoteToolsDescription')}
                  </div>
                </div>
              </label>
            </div>
          </div>
        )}

        {/* OAuth Configuration Section (Local mode) */}
        {(!isLine || connectionMode === 'local') && (
          <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-4">
            <h3 className="font-medium text-gray-900 dark:text-gray-100 mb-4">
              {'OAuth Configuration'}
            </h3>
          <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">
            {'Configure OAuth Client ID and Secret for this platform'}
          </p>

          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                {'Client ID'} <span className="text-red-500">*</span>
              </label>
              <input
                type="text"
                value={oauthConfig.client_id}
                onChange={(e) => setOauthConfig({ ...oauthConfig, client_id: e.target.value })}
                placeholder="Enter OAuth Client ID"
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                {'Client Secret'} <span className="text-red-500">*</span>
              </label>
              <input
                type="password"
                value={oauthConfig.client_secret}
                onChange={(e) => setOauthConfig({ ...oauthConfig, client_secret: e.target.value })}
                placeholder={connection?.config?.client_secret ? '•••••••• (configured)' : 'Enter OAuth Client Secret'}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
              />
              {connection?.config?.client_secret && !oauthConfig.client_secret && (
                <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                  {'Leave blank to keep existing secret'}
                </p>
              )}
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                {t('redirectURI') || 'Redirect URI'}
              </label>
              <input
                type="url"
                value={oauthConfig.redirect_uri}
                onChange={(e) => setOauthConfig({ ...oauthConfig, redirect_uri: e.target.value })}
                placeholder={`${API_URL}/api/v1/tools/oauth/${provider}/callback`}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
              />
              <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                {t('redirectURIDescription') || 'OAuth callback URL. Default will be used if not specified.'}
              </p>
            </div>

            <button
              onClick={handleSaveOAuthConfig}
              disabled={savingConfig || !oauthConfig.client_id || (!oauthConfig.client_secret && !connection?.config?.client_secret)}
              className="px-4 py-2 bg-gray-600 dark:bg-gray-500 text-white rounded-md hover:bg-gray-700 dark:hover:bg-gray-600 disabled:opacity-50 text-sm font-medium"
            >
              {savingConfig ? t('saving') : 'Save OAuth Configuration'}
            </button>
          </div>
        </div>
        )}

        {/* Cloud Remote Tools Configuration Section (Remote mode) */}
        {isLine && connectionMode === 'remote' && (
          <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-4">
            <h3 className="font-medium text-gray-900 dark:text-gray-100 mb-4">
              {t('lineCloudRemoteTools')}
            </h3>
            <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">
              {t('lineCloudRemoteToolsDescription')}
            </p>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  {t('cloudRemoteToolsUrl')} <span className="text-red-500">*</span>
                </label>
                <input
                  type="url"
                  value={remoteConfig.cluster_url}
                  onChange={(e) => setRemoteConfig({ ...remoteConfig, cluster_url: e.target.value })}
                  placeholder={t('cloudRemoteToolsUrlPlaceholder')}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-purple-500 dark:focus:ring-purple-400 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                />
                <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                  {t('cloudRemoteToolsUrlDescription')}
                </p>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  {t('channelId')} <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  value={remoteConfig.channel_id}
                  onChange={(e) => setRemoteConfig({ ...remoteConfig, channel_id: e.target.value })}
                  placeholder={t('channelIdPlaceholder')}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-purple-500 dark:focus:ring-purple-400 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                />
                <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                  {t('channelIdDescription')}
                </p>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  {t('cloudRemoteToolsApiToken')}
                </label>
                <input
                  type="password"
                  value={remoteConfig.api_token}
                  onChange={(e) => setRemoteConfig({ ...remoteConfig, api_token: e.target.value })}
                  placeholder={connection?.config && 'api_token' in connection.config ? '•••••••• (configured)' : t('cloudRemoteToolsApiTokenPlaceholder')}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-purple-500 dark:focus:ring-purple-400 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                />
                <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                  {t('cloudRemoteToolsApiTokenDescription')}
                </p>
              </div>

              <button
                onClick={handleSaveRemoteConfig}
                disabled={savingConfig || !remoteConfig.cluster_url || !remoteConfig.channel_id}
                className="px-4 py-2 bg-purple-600 dark:bg-purple-500 text-white rounded-md hover:bg-purple-700 dark:hover:bg-purple-600 disabled:opacity-50 text-sm font-medium"
              >
                {savingConfig ? t('saving') : 'Save Cloud Remote Tools Configuration'}
              </button>
            </div>
          </div>
        )}

        {/* Connection Status Section */}
        <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-4">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="font-medium text-gray-900 dark:text-gray-100 mb-1">
                {t('connectionStatus')}
              </h3>
              <div className="flex items-center gap-2">
                <span
                  className={`inline-flex items-center gap-1 text-sm ${
                    isConnected
                      ? 'text-green-600 dark:text-green-400'
                      : 'text-gray-500 dark:text-gray-400'
                  }`}
                >
                  <span
                    className={`w-2 h-2 rounded-full ${
                      isConnected ? 'bg-green-500' : 'bg-gray-400'
                    }`}
                  />
                  {isConnected ? t('socialMediaConnected') : t('socialMediaNotConnected')}
                </span>
              </div>
            </div>
            <div>
              {isConnected ? (
                <button
                  onClick={handleDisconnect}
                  className="px-4 py-2 text-sm font-medium text-red-600 dark:text-red-400 hover:text-red-700 dark:hover:text-red-300 border border-red-300 dark:border-red-700 rounded-md hover:bg-red-50 dark:hover:bg-red-900/20"
                >
                  {t('disconnectSocialMedia')}
                </button>
              ) : (
                <button
                  onClick={handleConnect}
                  disabled={connecting}
                  className="px-4 py-2 text-sm font-medium text-white bg-gray-600 dark:bg-gray-500 rounded-md hover:bg-gray-700 dark:hover:bg-gray-600 disabled:opacity-50"
                >
                  {connecting ? t('socialMediaConnecting') : t('connectSocialMedia')}
                </button>
              )}
            </div>
          </div>

          {isConnected && connection && (
            <div className="mt-4 pt-4 border-t border-gray-200 dark:border-gray-700">
              <div className="grid grid-cols-2 gap-4 text-sm mb-4">
                <div>
                  <span className="text-gray-500 dark:text-gray-400">{t('connectionName')}:</span>
                  <span className="ml-2 text-gray-900 dark:text-gray-100">{connection.name}</span>
                </div>
                {connection.last_validated_at && (
                  <div>
                    <span className="text-gray-500 dark:text-gray-400">{t('lastValidated')}:</span>
                    <span className="ml-2 text-gray-900 dark:text-gray-100">
                      {new Date(connection.last_validated_at).toLocaleString()}
                    </span>
                  </div>
                )}
                {connection.connection_type === 'remote' && (
                  <>
                    {connection.remote_cluster_url && (
                      <div>
                        <span className="text-gray-500 dark:text-gray-400">Remote Cluster:</span>
                        <span className="ml-2 text-gray-900 dark:text-gray-100">{connection.remote_cluster_url}</span>
                      </div>
                    )}
                    {connection.remote_connection_id && (
                      <div>
                        <span className="text-gray-500 dark:text-gray-400">Remote Connection ID:</span>
                        <span className="ml-2 text-gray-900 dark:text-gray-100">{connection.remote_connection_id}</span>
                      </div>
                    )}
                  </>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Discovered Tools Section */}
        {isConnected && connection && (
          <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-4">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-medium text-gray-900 dark:text-gray-100">
                {t('discoveredTools') || 'Discovered Tools'}
              </h3>
              {loadingTools && (
                <span className="text-sm text-gray-500 dark:text-gray-400">{t('loading')}</span>
              )}
            </div>
            {tools.length > 0 ? (
              <div className="space-y-2">
                {tools.map((tool) => (
                  <div
                    key={tool.tool_id}
                    className="flex items-center justify-between p-3 border border-gray-200 dark:border-gray-700 rounded bg-gray-50 dark:bg-gray-800/50"
                  >
                    <div className="flex-1">
                      <div className="font-medium text-gray-900 dark:text-gray-100">
                        {tool.display_name}
                      </div>
                      <div className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                        {tool.description || tool.category}
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <span
                        className={`px-2 py-1 text-xs rounded ${
                          tool.enabled
                            ? 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400'
                            : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400'
                        }`}
                      >
                        {tool.enabled ? t('enabled') : t('disabled')}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-gray-500 dark:text-gray-400 text-center py-4">
                {loadingTools ? t('loading') : t('noToolsDiscovered') || 'No tools discovered yet'}
              </p>
            )}
          </div>
        )}
      </div>
    </Card>
  );
}

