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

// ---------------------------------------------------------------------------
// OllamaToolEmbeddingSection — manages the ollama_embed_model system setting
// distinct from the knowledge-base embedding model above.
// ---------------------------------------------------------------------------
export function OllamaToolEmbeddingSection() {
  const [currentModel, setCurrentModel] = useState<string>('');
  const [availableModels, setAvailableModels] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ ok: boolean; message: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadState();
  }, []);

  const loadState = async () => {
    setLoading(true);
    try {
      // Load saved setting (key: ollama_embed_model)
      const setting = await settingsApi
        .get<{ value?: string }>('/api/v1/system-settings/ollama_embed_model')
        .catch(() => ({ value: '' }));
      setCurrentModel((setting as any)?.value ?? '');

      // Probe Ollama tag list via backend proxy if available, otherwise use known models
      const ollamaData = await settingsApi
        .get<{ models?: Array<{ name?: string }> }>('/api/v1/tools/rag-models')
        .catch(() => null);
      if (ollamaData && Array.isArray((ollamaData as any).models)) {
        setAvailableModels((ollamaData as any).models.map((m: any) => m.name ?? '').filter(Boolean));
      } else {
        // Fallback to known embed models
        setAvailableModels(['bge-m3', 'nomic-embed-text', 'mxbai-embed-large']);
      }
    } catch (e) {
      setError('Failed to load Ollama embed model settings');
    } finally {
      setLoading(false);
    }
  };

  const save = async (value: string) => {
    setSaving(true);
    setError(null);
    setTestResult(null);
    try {
      await settingsApi.put('/api/v1/system-settings/ollama_embed_model', {
        value,
        type: 'string',
      });
      setCurrentModel(value);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Save failed');
    } finally {
      setSaving(false);
    }
  };

  const testSearch = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const res = await settingsApi.post<{ status: string; match_count: number; model?: string }>(
        '/api/v1/tools/rag-search/',
        { query: 'test connection ping', top_k: 1, min_score: 0 }
      );
      const model = (res as any).model ?? '(auto)';
      const ok = (res as any).status === 'hit' || typeof (res as any).match_count === 'number';
      setTestResult({
        ok,
        message: ok
          ? `✓ Tool RAG 搜尋正常 · 模型: ${model} · ${(res as any).match_count} 筆結果`
          : `搜尋返回異常 status=${(res as any).status}`,
      });
    } catch (e) {
      setTestResult({ ok: false, message: e instanceof Error ? e.message : 'Test failed' });
    } finally {
      setTesting(false);
    }
  };

  return (
    <div className="mt-8 pt-6 border-t border-gray-200 dark:border-gray-700">
      <div className="mb-3">
        <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-1">
          工具 RAG Embedding 模型
        </h3>
        <p className="text-xs text-gray-500 dark:text-gray-400">
          用於工具能力索引（Tool RAG）的本地 Ollama embed 模型，與知識庫 embedding 獨立設定。
          留空則啟動時自動選擇（優先 <code className="bg-gray-100 dark:bg-gray-700 px-1 rounded">bge-m3</code>）。
        </p>
      </div>

      {error && <InlineAlert type="error" message={error} onDismiss={() => setError(null)} />}

      {loading ? (
        <div className="text-xs text-gray-400 py-2">載入中...</div>
      ) : (
        <div className="space-y-3">
          <div className="flex items-center gap-3">
            <select
              value={currentModel}
              onChange={(e) => save(e.target.value)}
              disabled={saving}
              className="flex-1 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md text-sm
                         focus:outline-none focus:ring-2 focus:ring-accent/50 dark:focus:ring-gray-500
                         bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 disabled:opacity-50"
            >
              <option value="">自動選擇（推薦）</option>
              {availableModels.map((m) => (
                <option key={m} value={m}>{m}</option>
              ))}
            </select>
            {saving && <span className="text-xs text-gray-400">儲存中...</span>}
          </div>

          {currentModel ? (
            <div className="text-xs text-green-700 dark:text-green-400 bg-green-50 dark:bg-green-900/20 px-2 py-1 rounded border border-green-200 dark:border-green-800">
              已固定模型：<strong>{currentModel}</strong>
            </div>
          ) : (
            <div className="text-xs text-gray-500 dark:text-gray-400 bg-gray-50 dark:bg-gray-800 px-2 py-1 rounded border border-gray-200 dark:border-gray-700">
              自動選擇模式 — 啟動時從 Ollama 選 bge-m3 &gt; nomic-embed-text
            </div>
          )}

          <div>
            <button
              onClick={testSearch}
              disabled={testing}
              className="px-3 py-1.5 text-sm bg-accent dark:bg-blue-700 text-white rounded-md
                         hover:bg-accent/90 dark:hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed
                         transition-colors"
            >
              {testing ? '搜尋測試中...' : '測試 Tool RAG 搜尋'}
            </button>
          </div>

          {testResult && (
            <div
              className={`p-2 rounded text-xs border ${testResult.ok
                ? 'bg-green-50 dark:bg-green-900/20 text-green-800 dark:text-green-300 border-green-200 dark:border-green-800'
                : 'bg-red-50 dark:bg-red-900/20 text-red-800 dark:text-red-300 border-red-200 dark:border-red-800'
                }`}
            >
              {testResult.message}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main EmbeddingSettings
// ---------------------------------------------------------------------------
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

      if (data.migration_info) {
        const modelInfo = data.migration_info.previous_model || data.migration_info.new_model;
        const previousModelData = {
          model_name: modelInfo?.model_name || data.embedding_model?.model_name || '',
          provider: modelInfo?.provider || data.embedding_model?.provider || 'openai',
          model_type: 'embedding',
          metadata: data.migration_info
        } as LLMModelConfig;
        setPreviousModel(previousModelData);

        if (data.migration_info.needs_migration && !data.migration_info.has_active_migration) {
          setShowMigrationPrompt(true);
        } else {
          setShowMigrationPrompt(false);
        }
      } else {
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
      setTestResult(result.message);
    } catch (err) {
      setTestResult(`${t('testFailedWithError' as any)}: ${err instanceof Error ? err.message : 'Unknown error'}`);
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
          previous_model: { model_name: string; provider: string; total_embeddings: number | null; first_used?: string; last_used?: string; last_updated?: string; };
          new_model: { model_name: string; provider: string; existing_embeddings: number; first_used?: string; last_used?: string; };
          historical_models: Array<{ model_name: string; provider: string; count: number; first_used?: string; last_used?: string; last_updated?: string; }>;
          missing_periods: Array<{ from: string; to: string; model: string; count: number; }>;
          has_active_migration?: boolean;
          migration_recommendation?: string;
          error?: string;
        };
      }>(`/api/v1/system-settings/llm-models/embedding?model_name=${modelName}&provider=${provider}`, {});

      await loadSettings();

      if (response.migration_info) {
        const modelInfo = response.migration_info.previous_model || response.migration_info.new_model;
        const previousModelData = {
          model_name: modelInfo?.model_name || modelName,
          provider: modelInfo?.provider || provider,
          model_type: 'embedding',
          metadata: response.migration_info
        } as LLMModelConfig;
        setPreviousModel(previousModelData);
        setShowMigrationPrompt(response.migration_info.needs_migration);
      } else {
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
      const result = await settingsApi.post<{ success: boolean; migration: EmbeddingMigration; message: string }>(
        '/api/v1/system-settings/embedding-migrations',
        {
          source_model: previousModel.model_name,
          target_model: settings.embedding_model.model_name,
          source_provider: previousModel.provider,
          target_provider: settings.embedding_model.provider,
          strategy: 'replace',
          scope: 'all',
        }
      );
      if (result.success && result.migration) {
        setMigration(result.migration);
        setShowMigrationPrompt(false);
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
      pollMigrationProgress(migrationId);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start migration');
    }
  };

  const pollMigrationProgress = (migrationId: string) => {
    const interval = setInterval(async () => {
      try {
        const result = await settingsApi.get<{ success: boolean; migration: EmbeddingMigration }>(
          `/api/v1/system-settings/embedding-migrations/${migrationId}`
        );
        if (result.success && result.migration) {
          setMigration(result.migration);
          setMigrationProgress(
            result.migration.total_count > 0
              ? Math.round((result.migration.completed_count / result.migration.total_count) * 100)
              : 0
          );
          if (['completed', 'failed', 'cancelled'].includes(result.migration.status)) {
            clearInterval(interval);
            setMigrating(false);
          }
        }
      } catch {
        clearInterval(interval);
      }
    }, 2000);
    setTimeout(() => clearInterval(interval), 5 * 60 * 1000);
  };

  const skipMigration = () => {
    setShowMigrationPrompt(false);
    setPreviousModel(null);
  };

  if (loading) {
    return <div className="text-center py-4 text-sm text-gray-500 dark:text-gray-400">{t('loading' as any)}</div>;
  }

  if (!settings) {
    return <div className="text-sm text-red-600 dark:text-red-400">{error || t('failedToLoad' as any)}</div>;
  }

  return (
    <div className="space-y-4">
      {error && <InlineAlert type="error" message={error} onDismiss={() => setError(null)} />}

      {/* ── Knowledge-base embedding header ──────────────────────────────── */}
      <div>
        <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-1">{t('embeddingModel' as any)}</h3>
        <p className="text-xs text-gray-500 dark:text-gray-400 mb-4">
          {t('embeddingModelDescription' as any)}
          {settings.embedding_model && (
            <span className="ml-2">
              {t('currentModel' as any)}: <strong>{settings.embedding_model.model_name}</strong> ({settings.embedding_model.provider})
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
          {testing ? t('testing' as any) : t('testConnection' as any)}
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
              <h4 className="text-sm font-semibold text-green-900 dark:text-green-200 mb-2">Embedding Status</h4>
              {previousModel.metadata.new_model && (
                <div className="mb-3 p-2 bg-white dark:bg-gray-800 rounded border border-green-200 dark:border-green-800">
                  <div className="text-xs font-medium text-green-900 dark:text-green-200 mb-1">Current Model:</div>
                  <div className="text-xs text-green-800 dark:text-green-300 space-y-1">
                    <div><strong>{previousModel.metadata.new_model.model_name}</strong> ({previousModel.metadata.new_model.provider})</div>
                    {previousModel.metadata.new_model.existing_embeddings > 0 && (
                      <div>Total Embeddings: <strong>{previousModel.metadata.new_model.existing_embeddings.toLocaleString()}</strong></div>
                    )}
                    {previousModel.metadata.new_model.existing_embeddings === 0 && (
                      <div className="space-y-2">
                        <div className="text-amber-600 dark:text-amber-400">
                          {t('noEmbeddingsFound' as any) || 'No embeddings found yet. Embeddings will be automatically generated when you:'}
                        </div>
                        <ul className="text-xs text-amber-700 dark:text-amber-300 list-disc list-inside ml-2 space-y-1">
                          <li>{t('embeddingGenerationMethod1' as any) || 'Upload documents to workspaces'}</li>
                          <li>{t('embeddingGenerationMethod2' as any) || 'Use AI features that require document search'}</li>
                          <li>{t('embeddingGenerationMethod3' as any) || 'Process files through playbooks'}</li>
                        </ul>
                        {(() => {
                          const prevEmbeds = previousModel.metadata?.previous_model?.total_embeddings || 0;
                          const historical = (previousModel.metadata?.historical_models || []).filter(
                            (m: any) => m.model_name !== previousModel.metadata?.new_model?.model_name && m.count > 0
                          );
                          const totalHist = historical.reduce((s: number, m: any) => s + m.count, 0);
                          if (prevEmbeds > 0 || totalHist > 0) {
                            const src = prevEmbeds > 0 ? previousModel.metadata.previous_model : historical[0];
                            return (
                              <div className="mt-2 pt-2 border-t border-amber-300 dark:border-amber-700">
                                <div className="text-xs text-amber-700 dark:text-amber-300 mb-2">
                                  Found {(prevEmbeds > 0 ? prevEmbeds : totalHist).toLocaleString()} embeddings from {src?.model_name || 'previous model'}:
                                </div>
                                <button onClick={() => setShowMigrationPrompt(true)}
                                  className="px-3 py-1.5 text-xs bg-amber-600 dark:bg-amber-700 text-white rounded-md hover:bg-amber-700 dark:hover:bg-amber-600 transition-colors">
                                  {t('reembedAllDocuments' as any) || 'Re-embed All Documents'}
                                </button>
                              </div>
                            );
                          }
                          return (
                            <div className="mt-2 pt-2 border-t border-amber-300 dark:border-amber-700">
                              <div className="text-xs text-amber-700 dark:text-amber-300 mb-2">
                                {t('hasHistoricalDataButNoEmbeddings' as any) || 'If you have historical documents, files, or conversations that need embedding, you can manually trigger embedding generation:'}
                              </div>
                              <button onClick={() => setShowMigrationPrompt(true)}
                                className="px-3 py-1.5 text-xs bg-amber-600 dark:bg-amber-700 text-white rounded-md hover:bg-amber-700 dark:hover:bg-amber-600 transition-colors">
                                {t('generateEmbeddingsForHistoricalData' as any) || 'Generate Embeddings for Historical Data'}
                              </button>
                            </div>
                          );
                        })()}
                      </div>
                    )}
                    {previousModel.metadata.new_model.first_used && (
                      <div>First Used: {new Date(previousModel.metadata.new_model.first_used).toLocaleString()}</div>
                    )}
                    {previousModel.metadata.new_model.last_used && (
                      <div>Last Used: {new Date(previousModel.metadata.new_model.last_used).toLocaleString()}</div>
                    )}
                  </div>
                </div>
              )}
              {previousModel.metadata.historical_models && previousModel.metadata.historical_models.length > 0 && (
                <details className="mb-3">
                  <summary className="text-xs font-medium text-green-900 dark:text-green-200 cursor-pointer hover:text-green-700 dark:hover:text-green-300">
                    View All Historical Models ({previousModel.metadata.historical_models.length})
                  </summary>
                  <div className="mt-2 p-2 bg-white dark:bg-gray-800 rounded border border-green-200 dark:border-green-800 text-xs space-y-1">
                    {previousModel.metadata.historical_models.map((model: any, idx: number) => (
                      <div key={idx} className="flex justify-between items-center">
                        <span><strong>{model.model_name}</strong> ({model.provider})</span>
                        <span className="text-gray-600 dark:text-gray-400">{model.count.toLocaleString()} embeddings</span>
                      </div>
                    ))}
                  </div>
                </details>
              )}
              {previousModel.metadata.migration_recommendation && (
                <div className="mb-3 p-2 bg-accent-10 dark:bg-blue-900/20 rounded border border-accent/30 dark:border-blue-800">
                  <div className="text-xs font-medium text-accent dark:text-blue-200 mb-1">Status:</div>
                  <div className="text-xs text-accent dark:text-blue-300">{previousModel.metadata.migration_recommendation}</div>
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
              {previousModel.metadata.previous_model && (
                <div className="mb-3 p-2 bg-white dark:bg-gray-800 rounded border border-amber-200 dark:border-amber-800">
                  <div className="text-xs font-medium text-amber-900 dark:text-amber-200 mb-1">Previous Model:</div>
                  <div className="text-xs text-amber-800 dark:text-amber-300 space-y-1">
                    <div><strong>{previousModel.metadata.previous_model.model_name}</strong> ({previousModel.metadata.previous_model.provider})</div>
                    {previousModel.metadata.previous_model.total_embeddings !== null && (
                      <div>Total Embeddings: <strong>{previousModel.metadata.previous_model.total_embeddings.toLocaleString()}</strong></div>
                    )}
                  </div>
                </div>
              )}
              {previousModel.metadata.new_model && (
                <div className="mb-3 p-2 bg-surface-accent dark:bg-gray-800 rounded border border-accent/30 dark:border-blue-800">
                  <div className="text-xs font-medium text-accent dark:text-blue-200 mb-1">New Model:</div>
                  <div className="text-xs text-accent dark:text-blue-300 space-y-1">
                    <div><strong>{previousModel.metadata.new_model.model_name}</strong> ({previousModel.metadata.new_model.provider})</div>
                    {previousModel.metadata.new_model.existing_embeddings === 0 && (
                      <div className="text-amber-600 dark:text-amber-400">New model has no embeddings yet</div>
                    )}
                  </div>
                </div>
              )}
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
                <button onClick={createMigration} disabled={migrating}
                  className="px-3 py-1.5 text-sm bg-amber-600 dark:bg-amber-700 text-white rounded-md hover:bg-amber-700 dark:hover:bg-amber-600 disabled:opacity-50 disabled:cursor-not-allowed">
                  {migrating ? 'Preparing...' : 'Start Re-embedding'}
                </button>
                <button onClick={skipMigration} disabled={migrating}
                  className="px-3 py-1.5 text-sm bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-md hover:bg-gray-300 dark:hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed">
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
              {migration.status === 'running' ? '…' : migration.status === 'completed' ? '✓' : migration.status === 'failed' ? '✗' : '○'}
            </div>
            <div className="flex-1">
              <h4 className="text-sm font-semibold text-accent dark:text-blue-200 mb-2">Re-embedding in Progress</h4>
              {migration.status === 'running' && (
                <>
                  <div className="mb-2">
                    <div className="flex justify-between text-xs text-accent dark:text-blue-300 mb-1">
                      <span>Progress: {migration.completed_count} / {migration.total_count}</span>
                      <span>{migrationProgress}%</span>
                    </div>
                    <div className="w-full bg-accent-10 dark:bg-blue-800 rounded-full h-2">
                      <div className="bg-accent dark:bg-blue-500 h-2 rounded-full transition-all duration-300" style={{ width: `${migrationProgress}%` }} />
                    </div>
                  </div>
                  <p className="text-xs text-accent dark:text-blue-400">Re-embedding document vectors. Please do not close this page...</p>
                </>
              )}
              {migration.status === 'completed' && (
                <p className="text-sm text-accent dark:text-blue-300">Re-embedding completed! Processed {migration.total_count} embeddings.</p>
              )}
              {migration.status === 'failed' && (
                <p className="text-sm text-red-800 dark:text-red-300">Re-embedding failed. Please check backend logs or retry.</p>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Knowledge-base model selector */}
      <div>
        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
          {t('selectEmbeddingModel' as any) || '選擇知識庫 Embedding 模型'}
        </label>
        {enabledEmbeddingModels.length === 0 ? (
          <div className="p-3 border border-gray-300 dark:border-gray-600 rounded-md bg-gray-50 dark:bg-gray-800 text-sm text-gray-500 dark:text-gray-400">
            {t('noEnabledModels' as any) || '沒有已啟用的 Embedding 模型。請在「模型與配額」中啟用至少一個模型。'}
          </div>
        ) : (
          <select
            value={settings.embedding_model?.model_name || ''}
            onChange={(e) => {
              const selected = enabledEmbeddingModels.find(m => m.model_name === e.target.value);
              if (selected) updateEmbeddingModel(selected.model_name, selected.provider);
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

      {/* ── Tool RAG Embedding — separate from knowledge-base embedding ───── */}
      <OllamaToolEmbeddingSection />
    </div>
  );
}
