'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { t } from '../../../../lib/i18n';
import { settingsApi } from '../../utils/settingsApi';
import { ModelConfigCard, PullState } from './ModelConfigCard';
import { showNotification } from '../../hooks/useSettingsNotification';
import { OllamaToolEmbeddingSection } from './EmbeddingSettings';
import { useEnabledModels, EnabledModel } from '../../hooks/useEnabledModels';
import CliApiKeysSection from '../../../workspaces/[workspaceId]/components/CliApiKeysSection';

interface ModelItem {
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

interface ModelConfigCardData {
  model: ModelItem;
  api_key_configured: boolean;
  base_url?: string;
  quota_info?: {
    used: number;
    limit: number;
    reset_date?: string;
  };
}

type ModelTypeFilter = 'chat' | 'embedding' | 'multimodal' | 'tool-calling';
type SubTab = 'models' | 'dynamic';

const CHAT_PROFILES = [
  { key: 'fast',       label: '快速 (Fast)',       description: 'Facilitator / 快速回應' },
  { key: 'standard',   label: '標準 (Standard)',   description: '一般對話 / 預設路徑' },
  { key: 'precise',    label: '精確 (Precise)',     description: 'Planner / Critic / 深度推理' },
  { key: 'safe_write', label: '安全寫入 (Safe)',    description: 'Program Synthesizer' },
];

const MULTIMODAL_PROFILES = [
  { key: 'vision',     label: '視覺 (Vision)',      description: '多模態影像分析' },
];



export function ModelsAndQuotaPanel() {
  const [loading, setLoading] = useState(true);
  const [models, setModels] = useState<ModelItem[]>([]);
  const [selectedModel, setSelectedModel] = useState<ModelItem | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedProvider, setSelectedProvider] = useState<string | null>(null);
  const [modelTypeFilter, setModelTypeFilter] = useState<ModelTypeFilter>('chat');
  const [configCard, setConfigCard] = useState<ModelConfigCardData | null>(null);
  const [togglingModels, setTogglingModels] = useState<Set<string>>(new Set());
  const [hoveredModelId, setHoveredModelId] = useState<string | number | null>(null);
  const [subTab, setSubTab] = useState<SubTab>('models');

  // ── Centralized pull state management ──
  const [activePulls, setActivePulls] = useState<Record<string, PullState>>({});
  const pollIntervalRef = React.useRef<ReturnType<typeof setInterval> | null>(null);


  // Profile routing state
  const [profileMap, setProfileMap] = useState<Record<string, string>>({});
  const [profileSaving, setProfileSaving] = useState(false);
  const { enabledModels: enabledChatModels } = useEnabledModels('chat');
  const { enabledModels: enabledMultimodalModels } = useEnabledModels('multimodal');

  // Embedding test connection state
  const [embeddingTesting, setEmbeddingTesting] = useState(false);
  const [embeddingTestResult, setEmbeddingTestResult] = useState<string | null>(null);

  // HF Discovery modal state
  const [showAddModal, setShowAddModal] = useState(false);
  const [hfSearchQuery, setHfSearchQuery] = useState('');
  const [hfResults, setHfResults] = useState<Array<{
    model_id: string; pipeline_tag: string; model_type: string;
    downloads: number; likes: number;
  }>>([]);
  const [hfLoading, setHfLoading] = useState(false);
  const [hfRegistering, setHfRegistering] = useState<string | null>(null);
  const [customRepoId, setCustomRepoId] = useState('');
  const [addModelType, setAddModelType] = useState<string>(modelTypeFilter as string === 'tool-calling' ? 'chat' : modelTypeFilter);

  // Auto-search when modal opens, model type changes, or search query is cleared
  useEffect(() => {
    if (!showAddModal) return;
    const doSearch = async () => {
      setHfLoading(true);
      try {
        const results = await settingsApi.get<Array<{
          model_id: string; pipeline_tag: string; model_type: string;
          downloads: number; likes: number;
        }>>(`/api/v1/system-settings/discover/huggingface?model_type=${addModelType}&limit=20${hfSearchQuery ? `&search=${encodeURIComponent(hfSearchQuery)}` : ''}`);
        setHfResults(results);
      } catch (err) {
        // silent on auto-search
      } finally {
        setHfLoading(false);
      }
    };
    doSearch();
  }, [showAddModal, addModelType]);

  // When search query is cleared, auto-reload default list
  useEffect(() => {
    if (!showAddModal || hfSearchQuery !== '') return;
    const doSearch = async () => {
      setHfLoading(true);
      try {
        const results = await settingsApi.get<Array<{
          model_id: string; pipeline_tag: string; model_type: string;
          downloads: number; likes: number;
        }>>(`/api/v1/system-settings/discover/huggingface?model_type=${addModelType}&limit=20`);
        setHfResults(results);
      } catch (err) {
        // silent
      } finally {
        setHfLoading(false);
      }
    };
    doSearch();
  }, [hfSearchQuery]);

  useEffect(() => {
    loadAllModels();
    loadProfileMap();
  }, []);

  useEffect(() => {
    if (selectedModel && selectedModel.enabled) {
      loadModelConfig(selectedModel);
    } else {
      setConfigCard(null);
    }
  }, [selectedModel]);

