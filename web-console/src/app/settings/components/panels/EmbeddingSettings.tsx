'use client';

import React, { useState, useEffect, useMemo } from 'react';
import { t } from '../../../../lib/i18n';
import { settingsApi } from '../../utils/settingsApi';
import { InlineAlert } from '../InlineAlert';
import { useEnabledModels } from '../../hooks/useEnabledModels';

interface LLMModelConfig {
  model_name: string;
  provider: string;
  model_type: 'chat' | 'embedding';
  api_key_setting_key?: string;
  metadata?: Record<string, any>;
}

interface EmbeddingSettingsResponse {
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

interface EmbeddingMigration {
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

export function EmbeddingSettings() {
  const [loading, setLoading] = useState(true);
  const [settings, setSettings] = useState<EmbeddingSettingsResponse | null>(null);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showMigrationPrompt, setShowMigrationPrompt] = useState(false);
  const [previousModel, setPreviousModel] = useState<LLMModelConfig | null>(null);
  const [migrating, setMigrating] = useState(false);
  const [migration, setMigration] = useState<EmbeddingMigration | null>(null);
  const [migrationProgress, setMigrationProgress] = useState<number>(0);

  const { enabledModels: enabledEmbeddingModels } = useEnabledModels('embedding');

  useEffect(() => {
    loadSettings();
  }, []);

