export interface BackendConfig {
  profile_id: string;
  current_mode: string;
  remote_crs_url?: string;
  remote_crs_configured: boolean;
  openai_api_key_configured: boolean;
  anthropic_api_key_configured: boolean;
  available_backends: Record<string, BackendInfo>;
}

export interface BackendInfo {
  name: string;
  available: boolean;
}

export interface ToolConnection {
  id: string;
  name: string;
  tool_type: string;
  enabled: boolean;
  wp_url?: string;
  wp_username?: string;
  last_discovery?: string;
  discovery_method?: string;
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

export interface ToolInfo {
  name: string;
  official_url?: string;
  download_url?: string;
  description?: string;
  installation_type?: string;
  api_docs?: string;
  local_setup_guide?: string;
}

export interface CapabilityPack {
  id: string;
  name: string;
  description: string;
  icon?: string;
  ai_members: string[];
  capabilities: string[];
  playbooks: string[];
  required_tools: string[];
  required_tools_info?: Record<string, ToolInfo>;
  installed: boolean;
  enabled?: boolean;
  enabled_by_default?: boolean;
  version?: string;
  installed_at?: string;
  routes?: string[];
  tools?: string[];
}

export interface Profile {
  id?: string;
  preferences?: ProfilePreferences;
}

export interface ProfilePreferences {
  enable_habit_suggestions?: boolean;
  review_preferences?: ReviewPreferences;
}

export interface ReviewPreferences {
  cadence: 'manual' | 'weekly' | 'monthly';
  day_of_week?: number;
  day_of_month?: number;
  time_of_day?: string;
  min_entries?: number;
  min_insight_events?: number;
}

export interface VectorDBConfig {
  mode: 'local' | 'custom';
  enabled: boolean;
  host?: string;
  port?: number;
  database?: string;
  schema_name?: string;
  username?: string;
  password?: string;
  ssl_mode?: string;
  access_mode?: 'read_write' | 'read_only' | 'disabled';
  data_scope?: 'mindscape_only' | 'with_documents' | 'all';
}

export interface ToolStatus {
  status: 'connected' | 'not_configured' | 'inactive' | 'local' | 'unavailable' | 'registered_but_not_connected';
  label: string;
  icon: string;
}

export interface ToolStatusInfo {
  status: 'unavailable' | 'registered_but_not_connected' | 'connected';
  info?: ToolInfo;
}

export interface PlaybookReadinessStatus {
  readiness_status: 'ready' | 'needs_setup' | 'unsupported';
  tool_statuses: Record<string, string>;
  missing_required_tools: string[];
  required_tools: string[];
  optional_tools: string[];
}

export type SettingsTab = 'basic' | 'mindscape' | 'social_media' | 'tools' | 'packs' | 'localization' | 'service_status';
