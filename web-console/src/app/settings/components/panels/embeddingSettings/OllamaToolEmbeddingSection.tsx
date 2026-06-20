'use client';

import { useEffect, useState } from 'react';

import { InlineAlert } from '../../InlineAlert';
import { settingsApi } from '../../../utils/settingsApi';

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
      const setting = await settingsApi
        .get<{ value?: string }>('/api/v1/system-settings/ollama_embed_model')
        .catch(() => ({ value: '' }));
      setCurrentModel((setting as any)?.value ?? '');

      const ollamaData = await settingsApi
        .get<{ models?: Array<{ name?: string }> }>('/api/v1/tools/rag-models')
        .catch(() => null);
      if (ollamaData && Array.isArray((ollamaData as any).models)) {
        setAvailableModels((ollamaData as any).models.map((m: any) => m.name ?? '').filter(Boolean));
      } else {
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
          ? `Success: Tool RAG search is healthy. Model: ${model}. Matches: ${(res as any).match_count}`
          : `Warning: search returned unexpected status=${(res as any).status}`,
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
          Tool RAG Embedding Model
        </h3>
        <p className="text-xs text-gray-500 dark:text-gray-400">
          Local Ollama embedding model used for Tool RAG indexing. This setting is independent from the knowledge-base embedding model.
          Leave it empty to auto-select on startup, preferring <code className="bg-gray-100 dark:bg-gray-700 px-1 rounded">bge-m3</code>.
        </p>
      </div>

      {error && <InlineAlert type="error" message={error} onDismiss={() => setError(null)} />}

      {loading ? (
        <div className="text-xs text-gray-400 py-2">Loading...</div>
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
              <option value="">Auto-select (recommended)</option>
              {availableModels.map((m) => (
                <option key={m} value={m}>{m}</option>
              ))}
            </select>
            {saving && <span className="text-xs text-gray-400">Saving...</span>}
          </div>

          {currentModel ? (
            <div className="text-xs text-green-700 dark:text-green-400 bg-green-50 dark:bg-green-900/20 px-2 py-1 rounded border border-green-200 dark:border-green-800">
              Pinned model: <strong>{currentModel}</strong>
            </div>
          ) : (
            <div className="text-xs text-gray-500 dark:text-gray-400 bg-gray-50 dark:bg-gray-800 px-2 py-1 rounded border border-gray-200 dark:border-gray-700">
              Auto-select mode: startup selects bge-m3 before nomic-embed-text from Ollama.
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
              {testing ? 'Testing search...' : 'Test Tool RAG Search'}
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
