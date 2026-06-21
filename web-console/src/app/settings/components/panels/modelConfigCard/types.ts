'use client';

import type { ChangeEvent } from 'react';

export interface ModelItem {
  id: string | number;
  model_name: string;
  provider: string;
  model_type: 'chat' | 'embedding' | 'multimodal';
  display_name: string;
  description: string;
  enabled: boolean;
  icon?: string;
  is_latest?: boolean;
  is_recommended?: boolean;
  dimensions?: number;
  context_window?: number;
  metadata?: Record<string, any>;
}

export interface ProviderConfig {
  api_key_configured: boolean;
  api_key?: string;
  base_url?: string;
  project_id?: string;
  location?: string;
}

export interface ModelConfigCardData {
  model: ModelItem;
  api_key_configured: boolean;
  base_url?: string;
  project_id?: string;
  location?: string;
  provider_config?: ProviderConfig;
  quota_info?: {
    used: number;
    limit: number;
    reset_date?: string;
  };
}

export interface PullState {
  taskId: string;
  progress: number;
  status: string;
  message: string;
  totalBytes: number;
  downloadedBytes: number;
}

export interface ModelConfigCardProps {
  card: ModelConfigCardData;
  onConfigSaved?: () => void;
  pullState?: PullState | null;
  onPullModel?: (model: ModelItem) => void;
  onCancelPull?: (taskId: string) => void;
  onRemoveModel?: (modelId: string | number) => void;
}

export type TestResult = {
  success: boolean;
  message: string;
};

export interface ProviderConfigurationSectionProps {
  model: ModelItem;
  providerConfig?: ProviderConfig;
  apiKey: string;
  baseUrl: string;
  projectId: string;
  vertexLocation: string;
  jsonFileName: string;
  saving: boolean;
  onApiKeyChange: (value: string) => void;
  onBaseUrlChange: (value: string) => void;
  onProjectIdChange: (value: string) => void;
  onVertexLocationChange: (value: string) => void;
  onJsonFileChange: (event: ChangeEvent<HTMLInputElement>) => void;
  onSaveProviderConfig: () => void;
}

export interface ModelHeaderProps {
  model: ModelItem;
  pullStatus: string;
  onRemoveModel?: () => void;
}

export interface ModelOverrideSectionProps {
  model: ModelItem;
  showModelOverride: boolean;
  saving: boolean;
  modelApiKey: string;
  modelBaseUrl: string;
  modelProjectId: string;
  modelLocation: string;
  runtimeEngine: string;
  temperature: number;
  maxOutputTokenSliderMax: number;
  effectiveMaxOutputTokens: number;
  defaultMaxTokens: number;
  localRuntimeMaxTokensCap: number | null;
  onToggleShowModelOverride: () => void;
  onSaveModelOverride: () => void;
  onModelApiKeyChange: (value: string) => void;
  onModelBaseUrlChange: (value: string) => void;
  onModelProjectIdChange: (value: string) => void;
  onModelLocationChange: (value: string) => void;
  onRuntimeEngineChange: (value: string) => void;
  onTemperatureChange: (value: number) => void;
  onMaxOutputTokensChange: (value: number) => void;
}

export interface ModelActionsSectionProps {
  model: ModelItem;
  testing: boolean;
  pulling: boolean;
  pullProgress: number;
  pullStatus: string;
  pullMessage: string;
  pullTotalBytes: number;
  pullDownloadedBytes: number;
  pullState?: PullState | null;
  testResult: TestResult | null;
  onTestConnection: () => void;
  onPullModel: () => void;
  onCancelPull?: (taskId: string) => void;
}

export interface QuotaUsageSectionProps {
  quotaInfo?: ModelConfigCardData['quota_info'];
}

export interface ModelConfigCardViewProps
  extends ProviderConfigurationSectionProps,
    ModelHeaderProps,
    ModelOverrideSectionProps,
    ModelActionsSectionProps,
    QuotaUsageSectionProps {}
