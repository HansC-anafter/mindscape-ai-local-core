'use client';

import React, { useEffect, useState } from 'react';
import { FolderSearch } from 'lucide-react';

import { settingsApi } from '@/app/settings/utils/settingsApi';
import { InlineAlert } from '@/app/settings/components/InlineAlert';

interface ComfyUIRuntimeConfigured {
  install_path?: string;
  main_py?: string;
  python_bin?: string;
  log_file?: string;
  extra_model_paths_config?: string;
  port?: number;
  health_host?: string;
  listen?: string;
}

interface ComfyUIRuntimeEffective extends ComfyUIRuntimeConfigured {
  health_url: string;
  install_path: string;
  main_py: string;
  python_bin: string;
  log_file: string;
  extra_model_paths_config: string;
  port: number;
  health_host: string;
  listen: string;
  install_path_configured: boolean;
  source_map: Record<string, string>;
}

interface ComfyUIRuntimeSettingsResponse {
  configured: ComfyUIRuntimeConfigured;
  effective: ComfyUIRuntimeEffective;
  install_path_configured: boolean;
}

interface HostValidationDetectedPath {
  path: string;
  source: string;
}

interface HostValidationResult {
  success: boolean;
  status: 'ready' | 'needs_overrides' | 'invalid';
  valid_access: boolean;
  is_probable_comfyui: boolean;
  install_path: string;
  checks: {
    requested_path: string;
    resolved_path: string;
    exists: boolean;
    is_directory: boolean;
    readable: boolean;
    writable: boolean;
    executable: boolean;
  };
  detected: {
    main_py: HostValidationDetectedPath;
    python_bin: HostValidationDetectedPath;
    extra_model_paths_config: HostValidationDetectedPath;
    log_file: HostValidationDetectedPath;
    models_dir: HostValidationDetectedPath;
    standard_layout_ready: boolean;
  };
  issues: string[];
  guidance: string[];
}

interface ChooseDirectoryResponse {
  path: string;
}

const defaultForm: ComfyUIRuntimeConfigured = {
  install_path: '',
  main_py: '',
  python_bin: '',
  log_file: '',
  extra_model_paths_config: '',
  port: 8188,
  health_host: '127.0.0.1',
  listen: '0.0.0.0',
};

const displayValue = (value?: string | number | null) => {
  if (value == null) {
    return '未設定';
  }
  const text = String(value).trim();
  return text || '未設定';
};

const truthyLabel = (value: boolean) => (value ? 'yes' : 'no');

