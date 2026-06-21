export interface CloudExtensionSettingsProps {
  activeSection?: string;
}

export type ProviderType = 'official' | 'generic_http';

export type TestStatus = 'idle' | 'testing' | 'success' | 'error';

export type AuthType = 'bearer' | 'api_key' | string;

export interface ProviderAuthConfig {
  auth_type: AuthType;
  token: string;
  api_key: string;
}

export interface ProviderFormConfig {
  api_url: string;
  license_key: string;
  name: string;
  auth: ProviderAuthConfig;
}

export interface CloudProviderFormData {
  provider_id: string;
  provider_type: ProviderType;
  enabled: boolean;
  config: ProviderFormConfig;
}

export interface Provider {
  provider_id: string;
  provider_type: string;
  enabled: boolean;
  configured: boolean;
  name: string;
  description: string;
  config: Record<string, any>;
}

export interface Pack {
  pack_ref: string;
  code: string;
  display_name: string;
  version: string;
  description: string;
  checksum?: string;
  size?: number;
  bundle: string;
  installed?: boolean;
}

export interface InstallDefaultPackJob {
  pack_code?: string;
  code?: string;
  pack_ref?: string;
  install_id?: string;
  state?: string;
  status_url?: string;
}

export interface InstallDefaultPacksResult {
  success?: boolean;
  accepted?: boolean;
  bundle?: string;
  provider_id?: string;
  jobs?: InstallDefaultPackJob[];
  skipped?: Array<Record<string, any>>;
  installed?: Array<Record<string, any>>;
  message?: string;
  detail?: string;
}
