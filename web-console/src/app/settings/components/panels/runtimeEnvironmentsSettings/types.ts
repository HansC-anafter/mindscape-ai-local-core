export interface RuntimeEnvironment {
  id: string;
  name: string;
  description: string;
  icon: string;
  status: 'active' | 'inactive' | 'configured' | 'not_configured';
  isDefault?: boolean;
  is_default?: boolean;
  config_url?: string;
  auth_type?: string;
  auth_status?: 'disconnected' | 'pending' | 'connected' | 'error';
  auth_identity?: string | null;
  metadata?: Record<string, any>;
  supportsDispatch?: boolean;
  supportsCell?: boolean;
  recommendedForDispatch?: boolean;
}

export interface SettingsPanel {
  capabilityCode: string;
  componentCode: string;
  section?: 'runtime-environments' | 'workflow-engines';
  title: string;
  description?: string;
  displayMode?: string;
  requiresWorkspaceId?: boolean;
  showWhen?: {
    runtimeCodes?: string[];
  };
  propsSchema?: Record<string, any>;
  importPath: string;
  export: string;
  path?: string;
  assetUrl?: string;
  integrity?: string;
  runtime?: string;
  legacyContext?: boolean;
  bytes?: number;
  assetPath?: string;
}

export type RuntimeSettingsExtensionProps = Record<string, any> & {
  apiUrl?: string;
  runtimeId?: string;
  runtime?: RuntimeEnvironment;
  workspaceId?: string;
};

export interface RuntimeSettingsFormCallbacks {
  onSave: () => void;
  onCancel: () => void;
}

export interface SiteHubSettingsFormProps extends RuntimeSettingsFormCallbacks {
  runtime: RuntimeEnvironment;
}