export default function ComfyUIRuntimeSettingsPanel() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [clearing, setClearing] = useState(false);
  const [choosingDirectory, setChoosingDirectory] = useState(false);
  const [validatingPath, setValidatingPath] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [config, setConfig] = useState<ComfyUIRuntimeConfigured>(defaultForm);
  const [effective, setEffective] = useState<ComfyUIRuntimeEffective | null>(null);
  const [validationResult, setValidationResult] = useState<HostValidationResult | null>(null);

  useEffect(() => {
    void loadConfig();
  }, []);

  const loadConfig = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await settingsApi.get<ComfyUIRuntimeSettingsResponse>('/api/v1/capabilities/comfyui_runtime/runtime-config');
      setConfig({
        ...defaultForm,
        ...data.configured,
      });
      setEffective(data.effective);
      setValidationResult(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : '載入 ComfyUI runtime 設定失敗');
    } finally {
      setLoading(false);
    }
  };

  const applyValidationSuggestions = (
    path: string,
    result: HostValidationResult,
  ) => {
    setConfig((prev) => ({
      ...prev,
      install_path: path,
      main_py: prev.main_py?.trim() ? prev.main_py : result.detected.main_py.path,
      python_bin: prev.python_bin?.trim() ? prev.python_bin : result.detected.python_bin.path,
      extra_model_paths_config:
        prev.extra_model_paths_config?.trim()
          ? prev.extra_model_paths_config
          : result.detected.extra_model_paths_config.path,
      log_file: prev.log_file?.trim() ? prev.log_file : result.detected.log_file.path,
    }));
  };

  const validateHostPath = async (
    installPath: string,
    options?: { applySuggestions?: boolean; successMessage?: string },
  ) => {
    const trimmed = installPath.trim();
    if (!trimmed) {
      setError('請先輸入或選擇 ComfyUI 安裝路徑');
      return null;
    }

    try {
      setValidatingPath(true);
      setError(null);
      setSuccess(null);
      const result = await settingsApi.post<HostValidationResult>(
        '/api/v1/capabilities/comfyui_runtime/runtime-config/validate-host-path',
        { install_path: trimmed }
      );
      setValidationResult(result);

      if (options?.applySuggestions) {
        applyValidationSuggestions(trimmed, result);
      }

      if (result.status === 'ready') {
        setSuccess(options?.successMessage || '已驗證 host 路徑、權限與標準 ComfyUI 結構');
      } else if (result.status === 'needs_overrides') {
        setSuccess(options?.successMessage || 'host 路徑與權限可用，但仍需補 override');
      } else if (result.issues.length > 0) {
        setError(result.issues[0]);
      }

      return result;
    } catch (err) {
      setValidationResult(null);
      setError(err instanceof Error ? err.message : '驗證 ComfyUI host 路徑失敗');
      return null;
    } finally {
      setValidatingPath(false);
    }
  };

  const handleChooseInstallPath = async () => {
    try {
      setChoosingDirectory(true);
      setError(null);
      setSuccess(null);
      const result = await settingsApi.post<ChooseDirectoryResponse>(
        '/api/v1/system-settings/local-content/choose-directory'
      );
      const chosenPath = result.path?.trim();
      if (!chosenPath) {
        return;
      }

      setConfig((prev) => ({ ...prev, install_path: chosenPath }));
      await validateHostPath(chosenPath, {
        applySuggestions: true,
        successMessage: '已從 host 選擇目錄並完成權限驗證',
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : '無法開啟 host 目錄選擇器');
    } finally {
      setChoosingDirectory(false);
    }
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!config.install_path?.trim()) {
      setError('ComfyUI 安裝路徑不能為空');
      return;
    }

    try {
      setSaving(true);
      setError(null);
      setSuccess(null);
      const response = await settingsApi.put<ComfyUIRuntimeSettingsResponse & { success: boolean; message: string }>(
        '/api/v1/capabilities/comfyui_runtime/runtime-config',
        {
          install_path: config.install_path,
          main_py: config.main_py || '',
          python_bin: config.python_bin || '',
          log_file: config.log_file || '',
          extra_model_paths_config: config.extra_model_paths_config || '',
          port: config.port,
          health_host: config.health_host || '',
          listen: config.listen || '',
        }
      );
      setEffective(response.effective);
      setConfig({
        ...defaultForm,
        ...response.configured,
      });
      setSuccess(response.message || 'ComfyUI runtime 設定已儲存');
    } catch (err) {
      setError(err instanceof Error ? err.message : '儲存 ComfyUI runtime 設定失敗');
    } finally {
      setSaving(false);
    }
  };

  const handleClear = async () => {
    try {
      setClearing(true);
      setError(null);
      setSuccess(null);
      const response = await settingsApi.put<ComfyUIRuntimeSettingsResponse & { success: boolean; message: string }>(
        '/api/v1/capabilities/comfyui_runtime/runtime-config',
        { clear: true }
      );
      setConfig(defaultForm);
      setEffective(response.effective);
      setValidationResult(null);
      setSuccess(response.message || 'ComfyUI runtime 設定已清除');
    } catch (err) {
      setError(err instanceof Error ? err.message : '清除 ComfyUI runtime 設定失敗');
    } finally {
      setClearing(false);
    }
  };

  const inputClass =
    'w-full rounded-md border border-default dark:border-gray-600 bg-surface-accent dark:bg-gray-900 px-3 py-2 text-sm text-primary dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-gray-500';

  if (loading) {
    return <div className="text-center py-4 text-sm text-gray-500 dark:text-gray-400">載入中...</div>;
  }

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100 mb-2">
          ComfyUI Local Runtime
        </h3>
        <p className="text-sm text-gray-600 dark:text-gray-400">
          這裡管理的是 host 上的 ComfyUI 安裝點。請用本機目錄選擇器授權路徑，再驗證讀寫權限與可推導的 ComfyUI 結構；不再保留任何機器特定硬編碼 fallback。
        </p>
      </div>

      {error && <InlineAlert type="error" message={error} onDismiss={() => setError(null)} />}
      {success && <InlineAlert type="success" message={success} onDismiss={() => setSuccess(null)} />}

      <div className="rounded-lg border border-default dark:border-gray-700 bg-surface-secondary dark:bg-gray-800 p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="text-sm font-medium text-primary dark:text-gray-100">目前生效設定</div>
            <div className="mt-1 text-xs text-secondary dark:text-gray-400">
              {effective?.install_path_configured
                ? '已指定 host 安裝路徑'
                : '尚未指定。install_path 不會再退回任何硬編碼路徑。'}
            </div>
          </div>
          <span
            className={`inline-flex items-center rounded-full px-3 py-1 text-xs font-medium ${
              effective?.install_path_configured
                ? 'bg-green-50 text-green-700 border border-green-200 dark:bg-green-900/20 dark:text-green-300 dark:border-green-800'
                : 'bg-yellow-50 text-yellow-700 border border-yellow-200 dark:bg-yellow-900/20 dark:text-yellow-300 dark:border-yellow-800'
            }`}
          >
            {effective?.install_path_configured ? '已設定' : '未設定'}
          </span>
        </div>

        {effective && (
          <div className="mt-4 grid gap-3 text-xs text-secondary dark:text-gray-400 md:grid-cols-2">
            <div>
              <div className="font-medium text-primary dark:text-gray-200">install_path</div>
              <div className="mt-1 break-all">{displayValue(effective.install_path)}</div>
              <div className="mt-1 opacity-75">source: {effective.source_map.install_path}</div>
            </div>
            <div>
              <div className="font-medium text-primary dark:text-gray-200">health_url</div>
              <div className="mt-1 break-all">{displayValue(effective.health_url)}</div>
            </div>
            <div>
              <div className="font-medium text-primary dark:text-gray-200">main.py</div>
              <div className="mt-1 break-all">{displayValue(effective.main_py)}</div>
              <div className="mt-1 opacity-75">source: {effective.source_map.main_py}</div>
            </div>
            <div>
              <div className="font-medium text-primary dark:text-gray-200">Python</div>
              <div className="mt-1 break-all">{displayValue(effective.python_bin)}</div>
              <div className="mt-1 opacity-75">source: {effective.source_map.python_bin}</div>
            </div>
          </div>
        )}
      </div>

      <form onSubmit={handleSave} className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-primary dark:text-gray-300 mb-2">
            ComfyUI 安裝路徑
          </label>
          <div className="flex gap-2">
            <div className="relative flex-1">
              <input
                type="text"
                value={config.install_path || ''}
                onChange={(e) => setConfig((prev) => ({ ...prev, install_path: e.target.value }))}
                placeholder="/path/to/ComfyUI"
                className={`${inputClass} pr-10`}
              />
              <button
                type="button"
                onClick={handleChooseInstallPath}
                disabled={choosingDirectory}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-700 dark:hover:text-gray-300 p-1 disabled:opacity-50"
                title="從 host 選擇資料夾"
              >
                <FolderSearch size={18} />
              </button>
            </div>
            <button
              type="button"
              onClick={() => void validateHostPath(config.install_path || '', { applySuggestions: true })}
              disabled={validatingPath}
              className="rounded-md bg-gray-700 px-4 py-2 text-sm font-medium text-white hover:bg-gray-800 disabled:opacity-50"
            >
              {validatingPath ? '驗證中...' : '驗證權限'}
            </button>
          </div>
          <p className="mt-2 text-xs text-secondary dark:text-gray-400">
            目錄按鈕會直接呼叫 host Finder 選擇器。這裡驗證的是 host 實際存在、是否可讀寫，以及能否推導出標準 ComfyUI 路徑，不是容器內假掃描。
          </p>
        </div>

        {validationResult && (
          <div
            className={`rounded-lg border p-4 text-sm ${
              validationResult.status === 'ready'
                ? 'border-green-200 bg-green-50 text-green-700 dark:border-green-800 dark:bg-green-900/20 dark:text-green-300'
                : validationResult.status === 'needs_overrides'
                  ? 'border-yellow-200 bg-yellow-50 text-yellow-700 dark:border-yellow-800 dark:bg-yellow-900/20 dark:text-yellow-300'
                  : 'border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300'
            }`}
          >
            <div className="font-medium">
              {validationResult.status === 'ready'
                ? 'host 路徑已通過驗證'
                : validationResult.status === 'needs_overrides'
                  ? 'host 路徑可用，但需要補 override'
                  : 'host 路徑驗證失敗'}
            </div>
            <div className="mt-2 grid gap-2 text-xs md:grid-cols-2">
              <div>exists: {truthyLabel(validationResult.checks.exists)}</div>
              <div>is_directory: {truthyLabel(validationResult.checks.is_directory)}</div>
              <div>readable: {truthyLabel(validationResult.checks.readable)}</div>
              <div>writable: {truthyLabel(validationResult.checks.writable)}</div>
            </div>
            <div className="mt-3 grid gap-2 text-xs md:grid-cols-2">
              <div>
                <div className="font-medium">detected main.py</div>
                <div className="break-all">{displayValue(validationResult.detected.main_py.path)}</div>
                <div className="opacity-75">source: {validationResult.detected.main_py.source}</div>
              </div>
              <div>
                <div className="font-medium">detected Python</div>
                <div className="break-all">{displayValue(validationResult.detected.python_bin.path)}</div>
                <div className="opacity-75">source: {validationResult.detected.python_bin.source}</div>
              </div>
            </div>
            {validationResult.issues.length > 0 && (
              <div className="mt-3 space-y-1 text-xs">
                {validationResult.issues.map((issue) => (
                  <div key={issue}>- {issue}</div>
                ))}
              </div>
            )}
            {validationResult.guidance.length > 0 && (
              <div className="mt-3 space-y-1 text-xs opacity-90">
                {validationResult.guidance.map((item) => (
                  <div key={item}>- {item}</div>
                ))}
              </div>
            )}
          </div>
        )}

        <div className="grid gap-4 md:grid-cols-2">
          <div>
            <label className="block text-sm font-medium text-primary dark:text-gray-300 mb-2">main.py override</label>
            <input
              type="text"
              value={config.main_py || ''}
              onChange={(e) => setConfig((prev) => ({ ...prev, main_py: e.target.value }))}
              placeholder="可留空，自動推導"
              className={inputClass}
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-primary dark:text-gray-300 mb-2">Python binary override</label>
            <input
              type="text"
              value={config.python_bin || ''}
              onChange={(e) => setConfig((prev) => ({ ...prev, python_bin: e.target.value }))}
              placeholder="可留空，自動推導"
              className={inputClass}
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-primary dark:text-gray-300 mb-2">extra_model_paths.yaml override</label>
            <input
              type="text"
              value={config.extra_model_paths_config || ''}
              onChange={(e) => setConfig((prev) => ({ ...prev, extra_model_paths_config: e.target.value }))}
              placeholder="可留空，自動推導"
              className={inputClass}
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-primary dark:text-gray-300 mb-2">Log file override</label>
            <input
              type="text"
              value={config.log_file || ''}
              onChange={(e) => setConfig((prev) => ({ ...prev, log_file: e.target.value }))}
              placeholder="可留空，自動推導"
              className={inputClass}
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-primary dark:text-gray-300 mb-2">Health host</label>
            <input
              type="text"
              value={config.health_host || ''}
              onChange={(e) => setConfig((prev) => ({ ...prev, health_host: e.target.value }))}
              className={inputClass}
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-primary dark:text-gray-300 mb-2">Listen host</label>
            <input
              type="text"
              value={config.listen || ''}
              onChange={(e) => setConfig((prev) => ({ ...prev, listen: e.target.value }))}
              className={inputClass}
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-primary dark:text-gray-300 mb-2">Port</label>
            <input
              type="number"
              min={1}
              max={65535}
              value={config.port ?? 8188}
              onChange={(e) => setConfig((prev) => ({ ...prev, port: Number(e.target.value || 8188) }))}
              className={inputClass}
            />
          </div>
        </div>

        <div className="flex items-center gap-3">
          <button
            type="submit"
            disabled={saving}
            className="px-4 py-2 bg-gray-700 text-white rounded-md hover:bg-gray-800 disabled:opacity-50"
          >
            {saving ? '儲存中...' : '儲存設定'}
          </button>
          <button
            type="button"
            onClick={handleClear}
            disabled={clearing}
            className="px-4 py-2 border border-default dark:border-gray-600 rounded-md text-primary dark:text-gray-200 hover:bg-surface-accent dark:hover:bg-gray-700 disabled:opacity-50"
          >
            {clearing ? '清除中...' : '清除 override'}
          </button>
        </div>
      </form>
    </div>
  );
}