  const loadSettings = async () => {
    try {
      setLoading(true);
      const data = await settingsApi.get<EmbeddingSettingsResponse>('/api/v1/system-settings/llm-models?include_embedding_status=true');
      setSettings(data);

      // Load migration info if available
      if (data.migration_info) {
        console.log('[EmbeddingSettings] Loaded migration_info from settings:', data.migration_info);
        // Use new_model if previous_model is not available
        const modelInfo = data.migration_info.previous_model || data.migration_info.new_model;
        const previousModelData = {
          model_name: modelInfo?.model_name || data.embedding_model?.model_name || '',
          provider: modelInfo?.provider || data.embedding_model?.provider || 'openai',
          model_type: 'embedding',
          metadata: data.migration_info
        } as LLMModelConfig;
        console.log('[EmbeddingSettings] Setting previousModel from loadSettings:', previousModelData);
        setPreviousModel(previousModelData);

        if (data.migration_info.needs_migration && !data.migration_info.has_active_migration) {
          setShowMigrationPrompt(true);
        } else {
          setShowMigrationPrompt(false);
        }
      } else {
        console.log('[EmbeddingSettings] No migration_info in loaded settings:', data);
        setPreviousModel(null);
        setShowMigrationPrompt(false);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load embedding settings');
    } finally {
      setLoading(false);
    }
  };

  const testConnection = async () => {
    try {
      setTesting(true);
      setTestResult(null);
      const result = await settingsApi.post<{
        success: boolean;
        message: string;
        model_name: string;
        provider: string;
        dimensions?: number;
      }>('/api/v1/system-settings/llm-models/test-embedding');

      if (result.success) {
        setTestResult(result.message);
      } else {
        setTestResult(result.message);
      }
    } catch (err) {
      setTestResult(`${t('testFailedWithError')}: ${err instanceof Error ? err.message : 'Unknown error'}`);
    } finally {
      setTesting(false);
    }
  };

  const updateEmbeddingModel = async (modelName: string, provider: string) => {
    try {
      setError(null);

      const response = await settingsApi.put<{
        model: LLMModelConfig;
        migration_info?: {
          needs_migration: boolean;
          previous_model: {
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
          has_active_migration?: boolean;
          migration_recommendation?: string;
          error?: string;
        };
      }>(`/api/v1/system-settings/llm-models/embedding?model_name=${modelName}&provider=${provider}`, {});

      await loadSettings();

      // Always save migration_info if available (for health status display)
      if (response.migration_info) {
        console.log('[EmbeddingSettings] Received migration_info:', response.migration_info);
        // Use new_model if previous_model is not available (e.g., model didn't change)
        const modelInfo = response.migration_info.previous_model || response.migration_info.new_model;
        const previousModelData = {
          model_name: modelInfo?.model_name || modelName,
          provider: modelInfo?.provider || provider,
          model_type: 'embedding',
          metadata: response.migration_info
        } as LLMModelConfig;
        console.log('[EmbeddingSettings] Setting previousModel:', previousModelData);
        setPreviousModel(previousModelData);

        // Show migration prompt only if migration is needed
        if (response.migration_info.needs_migration) {
          setShowMigrationPrompt(true);
        } else {
          setShowMigrationPrompt(false);
        }
      } else {
        console.log('[EmbeddingSettings] No migration_info in response:', response);
        setShowMigrationPrompt(false);
        setPreviousModel(null);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update embedding model');
    }
  };

  const createMigration = async () => {
    if (!previousModel || !settings?.embedding_model) return;

    try {
      setMigrating(true);
      setError(null);
      const result = await settingsApi.post<{
        success: boolean;
        migration: EmbeddingMigration;
        message: string;
      }>('/api/v1/system-settings/embedding-migrations', {
        source_model: previousModel.model_name,
        target_model: settings.embedding_model.model_name,
        source_provider: previousModel.provider,
        target_provider: settings.embedding_model.provider,
        strategy: 'replace',
        scope: 'all' // Migrate all embeddings
      });

      if (result.success && result.migration) {
        setMigration(result.migration);
        setShowMigrationPrompt(false);
        // Start the migration
        await startMigration(result.migration.id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create migration task');
    } finally {
      setMigrating(false);
    }
  };

  const startMigration = async (migrationId: string) => {
    try {
      await settingsApi.post(`/api/v1/system-settings/embedding-migrations/${migrationId}/start`, {});
      // Poll for progress
      pollMigrationProgress(migrationId);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start migration');
    }
  };

  const pollMigrationProgress = async (migrationId: string) => {
    const interval = setInterval(async () => {
      try {
        const result = await settingsApi.get<{
          success: boolean;
          migration: EmbeddingMigration;
        }>(`/api/v1/system-settings/embedding-migrations/${migrationId}`);

        if (result.success && result.migration) {
          setMigration(result.migration);
          const progress = result.migration.total_count > 0
            ? Math.round((result.migration.completed_count / result.migration.total_count) * 100)
            : 0;
          setMigrationProgress(progress);

          if (result.migration.status === 'completed' || result.migration.status === 'failed' || result.migration.status === 'cancelled') {
            clearInterval(interval);
            setMigrating(false);
          }
        }
      } catch (err) {
        console.error('Failed to poll migration progress:', err);
        clearInterval(interval);
      }
    }, 2000); // Poll every 2 seconds

    // Cleanup after 5 minutes
    setTimeout(() => clearInterval(interval), 5 * 60 * 1000);
  };

  const skipMigration = () => {
    setShowMigrationPrompt(false);
    setPreviousModel(null);
  };

  if (loading) {
    return <div className="text-center py-4 text-sm text-gray-500 dark:text-gray-400">{t('loading')}</div>;
  }

  if (!settings) {
    return <div className="text-sm text-red-600 dark:text-red-400">{error || t('failedToLoad')}</div>;
  }

  return (
    <div className="space-y-4">
      {error && <InlineAlert type="error" message={error} onDismiss={() => setError(null)} />}

      <div>
        <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-1">{t('embeddingModel')}</h3>
        <p className="text-xs text-gray-500 dark:text-gray-400 mb-4">
          {t('embeddingModelDescription')}
          {settings.embedding_model && (
            <span className="ml-2">
              {t('currentModel')}: <strong>{settings.embedding_model.model_name}</strong> ({settings.embedding_model.provider})
            </span>
          )}
        </p>
      </div>

      <div className="flex items-center gap-3 mb-4">
        <button
          onClick={testConnection}
          disabled={testing}
          className="px-3 py-1.5 text-sm bg-accent dark:bg-blue-700 text-white rounded-md hover:bg-accent/90 dark:hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {testing ? t('testing') : t('testConnection')}
        </button>
      </div>

      {testResult && (
        <div className={`mb-3 p-2 rounded text-sm ${testResult.includes('success') || testResult.includes('Success') ? 'bg-green-50 dark:bg-green-900/20 text-green-800 dark:text-green-300' : 'bg-red-50 dark:bg-red-900/20 text-red-800 dark:text-red-300'}`}>
          {testResult}
        </div>
      )}

      {/* Embedding Health Status */}
      {previousModel && previousModel.metadata && !showMigrationPrompt && (
        <div className="mb-4 p-4 border border-green-300 dark:border-green-700 rounded-lg bg-green-50 dark:bg-green-900/20">
          <div className="flex items-start gap-3">
            <div className="flex-shrink-0 text-green-600 dark:text-green-400 text-xl">✓</div>
            <div className="flex-1">
              <h4 className="text-sm font-semibold text-green-900 dark:text-green-200 mb-2">
                Embedding Status
              </h4>

              {/* Current Model Info */}
              {previousModel.metadata.new_model && (
                <div className="mb-3 p-2 bg-white dark:bg-gray-800 rounded border border-green-200 dark:border-green-800">
                  <div className="text-xs font-medium text-green-900 dark:text-green-200 mb-1">
                    Current Model:
                  </div>
                  <div className="text-xs text-green-800 dark:text-green-300 space-y-1">
                    <div>
                      <strong>{previousModel.metadata.new_model.model_name}</strong> ({previousModel.metadata.new_model.provider})
                    </div>
                    {previousModel.metadata.new_model.existing_embeddings > 0 && (
                      <div>
                        Total Embeddings: <strong>{previousModel.metadata.new_model.existing_embeddings.toLocaleString()}</strong>
                      </div>
                    )}
                    {previousModel.metadata.new_model.existing_embeddings === 0 && (
                      <div className="space-y-2">
                        <div className="text-amber-600 dark:text-amber-400">
                          {t('noEmbeddingsFound') || 'No embeddings found yet. Embeddings will be automatically generated when you:'}
                        </div>
                        <ul className="text-xs text-amber-700 dark:text-amber-300 list-disc list-inside ml-2 space-y-1">
                          <li>{t('embeddingGenerationMethod1') || 'Upload documents to workspaces'}</li>
                          <li>{t('embeddingGenerationMethod2') || 'Use AI features that require document search'}</li>
                          <li>{t('embeddingGenerationMethod3') || 'Process files through playbooks'}</li>
                        </ul>
                        {/* Check if there are embeddings from previous model or other historical models that need migration */}
                        {(() => {
                          const previousModelEmbeddings = previousModel.metadata.previous_model?.total_embeddings || 0;
                          const historicalModelsWithEmbeddings = (previousModel.metadata.historical_models || []).filter(
                            (m: any) => m.model_name !== previousModel.metadata.new_model.model_name && m.count > 0
                          );
                          const totalHistoricalEmbeddings = historicalModelsWithEmbeddings.reduce((sum: number, m: any) => sum + m.count, 0);

                          if (previousModelEmbeddings > 0 || totalHistoricalEmbeddings > 0) {
                            const sourceModel = previousModelEmbeddings > 0
                              ? previousModel.metadata.previous_model
                              : historicalModelsWithEmbeddings[0];
                            const totalCount = previousModelEmbeddings > 0
                              ? previousModelEmbeddings
                              : totalHistoricalEmbeddings;

                            return (
                              <div className="mt-2 pt-2 border-t border-amber-300 dark:border-amber-700">
                                <div className="text-xs text-amber-700 dark:text-amber-300 mb-2">
                                  {t('foundPreviousEmbeddings') || 'Found'} {totalCount.toLocaleString()} {t('embeddingsFromPreviousModel') || 'embeddings from'} {sourceModel?.model_name || 'previous model'}:
                                </div>
                                <button
                                  onClick={() => {
                                    setShowMigrationPrompt(true);
                                  }}
                                  className="px-3 py-1.5 text-xs bg-amber-600 dark:bg-amber-700 text-white rounded-md hover:bg-amber-700 dark:hover:bg-amber-600 transition-colors"
                                >
                                  {t('reembedAllDocuments') || 'Re-embed All Documents'}
                                </button>
                              </div>
                            );
                          } else {
                            // Even if no historical embeddings, show option to manually trigger embedding for historical data
                            return (
                              <div className="mt-2 pt-2 border-t border-amber-300 dark:border-amber-700">
                                <div className="text-xs text-amber-700 dark:text-amber-300 mb-2">
                                  {t('hasHistoricalDataButNoEmbeddings') || 'If you have historical documents, files, or conversations that need embedding, you can manually trigger embedding generation:'}
                                </div>
                                <button
                                  onClick={() => {
                                    // Show migration prompt even without previous embeddings
                                    // This allows manual re-embedding of historical data
                                    setShowMigrationPrompt(true);
                                  }}
                                  className="px-3 py-1.5 text-xs bg-amber-600 dark:bg-amber-700 text-white rounded-md hover:bg-amber-700 dark:hover:bg-amber-600 transition-colors"
                                >
                                  {t('generateEmbeddingsForHistoricalData') || 'Generate Embeddings for Historical Data'}
                                </button>
                              </div>
                            );
                          }
                        })()}
                      </div>
                    )}
                    {previousModel.metadata.new_model.first_used && (
                      <div>
                        First Used: {new Date(previousModel.metadata.new_model.first_used).toLocaleString()}
                      </div>
                    )}
                    {previousModel.metadata.new_model.last_used && (
                      <div>
                        Last Used: {new Date(previousModel.metadata.new_model.last_used).toLocaleString()}
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* Historical Models Summary */}
              {previousModel.metadata.historical_models && previousModel.metadata.historical_models.length > 0 && (
                <details className="mb-3">
                  <summary className="text-xs font-medium text-green-900 dark:text-green-200 cursor-pointer hover:text-green-700 dark:hover:text-green-300">
                    View All Historical Models ({previousModel.metadata.historical_models.length})
                  </summary>
                  <div className="mt-2 p-2 bg-white dark:bg-gray-800 rounded border border-green-200 dark:border-green-800 text-xs space-y-1">
                    {previousModel.metadata.historical_models.map((model: any, idx: number) => (
                      <div key={idx} className="flex justify-between items-center">
                        <span>
                          <strong>{model.model_name}</strong> ({model.provider})
                        </span>
                        <span className="text-gray-600 dark:text-gray-400">
                          {model.count.toLocaleString()} embeddings
                        </span>
                      </div>
                    ))}
                  </div>
                </details>
              )}

              {/* Status Message */}
              {previousModel.metadata.migration_recommendation && (
                <div className="mb-3 p-2 bg-accent-10 dark:bg-blue-900/20 rounded border border-accent/30 dark:border-blue-800">
                  <div className="text-xs font-medium text-accent dark:text-blue-200 mb-1">
                    Status:
                  </div>
                  <div className="text-xs text-accent dark:text-blue-300">
                    {previousModel.metadata.migration_recommendation}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Migration Prompt */}
      {showMigrationPrompt && previousModel && settings?.embedding_model && previousModel.metadata && (
        <div className="mb-4 p-4 border border-amber-300 dark:border-amber-700 rounded-lg bg-amber-50 dark:bg-amber-900/20">
          <div className="flex items-start gap-3">
            <div className="flex-shrink-0 text-amber-600 dark:text-amber-400 text-xl">!</div>
            <div className="flex-1">
              <h4 className="text-sm font-semibold text-amber-900 dark:text-amber-200 mb-2">
                Model Switch Detected - Re-embedding Recommended
              </h4>

              {/* Previous Model Info */}
              {previousModel.metadata.previous_model && (
                <div className="mb-3 p-2 bg-white dark:bg-gray-800 rounded border border-amber-200 dark:border-amber-800">
                  <div className="text-xs font-medium text-amber-900 dark:text-amber-200 mb-1">
                    Previous Model:
                  </div>
                  <div className="text-xs text-amber-800 dark:text-amber-300 space-y-1">
                    <div>
                      <strong>{previousModel.metadata.previous_model.model_name}</strong> ({previousModel.metadata.previous_model.provider})
                    </div>
                    {previousModel.metadata.previous_model.total_embeddings !== null && (
                      <div>
                        Total Embeddings: <strong>{previousModel.metadata.previous_model.total_embeddings.toLocaleString()}</strong>
                      </div>
                    )}
                    {previousModel.metadata.previous_model.first_used && (
                      <div>
                        First Used: {new Date(previousModel.metadata.previous_model.first_used).toLocaleString()}
                      </div>
                    )}
                    {previousModel.metadata.previous_model.last_used && (
                      <div>
                        Last Used: {new Date(previousModel.metadata.previous_model.last_used).toLocaleString()}
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* New Model Info */}
              {previousModel.metadata.new_model && (
                <div className="mb-3 p-2 bg-surface-accent dark:bg-gray-800 rounded border border-accent/30 dark:border-blue-800">
                  <div className="text-xs font-medium text-accent dark:text-blue-200 mb-1">
                    New Model:
                  </div>
                  <div className="text-xs text-accent dark:text-blue-300 space-y-1">
                    <div>
                      <strong>{previousModel.metadata.new_model.model_name}</strong> ({previousModel.metadata.new_model.provider})
                    </div>
                    {previousModel.metadata.new_model.existing_embeddings > 0 && (
                      <div>
                        Existing Embeddings: <strong>{previousModel.metadata.new_model.existing_embeddings.toLocaleString()}</strong>
                      </div>
                    )}
                    {previousModel.metadata.new_model.existing_embeddings === 0 && (
                      <div className="text-amber-600 dark:text-amber-400">
                        New model has no embeddings yet
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* Missing Periods */}
              {previousModel.metadata.missing_periods && previousModel.metadata.missing_periods.length > 0 && (
                <div className="mb-3 p-2 bg-red-50 dark:bg-red-900/20 rounded border border-red-200 dark:border-red-800">
                  <div className="text-xs font-medium text-red-900 dark:text-red-200 mb-1">
                    Missing Time Periods:
                  </div>
                  <div className="text-xs text-red-800 dark:text-red-300 space-y-1">
                    {previousModel.metadata.missing_periods.map((period: any, idx: number) => (
                      <div key={idx}>
                        {new Date(period.from).toLocaleDateString()} to {new Date(period.to).toLocaleDateString()}
                        {' '}({period.count.toLocaleString()} embeddings)
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Historical Models */}
              {previousModel.metadata.historical_models && previousModel.metadata.historical_models.length > 0 && (
                <details className="mb-3">
                  <summary className="text-xs font-medium text-amber-900 dark:text-amber-200 cursor-pointer hover:text-amber-700 dark:hover:text-amber-300">
                    View All Historical Models ({previousModel.metadata.historical_models.length})
                  </summary>
                  <div className="mt-2 p-2 bg-white dark:bg-gray-800 rounded border border-amber-200 dark:border-amber-800 text-xs space-y-1">
                    {previousModel.metadata.historical_models.map((model: any, idx: number) => (
                      <div key={idx} className="flex justify-between items-center">
                        <span>
                          <strong>{model.model_name}</strong> ({model.provider})
                        </span>
                        <span className="text-gray-600 dark:text-gray-400">
                          {model.count.toLocaleString()} embeddings
                        </span>
                      </div>
                    ))}
                  </div>
                </details>
              )}

              {/* Migration Recommendation */}
              {previousModel.metadata.migration_recommendation && (
                <div className="mb-3 p-2 bg-accent-10 dark:bg-blue-900/20 rounded border border-accent/30 dark:border-blue-800">
                  <div className="text-xs font-medium text-accent dark:text-blue-200 mb-1">
                    Recommendation:
                  </div>
                  <div className="text-xs text-accent dark:text-blue-300">
                    {previousModel.metadata.migration_recommendation}
                  </div>
                </div>
              )}

              {/* Active Migration Warning */}
              {previousModel.metadata.has_active_migration && (
                <div className="mb-3 p-2 bg-yellow-50 dark:bg-yellow-900/20 rounded border border-yellow-200 dark:border-yellow-800">
                  <div className="text-xs text-yellow-800 dark:text-yellow-300">
                    Active migration task in progress. Please wait for completion before starting a new migration.
                  </div>
                </div>
              )}

              <p className="text-sm text-amber-800 dark:text-amber-300 mb-3">
                Re-embedding existing documents is recommended to ensure accurate vector search.
              </p>

              <div className="flex items-center gap-2">
                <button
                  onClick={createMigration}
                  disabled={migrating}
                  className="px-3 py-1.5 text-sm bg-amber-600 dark:bg-amber-700 text-white rounded-md hover:bg-amber-700 dark:hover:bg-amber-600 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {migrating ? 'Preparing...' : 'Start Re-embedding'}
                </button>
                <button
                  onClick={skipMigration}
                  disabled={migrating}
                  className="px-3 py-1.5 text-sm bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-md hover:bg-gray-300 dark:hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  Later
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Migration Progress */}
      {migration && (
        <div className="mb-4 p-4 border border-accent/30 dark:border-blue-700 rounded-lg bg-accent-10 dark:bg-blue-900/20">
          <div className="flex items-start gap-3">
            <div className="flex-shrink-0 text-accent dark:text-blue-400 text-xl">
              {migration.status === 'running' ? '...' : migration.status === 'completed' ? '✓' : migration.status === 'failed' ? '✗' : '○'}
            </div>
            <div className="flex-1">
              <h4 className="text-sm font-semibold text-accent dark:text-blue-200 mb-2">
                Re-embedding in Progress
              </h4>
              {migration.status === 'running' && (
                <>
                  <div className="mb-2">
                    <div className="flex justify-between text-xs text-accent dark:text-blue-300 mb-1">
                      <span>Progress: {migration.completed_count} / {migration.total_count}</span>
                      <span>{migrationProgress}%</span>
                    </div>
                    <div className="w-full bg-accent-10 dark:bg-blue-800 rounded-full h-2">
                      <div
                        className="bg-accent dark:bg-blue-500 h-2 rounded-full transition-all duration-300"
                        style={{ width: `${migrationProgress}%` }}
                      />
                    </div>
                  </div>
                  <p className="text-xs text-accent dark:text-blue-400">
                    Re-embedding document vectors. Please do not close this page...
                  </p>
                </>
              )}
              {migration.status === 'completed' && (
                <p className="text-sm text-accent dark:text-blue-300">
                  Re-embedding completed! Processed {migration.total_count} embeddings.
                </p>
              )}
              {migration.status === 'failed' && (
                <p className="text-sm text-red-800 dark:text-red-300">
                  Re-embedding failed. Please check backend logs or retry.
                </p>
              )}
            </div>
          </div>
        </div>
      )}

      <div>
        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
          {t('selectEmbeddingModel') || '選擇 Embedding 模型'}
        </label>
        {enabledEmbeddingModels.length === 0 ? (
          <div className="p-3 border border-gray-300 dark:border-gray-600 rounded-md bg-gray-50 dark:bg-gray-800 text-sm text-gray-500 dark:text-gray-400">
            {t('noEnabledModels') || '沒有已啟用的 Embedding 模型。請在「模型與配額」中啟用至少一個模型。'}
          </div>
        ) : (
          <select
            value={settings.embedding_model?.model_name || ''}
            onChange={(e) => {
              const selected = enabledEmbeddingModels.find(m => m.model_name === e.target.value);
              if (selected) {
                updateEmbeddingModel(selected.model_name, selected.provider);
              }
            }}
            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
          >
            {enabledEmbeddingModels.map((model) => (
              <option key={model.model_name} value={model.model_name}>
                {model.display_name || model.model_name} - {model.description}
              </option>
            ))}
          </select>
        )}
      </div>
    </div>
  );
}

