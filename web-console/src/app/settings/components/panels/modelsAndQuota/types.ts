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
  { key: 'fast', label: '快速 (Fast)', description: 'Facilitator / 快速回應' },
  { key: 'standard', label: '標準 (Standard)', description: '一般對話 / 預設路徑' },
  { key: 'precise', label: '精確 (Precise)', description: 'Planner / Critic / 深度推理' },
  { key: 'safe_write', label: '安全寫入 (Safe)', description: 'Program Synthesizer' },
] as const;

export const MULTIMODAL_PROFILES = [
  { key: 'vision', label: '視覺 (Vision)', description: '多模態影像分析' },
] as const;