  // Clear test result when switching models or tabs
  useEffect(() => {
    setEmbeddingTestResult(null);
  }, [selectedModel, modelTypeFilter]);

  const handleConfigSaved = () => {
    if (selectedModel) {
      loadModelConfig(selectedModel);
    }
  };

  // ── Pull management ──
  const startPolling = useCallback((modelId: string, taskId: string) => {
    const intervalId = setInterval(async () => {
      try {
        const resp = await fetch(`/api/v1/system-settings/llm-models/pull/${taskId}/progress`);
        if (!resp.ok) {
          clearInterval(intervalId);
          // Clean up stuck state when task expired/not found
          setActivePulls(prev => { const n = { ...prev }; delete n[modelId]; return n; });
          return;
        }
        const prog = await resp.json();
        setActivePulls(prev => ({
          ...prev,
          [modelId]: {
            taskId: prog.task_id,
            progress: prog.progress_pct || 0,
            status: prog.status || '',
            message: prog.message || '',
            totalBytes: prog.total_bytes || 0,
            downloadedBytes: prog.downloaded_bytes || 0,
          }
        }));
        if (prog.status === 'completed') {
          clearInterval(intervalId);
          showNotification('success', prog.message || '下載完成！');
          setTimeout(() => {
            setActivePulls(prev => { const n = { ...prev }; delete n[modelId]; return n; });
          }, 3000);
        } else if (prog.status === 'failed' || prog.status === 'cancelled') {
          clearInterval(intervalId);
          if (prog.status === 'failed') showNotification('error', prog.message || '下載失敗');
          setTimeout(() => {
            setActivePulls(prev => { const n = { ...prev }; delete n[modelId]; return n; });
          }, 3000);
        }
      } catch {
        // polling error, ignore
      }
    }, 1000);
    return intervalId;
  }, []);

  const handlePullModel = useCallback(async (model: { id: string | number; model_name: string; provider: string }) => {
    const modelId = String(model.id);
    try {
      setActivePulls(prev => ({
        ...prev,
        [modelId]: { taskId: '', progress: 0, status: 'starting', message: '啟動下載中...', totalBytes: 0, downloadedBytes: 0 }
      }));

      const result = await settingsApi.post<{ success: boolean; task_id?: string; message: string }>(
        `/api/v1/system-settings/llm-models/pull`,
        { model_name: model.model_name, provider: model.provider, model_id: modelId }
      );

      if (!result.success || !result.task_id) {
        showNotification('error', result.message || 'Failed to start download');
        setActivePulls(prev => { const n = { ...prev }; delete n[modelId]; return n; });
        return;
      }

      setActivePulls(prev => ({
        ...prev,
        [modelId]: { ...prev[modelId], taskId: result.task_id! }
      }));

      startPolling(modelId, result.task_id);
    } catch (err) {
      showNotification('error', `下載失敗: ${err instanceof Error ? err.message : 'Unknown error'}`);
      setActivePulls(prev => { const n = { ...prev }; delete n[modelId]; return n; });
    }
  }, [startPolling]);

  const handleCancelPull = useCallback(async (taskId: string) => {
    try {
      await settingsApi.post(`/api/v1/system-settings/llm-models/pull/${taskId}/cancel`, {});
      showNotification('success', '下載已取消');
    } catch {
      showNotification('error', '取消失敗');
    }
  }, []);

  const handleRemoveModel = useCallback(async (modelId: string | number) => {
    try {
      const result = await settingsApi.delete<{ success: boolean; message: string }>(
        `/api/v1/system-settings/models/${modelId}`
      );
      if (result.success) {
        showNotification('success', '模型已移除');
        setModels(prev => prev.filter(m => String(m.id) !== String(modelId)));
        if (selectedModel && String(selectedModel.id) === String(modelId)) {
          setSelectedModel(null);
          setConfigCard(null);
        }
      } else {
        showNotification('error', result.message || '移除失敗');
      }
    } catch (err) {
      showNotification('error', `移除失敗: ${err instanceof Error ? err.message : 'Unknown error'}`);
    }
  }, [selectedModel]);

  // Recover active pulls on page load
  useEffect(() => {
    const recoverPulls = async () => {
      try {
        const resp = await fetch('/api/v1/system-settings/llm-models/pull/active');
        if (!resp.ok) return;
        const tasks = await resp.json();
        for (const task of tasks) {
          const modelId = task.model_id || task.model_name;
          if (modelId && (task.status === 'starting' || task.status === 'downloading')) {
            setActivePulls(prev => ({
              ...prev,
              [modelId]: {
                taskId: task.task_id,
                progress: task.progress_pct || 0,
                status: task.status,
                message: task.message || '',
                totalBytes: task.total_bytes || 0,
                downloadedBytes: task.downloaded_bytes || 0,
              }
            }));
            startPolling(modelId, task.task_id);
          }
        }
      } catch { /* ignore */ }
    };
    recoverPulls();
  }, [startPolling]);

