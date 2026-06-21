import type React from 'react';

export interface SocialMediaConnection {
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
    api_token?: string;
  };
}

export interface RegisteredTool {
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

export interface SettingsExtensionPanel {
  capability_code: string;
  component_code: string;
  title: string;
  description?: string;
  requires_workspace_id?: boolean;
  props_schema?: Record<string, unknown>;
  import_path: string;
  export: string;
}

export interface SocialMediaPlatform {
  label: string;
  Icon: React.ComponentType<{ className?: string }>;
  color: string;
}

export interface OAuthConfig {
  client_id: string;
  client_secret: string;
  redirect_uri: string;
}

export interface RemoteConfig {
  cluster_url: string;
  channel_id: string;
  api_token: string;
}

export interface SocialMediaProviderSettingsProps {
  provider: string;
  workspaceId?: string;
  onBack: () => void;
}
