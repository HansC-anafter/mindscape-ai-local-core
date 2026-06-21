import { API_URL, PROFILE_ID, getOAuthCallbackUrl } from './constants';
import type {
  OAuthConfig,
  RegisteredTool,
  RemoteConfig,
  SettingsExtensionPanel,
  SocialMediaConnection,
} from './types';

export async function loadSocialProviderSettingsPanels(
  provider: string,
  workspaceId?: string,
): Promise<SettingsExtensionPanel[]> {
  const params = new URLSearchParams({ section: `social-media:${provider}` });
  if (workspaceId) {
    params.set('workspace_id', workspaceId);
  }
  const response = await fetch(`${API_URL}/api/v1/settings/extensions?${params.toString()}`);
  if (!response.ok) {
    return [];
  }
  const data = await response.json();
  return Array.isArray(data) ? data : [];
}

export async function loadSocialConnection(provider: string): Promise<SocialMediaConnection | null> {
  const response = await fetch(
    `${API_URL}/api/v1/tools/connections?profile_id=${PROFILE_ID}&tool_type=${provider}`,
  );
  if (!response.ok) {
    throw new Error('Failed to load connection');
  }
  const data: SocialMediaConnection[] = await response.json();
  return data.length > 0 ? data[0] : null;
}

export async function loadSocialConnectionTools(connectionId: string): Promise<RegisteredTool[]> {
  const response = await fetch(
    `${API_URL}/api/v1/tools/registry?site_id=${connectionId}&profile_id=${PROFILE_ID}`,
  );
  if (!response.ok) {
    if (response.status === 404) {
      return [];
    }
    throw new Error('Failed to load tools');
  }
  const data: RegisteredTool[] = await response.json();
  return data || [];
}

export async function saveOAuthConnection(
  provider: string,
  platformLabel: string,
  connection: SocialMediaConnection | null,
  oauthConfig: OAuthConfig,
): Promise<void> {
  const updateData = {
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
      },
    );
    if (!response.ok) {
      throw new Error('Failed to save OAuth configuration');
    }
    return;
  }

  const response = await fetch(
    `${API_URL}/api/v1/tools/connections?profile_id=${PROFILE_ID}`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        tool_type: provider,
        connection_type: 'local',
        name: `${platformLabel} Connection`,
        ...updateData,
      }),
    },
  );
  if (!response.ok) {
    throw new Error('Failed to create connection');
  }
}

export async function saveRemoteConnection(
  provider: string,
  platformLabel: string,
  connection: SocialMediaConnection | null,
  remoteConfig: RemoteConfig,
): Promise<void> {
  const connectionData: {
    tool_type: string;
    connection_type: 'remote';
    name: string;
    remote_cluster_url: string;
    remote_connection_id: string;
    config: { api_token?: string };
  } = {
    tool_type: provider,
    connection_type: 'remote',
    name: `${platformLabel} Connection (Cloud Remote Tools)`,
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
      },
    );
    if (!response.ok) {
      throw new Error('Failed to save Cloud Remote Tools configuration');
    }
    return;
  }

  const response = await fetch(
    `${API_URL}/api/v1/tools/connections?profile_id=${PROFILE_ID}`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(connectionData),
    },
  );
  if (!response.ok) {
    throw new Error('Failed to create connection');
  }
}

export async function getOAuthAuthorizationUrl(
  provider: string,
  connection: SocialMediaConnection,
): Promise<string> {
  const redirectUri = connection.config?.redirect_uri || getOAuthCallbackUrl(provider);
  const authorizeUrl = `${API_URL}/api/v1/tools/oauth/${provider}/authorize?redirect_uri=${encodeURIComponent(redirectUri)}&profile_id=${PROFILE_ID}&client_id=${encodeURIComponent(connection.config?.client_id || '')}&client_secret=${encodeURIComponent(connection.config?.client_secret || '')}`;
  const response = await fetch(authorizeUrl);

  if (!response.ok) {
    let errorMessage = 'Failed to get authorization URL';
    try {
      const errorData = await response.json();
      errorMessage = errorData.detail || errorData.message || errorMessage;
      console.error('[Line OAuth] Error response:', errorData);
    } catch {
      try {
        const errorText = await response.text();
        if (errorText) {
          errorMessage = errorText;
        }
        console.error('[Line OAuth] Error text:', errorText);
      } catch {
        errorMessage = response.statusText || `HTTP ${response.status}`;
        console.error(`[Line OAuth] HTTP ${response.status}: ${response.statusText}`);
      }
    }
    throw new Error(errorMessage);
  }

  const data = await response.json();
  if (!data.authorization_url) {
    console.error('[Line OAuth] No authorization_url in response:', data);
    throw new Error('No authorization URL received');
  }
  return data.authorization_url;
}

export async function deleteSocialConnection(connectionId: string): Promise<void> {
  const response = await fetch(
    `${API_URL}/api/v1/tools/connections/${connectionId}?profile_id=${PROFILE_ID}`,
    { method: 'DELETE' },
  );
  if (!response.ok) {
    throw new Error('Failed to disconnect');
  }
}