  const loadProfileMap = async () => {
    try {
      const data = await settingsApi.get<{
        profile_model_map: Record<string, string>;
      }>('/api/v1/system-settings/capability-profiles');
      setProfileMap(data.profile_model_map || {});
    } catch { /* silent — routing tab will show defaults */ }
  };

  const saveProfileMap = async (updated: Record<string, string>) => {
    const prev = { ...profileMap };
    setProfileMap(updated);
    setProfileSaving(true);
    try {
      await settingsApi.put('/api/v1/system-settings/capability-profiles', {
        profile_model_map: updated,
      });
      showNotification('success', 'Profile routing saved');
    } catch (err) {
      setProfileMap(prev);
      showNotification('error', err instanceof Error ? err.message : 'Save failed');
    } finally {
      setProfileSaving(false);
    }
  };



  const loadAllModels = async () => {
    try {
      setLoading(true);

      const data = await settingsApi.get<Array<{
        id: number;
        model_name: string;
        provider: string;
        model_type: 'chat' | 'embedding';
        display_name: string;
        description: string;
        enabled: boolean;
        is_latest?: boolean;
        is_recommended?: boolean;
        is_deprecated?: boolean;
        dimensions?: number;
        context_window?: number;
        icon?: string;
        metadata?: Record<string, any>;
      }>>('/api/v1/system-settings/models');

      const models: ModelItem[] = data.map((m) => ({
        id: m.id,
        model_name: m.model_name,
        provider: m.provider,
        model_type: m.model_type,
        display_name: m.display_name || m.model_name,
        description: m.description,
        enabled: m.enabled,
        icon: m.icon,
        is_latest: m.is_latest,
        is_recommended: m.is_recommended,
        dimensions: m.dimensions,
        context_window: m.context_window,
        metadata: m.metadata,
      }));

      setModels(models);

      // ── Auto-enrich HF models missing metadata (browser → HF API → backend PATCH) ──
      const hfMissing = models.filter(
        (m) => m.provider === 'huggingface' && m.model_name.includes('/') && !m.metadata?.hf_author
      );
      if (hfMissing.length > 0) {
        (async () => {
          for (const m of hfMissing) {
            try {
              const hfResp = await fetch(`https://huggingface.co/api/models/${m.model_name}`);
              if (!hfResp.ok) continue;
              const d = await hfResp.json();
              const tags: string[] = (d.tags || []).filter((t: any) => typeof t === 'string');
              const fmt = tags.includes('gguf') ? 'GGUF' : tags.some((t: string) => t.toLowerCase() === 'mlx') ? 'MLX' : 'safetensors';
              const quant = tags.find((t: string) => ['4-bit', '8-bit', 'fp8', 'gptq', 'awq'].some((q) => t.toLowerCase().includes(q))) || null;
              let params = null;
              if (d.safetensors?.total) params = d.safetensors.total;
              if (d.gguf?.total) params = d.gguf.total;
              const ctx = d.gguf?.context_length || null;

              const meta = {
                hf_author: d.author || '',
                hf_format: fmt,
                hf_quantization: quant,
                hf_library: d.library_name || '',
                hf_pipeline_tag: d.pipeline_tag || '',
                hf_parameters: params,
                hf_context_length: ctx,
                hf_downloads: d.downloads || 0,
                hf_likes: d.likes || 0,
                hf_tags: tags.slice(0, 15),
                hf_storage_bytes: d.usedStorage || null,
              };

              await fetch(`/api/v1/system-settings/models/${m.id}/metadata`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(meta),
              });
              // Update local state immediately
              setModels((prev) => prev.map((pm) => pm.id === m.id ? { ...pm, metadata: { ...pm.metadata, ...meta } } : pm));
            } catch {
              // skip individual failures silently
            }
          }
        })();
      }
    } catch (err) {
      showNotification('error', err instanceof Error ? err.message : 'Failed to load models');
    } finally {
      setLoading(false);
    }
  };

  const loadModelConfig = async (model: ModelItem) => {
    try {
      const data = await settingsApi.get<ModelConfigCardData>(
        `/api/v1/system-settings/models/${model.id}/config`
      );
      setConfigCard(data);
    } catch (err) {
      const configCardData: ModelConfigCardData = {
        model,
        api_key_configured: false,
        base_url: model.provider === 'ollama' ? 'http://localhost:11434' : undefined,
      };
      setConfigCard(configCardData);
    }
  };

  const toggleModel = async (modelId: string, enabled: boolean) => {
    if (togglingModels.has(modelId)) {
      return;
    }

    const currentModel = models.find(m => String(m.id) === modelId);
    if (!currentModel) {
      return;
    }

    const previousEnabled = currentModel.enabled;
    const wasSelected = selectedModel && String(selectedModel.id) === modelId;

    setTogglingModels(prev => new Set(prev).add(modelId));

    setModels(prev => prev.map(m =>
      String(m.id) === modelId ? { ...m, enabled } : m
    ));

    if (enabled) {
      setSelectedModel({ ...currentModel, enabled: true });
    } else if (wasSelected) {
      setSelectedModel(null);
      setConfigCard(null);
    }

    try {
      const numericModelId = Number(modelId);
      if (isNaN(numericModelId)) {
        throw new Error(`Invalid model ID: ${modelId}`);
      }

      const updatedModel = await settingsApi.put<ModelItem>(
        `/api/v1/system-settings/models/${numericModelId}/enable`,
        { enabled }
      );

      setModels(prev => prev.map(m =>
        String(m.id) === modelId ? { ...m, enabled: updatedModel.enabled } : m
      ));

      if (updatedModel.enabled && wasSelected) {
        const updatedSelectedModel = { ...currentModel, enabled: true };
        setSelectedModel(updatedSelectedModel);
        loadModelConfig(updatedSelectedModel);
      }
    } catch (err) {
      showNotification('error', err instanceof Error ? err.message : 'Failed to toggle model');
      setModels(prev => prev.map(m =>
        String(m.id) === modelId ? { ...m, enabled: previousEnabled } : m
      ));

      if (previousEnabled && wasSelected) {
        setSelectedModel({ ...currentModel, enabled: previousEnabled });
      } else if (!previousEnabled && wasSelected) {
        setSelectedModel(null);
        setConfigCard(null);
      }
    } finally {
      setTogglingModels(prev => {
        const next = new Set(prev);
        next.delete(modelId);
        return next;
      });
    }
  };

  const testEmbeddingConnection = useCallback(async () => {
    try {
      setEmbeddingTesting(true);
      setEmbeddingTestResult(null);
      const result = await settingsApi.post<{
        success: boolean;
        message: string;
        model_name: string;
        provider: string;
        dimensions?: number;
      }>('/api/v1/system-settings/llm-models/test-embedding');

      setEmbeddingTestResult(result.message);
    } catch (err) {
      setEmbeddingTestResult(`Test failed: ${err instanceof Error ? err.message : 'Unknown error'}`);
    } finally {
      setEmbeddingTesting(false);
    }
  }, []);

  // Derived values — only filter models for chat/embedding/multimodal tabs
  const LOCAL_PROVIDERS = new Set(['ollama', 'llama-cpp', 'llamacpp', 'huggingface']);
  const filteredModels = models.filter(model => {
    if (modelTypeFilter === 'tool-calling') return false;
    const matchesType = model.model_type === modelTypeFilter;
    const matchesSearch = !searchQuery ||
      model.display_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      model.provider.toLowerCase().includes(searchQuery.toLowerCase()) ||
      model.description.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesProvider = (() => {
      if (selectedProvider === null) return true;
      if (selectedProvider === '__local__') return LOCAL_PROVIDERS.has(model.provider);
      return model.provider === selectedProvider;
    })();
    return matchesType && matchesSearch && matchesProvider;
  });

  const providers = Array.from(
    new Set(
      models
        .filter(m => m.model_type === modelTypeFilter)
        .map(m => m.provider)
        .filter(p => !LOCAL_PROVIDERS.has(p))
    )
  ).sort();

  const hasLocalModels = models.some(
    m => m.model_type === modelTypeFilter && LOCAL_PROVIDERS.has(m.provider)
  );

  const chatCount = models.filter(m => m.model_type === 'chat').length;
  const embeddingCount = models.filter(m => m.model_type === 'embedding').length;
  const multimodalCount = models.filter(m => m.model_type === 'multimodal').length;

  // Helper for tab button classes
  const tabClass = (active: boolean) =>
    `flex-1 px-4 py-2 text-sm font-medium rounded-md transition-all whitespace-nowrap flex items-center justify-center ${active
      ? 'bg-surface-secondary dark:bg-gray-700 text-gray-900 dark:text-gray-100 shadow-sm'
      : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300'
    }`;
  const badgeClass = (active: boolean) =>
    `ml-1.5 text-xs px-1.5 py-0.5 rounded-full ${active
      ? 'bg-accent-10 dark:bg-purple-900/30 text-accent dark:text-purple-300'
      : 'bg-gray-200 dark:bg-gray-600 text-gray-500 dark:text-gray-400'
    }`;

  if (loading) {
    return <div className="text-center py-4 text-sm text-gray-500 dark:text-gray-400">{t('loading' as any)}</div>;
  }

  const switchTab = (tab: ModelTypeFilter) => {
    setModelTypeFilter(tab);
    setSelectedProvider(null);
    setSelectedModel(null);
    setSubTab('models');
  };

  // ── HF Discovery helpers ──
  const searchHF = async () => {
    setHfLoading(true);
    try {
      const results = await settingsApi.get<Array<{
        model_id: string; pipeline_tag: string; model_type: string;
        downloads: number; likes: number;
      }>>(`/api/v1/system-settings/discover/huggingface?model_type=${addModelType}&limit=20${hfSearchQuery ? `&search=${encodeURIComponent(hfSearchQuery)}` : ''}`);
      setHfResults(results);
    } catch (err) {
      showNotification('error', `HF 搜尋失敗: ${err instanceof Error ? err.message : 'Unknown'}`);
    } finally {
      setHfLoading(false);
    }
  };

  const registerModel = async (modelId: string, modelType: string) => {
    setHfRegistering(modelId);
    try {
      await settingsApi.post('/api/v1/system-settings/models/custom', {
        model_id: modelId,
        provider: 'huggingface',
        model_type: modelType,
      });
      showNotification('success', `已註冊: ${modelId}`);
      loadAllModels();
    } catch (err) {
      showNotification('error', `註冊失敗: ${err instanceof Error ? err.message : 'Unknown'}`);
    } finally {
      setHfRegistering(null);
    }
  };

  const registerCustomId = async () => {
    const repoId = customRepoId.trim();
    if (!repoId) return;
    setHfRegistering(repoId);
    try {
      await settingsApi.post('/api/v1/system-settings/models/custom', {
        model_id: repoId,
        provider: 'huggingface',
        model_type: addModelType,
      });
      showNotification('success', `已註冊: ${repoId}`);
      setCustomRepoId('');
      loadAllModels();
    } catch (err) {
      showNotification('error', `註冊失敗: ${err instanceof Error ? err.message : 'Unknown'}`);
    } finally {
      setHfRegistering(null);
    }
  };

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* ── Tab bar ────────────────────────────────────────────────────────── */}
      <div className="flex-shrink-0 border-b border-gray-200 dark:border-gray-700 pb-3 mb-3">
        <div className="flex flex-col xl:flex-row xl:items-center justify-between gap-4 mb-3">
          <div className="xl:max-w-sm shrink-0">
            <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-1">
              {t('modelsAndQuota' as any) || '模型與配額'}
            </h3>
            <p className="text-xs text-gray-500 dark:text-gray-400 leading-relaxed max-w-sm">
              {modelTypeFilter === 'chat'
                ? '設定與管理負責對話推理的大型語言模型'
                : modelTypeFilter === 'multimodal'
                  ? '管理多模態模型（支援圖片、音訊等輸入）'
                  : modelTypeFilter === 'embedding' 
                    ? '管理知識庫與記憶向量化模型'
                    : '配置工具調用的相關設定'}
            </p>
          </div>

          <div className="flex items-center gap-1 bg-gray-100 dark:bg-gray-800 rounded-lg p-1 self-start w-full xl:w-auto xl:flex-1 max-w-3xl">
            {/* Chat / Plan */}
            <button onClick={() => switchTab('chat')} className={tabClass(modelTypeFilter === 'chat')}>
              Chat / Plan
              <span className={badgeClass(modelTypeFilter === 'chat')}>{chatCount}</span>
            </button>

            {/* 知識庫 Embedding */}
            <button onClick={() => switchTab('embedding')} className={tabClass(modelTypeFilter === 'embedding')}>
              知識與記憶
              <span className={badgeClass(modelTypeFilter === 'embedding')}>{embeddingCount}</span>
            </button>

            {/* 多模態 Multimodal */}
            <button onClick={() => switchTab('multimodal')} className={tabClass(modelTypeFilter === 'multimodal')}>
              多模態
              <span className={badgeClass(modelTypeFilter === 'multimodal')}>{multimodalCount}</span>
            </button>

            {/* 工具調用 */}
            <button onClick={() => switchTab('tool-calling')} className={tabClass(modelTypeFilter === 'tool-calling')}>
              工具調用
            </button>
          </div>
        </div>

        {/* Header + Provider Filter — hidden on tool-calling tab and dynamic sub-tab */}
        {modelTypeFilter !== 'tool-calling' && subTab === 'models' && (
          <>
            <div className="flex flex-col gap-2 mb-3">
              {/* Provider Filter Bar */}
              <div className="flex flex-wrap gap-2">
                {/* Runtime CLI — only in Chat/Plan */}
                {modelTypeFilter === 'chat' && (
                  <>
                    <button
                      onClick={() => setSelectedProvider('__runtime_cli__')}
                      data-filter-button="runtime-cli"
                      className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors border ${selectedProvider === '__runtime_cli__'
                        ? 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 border-blue-400/40 dark:border-blue-700'
                        : 'bg-surface-accent dark:bg-gray-700 text-primary dark:text-gray-300 border-default dark:border-gray-600 hover:bg-surface-secondary dark:hover:bg-gray-600'
                      }`}
                    >
                      ⚙️ Runtime CLI
                    </button>
                    <span className="text-gray-300 dark:text-gray-600 mx-1 flex items-center">|</span>
                  </>
                )}
                <button
                  onClick={() => setSelectedProvider(null)}
                  data-filter-button="all"
                  className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors border ${selectedProvider === null
                    ? 'bg-accent-10 dark:bg-purple-900/20 text-accent dark:text-purple-300 border-accent/30 dark:border-purple-700'
                    : 'bg-surface-accent dark:bg-gray-700 text-primary dark:text-gray-300 border-default dark:border-gray-600 hover:bg-surface-secondary dark:hover:bg-gray-600'
                    }`}
                >
                  {t('allProviders' as any) || 'All'}
                </button>
                {providers.map((provider) => (
                  <button
                    key={provider}
                    onClick={() => setSelectedProvider(provider)}
                    data-filter-button={provider}
                    className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors border ${selectedProvider === provider
                      ? 'bg-accent-10 dark:bg-purple-900/20 text-accent dark:text-purple-300 border-accent/30 dark:border-purple-700'
                      : 'bg-surface-accent dark:bg-gray-700 text-primary dark:text-gray-300 border-default dark:border-gray-600 hover:bg-surface-secondary dark:hover:bg-gray-600'
                      }`}
                  >
                    {provider}
                  </button>
                ))}
                {/* ── 本地佈署 separator ── */}
                {hasLocalModels && (
                  <>
                    <span className="text-gray-300 dark:text-gray-600 mx-1 flex items-center">|</span>
                    <button
                      onClick={() => setSelectedProvider('__local__')}
                      data-filter-button="local"
                      className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors border ${selectedProvider === '__local__'
                        ? 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300 border-green-400/40 dark:border-green-700'
                        : 'bg-surface-accent dark:bg-gray-700 text-primary dark:text-gray-300 border-default dark:border-gray-600 hover:bg-surface-secondary dark:hover:bg-gray-600'
                        }`}
                    >
                      🏠 本地佈署
                    </button>
                  </>
                )}
              </div>
            </div>
          </>
        )}

        {/* ── Sub-tab bar (Chat/Plan + 多模態 only) + inline search ── */}
        {(modelTypeFilter === 'chat' || modelTypeFilter === 'multimodal') && (
          <div className="flex items-center gap-3 mt-2">
            <div className="flex gap-2">
              <button
                onClick={() => setSubTab('models')}
                className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${subTab === 'models'
                  ? 'bg-accent-10 dark:bg-purple-900/20 text-accent dark:text-purple-300 border border-accent/30 dark:border-purple-700'
                  : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 border border-transparent'
                }`}
              >
                模型清單
              </button>
              <button
                onClick={() => setSubTab('dynamic')}
                className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${subTab === 'dynamic'
                  ? 'bg-accent-10 dark:bg-purple-900/20 text-accent dark:text-purple-300 border border-accent/30 dark:border-purple-700'
                  : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 border border-transparent'
                }`}
              >
                動態分配
              </button>
            </div>
            {subTab === 'models' && (
              <div className="flex flex-1 items-center gap-2">
                <input
                  type="text"
                  placeholder={t('searchModels' as any) || 'Search models'}
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="flex-1 px-3 py-1.5 text-sm border border-default dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-accent/50 dark:focus:ring-gray-500 bg-surface-accent dark:bg-gray-800 text-primary dark:text-gray-100"
                />
                <button
                  onClick={() => { setShowAddModal(true); setAddModelType((modelTypeFilter as string) === 'tool-calling' ? 'chat' : modelTypeFilter); }}
                  data-filter-button="add-model"
                  className="px-3 py-1.5 text-sm font-medium rounded-md transition-colors border bg-orange-50 dark:bg-orange-900/20 text-orange-700 dark:text-orange-300 border-orange-300 dark:border-orange-700 hover:bg-orange-100 dark:hover:bg-orange-900/40 whitespace-nowrap"
                >
                  ＋ 新增模型
                </button>
              </div>
            )}
          </div>
        )}

        {/* Search for embedding/non-sub-tab tabs */}
        {modelTypeFilter === 'embedding' && (
          <div className="flex items-center gap-2 mt-2">
            <input
              type="text"
              placeholder={t('searchModels' as any) || 'Search models'}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="flex-1 px-3 py-1.5 text-sm border border-default dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-accent/50 dark:focus:ring-gray-500 bg-surface-accent dark:bg-gray-800 text-primary dark:text-gray-100"
            />
            <button
              onClick={() => { setShowAddModal(true); setAddModelType('embedding'); }}
              data-filter-button="add-model"
              className="px-3 py-1.5 text-sm font-medium rounded-md transition-colors border bg-orange-50 dark:bg-orange-900/20 text-orange-700 dark:text-orange-300 border-orange-300 dark:border-orange-700 hover:bg-orange-100 dark:hover:bg-orange-900/40 whitespace-nowrap"
            >
              ＋ 新增模型
            </button>
          </div>
        )}
      </div>

      {/* ── Tool Calling tab body ────────────────────────────────────────── */}
      {modelTypeFilter === 'tool-calling' && (
        <div className="flex-1">
          <OllamaToolEmbeddingSection />
        </div>
      )}

      {/* ── Runtime CLI (when selectedProvider = __runtime_cli__) ─ */}
      {modelTypeFilter === 'chat' && subTab === 'models' && selectedProvider === '__runtime_cli__' && (
        <div className="flex-1">
          <CliApiKeysSection />
        </div>
      )}

      {/* ── Dynamic Allocation sub-tab body ───────────────────────────── */}
      {subTab === 'dynamic' && (modelTypeFilter === 'chat' || modelTypeFilter === 'multimodal') && (
        <div className="flex-1">
          <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-1">
            動態分配
          </h3>
          <p className="text-xs text-gray-500 dark:text-gray-400 mb-4">
            設定每個能力等級使用的模型。留空則使用系統預設 Chat 模型。變更即時儲存。
          </p>
          <div className="space-y-3">
            {(modelTypeFilter === 'chat' ? CHAT_PROFILES : MULTIMODAL_PROFILES).map(({ key, label, description }) => {
              const options: EnabledModel[] = modelTypeFilter === 'multimodal' ? enabledMultimodalModels : enabledChatModels;
              return (
                <div key={key} className="flex items-center gap-3 p-3 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800">
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium text-gray-900 dark:text-gray-100">{label}</div>
                    <div className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{description}</div>
                  </div>
                  <select
                    value={profileMap[key] || ''}
                    onChange={(e) => {
                      const updated = { ...profileMap, [key]: e.target.value };
                      if (!e.target.value) delete updated[key];
                      saveProfileMap(updated);
                    }}
                    disabled={profileSaving}
                    className="w-56 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md text-sm
                               focus:outline-none focus:ring-2 focus:ring-accent/50 dark:focus:ring-gray-500
                               bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 disabled:opacity-50"
                  >
                    <option value="">預設: 系統 Chat 模型</option>
                    {options.map(m => (
                      <option key={m.model_name} value={m.model_name}>
                        {m.display_name || m.model_name}
                      </option>
                    ))}
                  </select>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* ── Chat / Embedding / Multimodal model list body ──────────────── */}
      {modelTypeFilter !== 'tool-calling' && subTab === 'models' && selectedProvider !== '__runtime_cli__' && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 flex-1 min-h-0">
          {/* Left: scrollable model list */}
          <div className="lg:col-span-5 lg:border-r border-gray-200 dark:border-gray-700 lg:pr-4 flex flex-col min-h-0">
            <div className="space-y-2 flex-1 overflow-y-auto overflow-x-hidden min-h-0 pr-2">
              {filteredModels.length === 0 ? (
                <div className="text-center py-8 text-sm text-gray-400 dark:text-gray-500">
                  {searchQuery
                    ? (t('noMatchingModels' as any) || 'No matching models')
                    : (t('noModelsInCategory' as any) || 'No models in this category')}
                </div>
              ) : (
                filteredModels.map((model) => {
                  const isSelected = selectedModel?.id === model.id;
                  const isHovered = hoveredModelId === model.id && !isSelected;
                  const cardClasses = `
                      p-3 rounded-lg border cursor-pointer transition-colors
                      ${isSelected
                      ? 'bg-accent-10 dark:bg-purple-900/20 border-accent/30 dark:border-purple-700'
                      : isHovered
                        ? 'bg-tertiary dark:hover:bg-gray-700 border-default dark:border-gray-700'
                        : 'bg-surface-secondary dark:bg-gray-800 border-default dark:border-gray-700'
                    }
                    `;

                  return (
                    <div
                      key={model.id}
                      data-model-id={model.id}
                      className={cardClasses}
                      onClick={() => setSelectedModel(model)}
                      onMouseEnter={(e) => {
                        e.stopPropagation();
                        if (!isSelected) {
                          setHoveredModelId(model.id);
                        }
                      }}
                      onMouseLeave={(e) => {
                        e.stopPropagation();
                        setHoveredModelId(null);
                      }}
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          {model.icon && <span className="text-lg">{model.icon}</span>}
                          <div>
                            <div className="font-medium text-sm text-gray-900 dark:text-gray-100">
                              {model.display_name}
                            </div>
                            <div className="text-xs text-gray-500 dark:text-gray-400">
                              {model.provider}
                              {model.model_type === 'embedding' && model.dimensions && (
                                <span> • {model.dimensions}d</span>
                              )}
                            </div>
                          </div>
                        </div>
                        <label className="relative inline-flex items-center cursor-pointer">
                          <input
                            type="checkbox"
                            checked={model.enabled}
                            disabled={togglingModels.has(String(model.id))}
                            onChange={(e) => {
                              e.stopPropagation();
                              toggleModel(String(model.id), e.target.checked);
                            }}
                            className="sr-only peer"
                          />
                          <div className={`w-11 h-6 bg-gray-300 dark:bg-gray-600 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-accent/30 dark:peer-focus:ring-purple-600 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 dark:after:border-gray-600 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-accent dark:peer-checked:bg-purple-700/80 ${togglingModels.has(String(model.id)) ? 'opacity-50 cursor-wait' : ''}`}></div>
                        </label>
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>

          {/* Right: config card */}
          <div className="lg:col-span-7 lg:pl-4 flex flex-col min-h-0">
            <div className="flex-1 overflow-y-auto overflow-x-hidden min-h-0 pr-2">
              {configCard ? (
                <div className="space-y-4">
                  <ModelConfigCard
                    card={configCard}
                    onConfigSaved={handleConfigSaved}
                    pullState={activePulls[String(selectedModel?.id)] || null}
                    onPullModel={handlePullModel}
                    onCancelPull={handleCancelPull}
                    onRemoveModel={handleRemoveModel}
                  />

                  {/* Embedding-specific: test connection */}
                  {modelTypeFilter === 'embedding' && selectedModel?.enabled && (
                    <div className="border-t border-gray-200 dark:border-gray-700 pt-4">
                      <div className="flex items-center gap-3">
                        <button
                          onClick={testEmbeddingConnection}
                          disabled={embeddingTesting}
                          className="px-4 py-2 text-sm bg-accent dark:bg-blue-700 text-white rounded-md hover:bg-accent/90 dark:hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                        >
                          {embeddingTesting
                            ? (t('testing' as any) || 'Testing...')
                            : (t('testConnection' as any) || 'Test Connection')}
                        </button>
                      </div>
                      {embeddingTestResult && (
                        <div className={`mt-3 p-3 rounded-md text-sm ${embeddingTestResult.toLowerCase().includes('success')
                          ? 'bg-green-50 dark:bg-green-900/20 text-green-800 dark:text-green-300 border border-green-200 dark:border-green-800'
                          : 'bg-red-50 dark:bg-red-900/20 text-red-800 dark:text-red-300 border border-red-200 dark:border-red-800'
                          }`}>
                          {embeddingTestResult}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ) : (
                <div className="flex items-center justify-center py-16 text-gray-400 dark:text-gray-500 text-sm">
                  {selectedModel && !selectedModel.enabled
                    ? t('enableModelToConfigure' as any) || 'Please enable the model to view configuration'
                    : t('selectModelToConfigure' as any) || 'Select an enabled model to view configuration'}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
      {/* ══════ HF Discovery Modal ══════ */}
      {showAddModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
          <div className="bg-white dark:bg-gray-800 rounded-xl shadow-2xl w-[560px] max-h-[80vh] flex flex-col border border-gray-200 dark:border-gray-700">
            {/* Header */}
            <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200 dark:border-gray-700">
              <h3 className="text-base font-semibold text-gray-900 dark:text-gray-100">🤗 新增 HuggingFace 模型</h3>
              <button onClick={() => setShowAddModal(false)} className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 text-lg">✕</button>
            </div>

            {/* Body */}
            <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
              {/* Model type selector */}
              <div className="flex items-center gap-2">
                <span className="text-xs text-gray-500 dark:text-gray-400 whitespace-nowrap">類型:</span>
                {(['chat', 'multimodal', 'embedding'] as const).map(mt => (
                  <button key={mt} onClick={() => setAddModelType(mt)}
                    className={`px-2.5 py-1 text-xs rounded-md border transition-colors ${
                      addModelType === mt
                        ? 'bg-accent text-white border-accent'
                        : 'bg-white dark:bg-gray-700 text-gray-600 dark:text-gray-300 border-gray-300 dark:border-gray-600 hover:border-accent/50'
                    }`}
                  >
                    {mt === 'chat' ? '💬 Chat' : mt === 'multimodal' ? '👁️ Multimodal' : '📐 Embedding'}
                  </button>
                ))}
              </div>

              {/* Search bar */}
              <div className="flex gap-2">
                <input
                  type="text" placeholder="搜尋 HF 模型（如 Qwen, Llama, Mistral...）"
                  value={hfSearchQuery} onChange={e => setHfSearchQuery(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter') searchHF(); }}
                  className="flex-1 px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-accent/50"
                />
                <button onClick={searchHF} disabled={hfLoading}
                  className="px-4 py-2 text-sm font-medium rounded-md bg-accent text-white hover:opacity-90 disabled:opacity-50 transition-opacity">
                  {hfLoading ? '搜尋中...' : '搜尋'}
                </button>
              </div>

              {/* Manual repo ID */}
              <div className="flex gap-2">
                <input
                  type="text" placeholder="或直接輸入 Repo ID（如 Qwen/Qwen2-VL-9B-Instruct）"
                  value={customRepoId} onChange={e => setCustomRepoId(e.target.value)}
                  className="flex-1 px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-accent/50"
                />
                <button onClick={registerCustomId} disabled={!customRepoId.trim() || hfRegistering === customRepoId}
                  className="px-4 py-2 text-sm font-medium rounded-md bg-green-600 text-white hover:bg-green-700 disabled:opacity-50 transition-colors">
                  {hfRegistering === customRepoId ? '註冊中...' : '直接註冊'}
                </button>
              </div>

              {/* Results */}
              {hfResults.length > 0 && (
                <div className="space-y-2">
                  <p className="text-xs text-gray-500 dark:text-gray-400">找到 {hfResults.length} 個模型：</p>
                  {hfResults.map(r => (
                    <div key={r.model_id} className="flex items-center justify-between p-3 rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900/50 hover:border-accent/40 transition-colors">
                      <div className="flex-1 min-w-0">
                        <div className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">{r.model_id}</div>
                        <div className="flex items-center gap-3 mt-0.5">
                          <span className="text-xs text-gray-500">⬇ {(r.downloads / 1000).toFixed(0)}K</span>
                          <span className="text-xs text-gray-500">❤ {r.likes}</span>
                          <span className={`text-xs px-1.5 py-0.5 rounded ${
                            r.model_type === 'multimodal' ? 'bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300'
                            : r.model_type === 'embedding' ? 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300'
                            : 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300'
                          }`}>{r.model_type}</span>
                        </div>
                      </div>
                      <button
                        onClick={() => registerModel(r.model_id, r.model_type)}
                        disabled={hfRegistering === r.model_id}
                        className="ml-3 px-3 py-1.5 text-xs font-medium rounded-md bg-accent text-white hover:opacity-90 disabled:opacity-50 transition-opacity whitespace-nowrap"
                      >
                        {hfRegistering === r.model_id ? '註冊中...' : '＋ 加入'}
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
