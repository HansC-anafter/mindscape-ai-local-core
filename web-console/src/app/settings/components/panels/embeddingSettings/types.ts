export interface LLMModelConfig {
  model_name: string;
  provider: string;
  model_type: 'chat' | 'embedding';
  api_key_setting_key?: string;
  metadata?: Record<string, any>;
}

export interface EmbeddingSettingsResponse {
  embedding_model?: LLMModelConfig;
  available_embedding_models: Array<{
    model_name: string;
    provider: string;
    description: string;
    is_latest?: boolean;
    is_recommended?: boolean;
    dimensions?: number;
  }>;
  migration_info?: {
    needs_migration: boolean;
    has_active_migration?: boolean;
    previous_model?: {
      model_name: string;
      provider: string;
      total_embeddings: number | null;
      first_used?: string;
      last_used?: string;
      last_updated?: string;
    };
    new_model: {
      model_name: string;
      provider: string;
      existing_embeddings: number;
      first_used?: string;
      last_used?: string;
    };
    historical_models: Array<{
      model_name: string;
      provider: string;
      count: number;
      first_used?: string;
      last_used?: string;
      last_updated?: string;
    }>;
    missing_periods: Array<{
      from: string;
      to: string;
      model: string;
      count: number;
    }>;
    migration_recommendation?: string | null;
    error?: string;
  };
}

export interface EmbeddingMigration {
  id: string;
  source_model: string;
  target_model: string;
  total_count: number;
  completed_count: number;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
  created_at: string;
  started_at?: string;
  completed_at?: string;
}
