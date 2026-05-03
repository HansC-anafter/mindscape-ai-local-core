'use client';

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

export interface ModelConfigCardData {
  model: ModelItem;
  api_key_configured: boolean;
  base_url?: string;
  quota_info?: {
    used: number;
    limit: number;
    reset_date?: string;
  };
}

export interface HuggingFaceModelResult {
  model_id: string;
  pipeline_tag: string;
  model_type: string;
  downloads: number;
  likes: number;
}

export type ModelTypeFilter = 'chat' | 'embedding' | 'multimodal' | 'tool-calling';
export type SubTab = 'models' | 'dynamic';
export type DeploymentScope = 'local' | 'cloud';
export type CatalogCategory = 'runtime-cli' | 'local-deployed' | 'api';

export const CHAT_PROFILES = [
  { key: 'fast', label: 'Fast', description: 'Facilitator / quick responses' },
  { key: 'standard', label: 'Standard', description: 'General chat / default path' },
  { key: 'precise', label: 'Precise', description: 'Planner / critic / deep reasoning' },
  { key: 'safe_write', label: 'Safe Write', description: 'Program synthesizer' },
] as const;

export const MULTIMODAL_PROFILES = [
  { key: 'vision', label: 'Vision', description: 'Multimodal image analysis' },
] as const;
