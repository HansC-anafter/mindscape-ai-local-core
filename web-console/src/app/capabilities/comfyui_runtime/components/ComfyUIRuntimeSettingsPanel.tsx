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
  talking_head_backend_preset?: string;
  talking_head_backend_repo?: string;
  talking_head_backend_family?: string;
  talking_head_backend_ref?: string;
  talking_head_backend_dir?: string;
  talking_head_viseme_bridge_repo?: string;
  talking_head_viseme_bridge_ref?: string;
  talking_head_viseme_bridge_dir?: string;
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
  talking_head_source_install?: TalkingHeadSourceInstallSummary;
}

interface TalkingHeadSourceInstallSummary {
  preset_id: string;
  backend_family: string;
  supports_auto_install: boolean;
  backend_contract_verification_mode?: string;
  declared_runtime_install_specs?: string[];
  declared_node_classes?: string[];
  default_backend_repo?: string;
  default_backend_ref?: string;
  default_viseme_bridge_repo?: string;
  default_viseme_bridge_ref?: string;
  resolved_backend_repo?: string;
  resolved_backend_repo_source?: string;
  resolved_viseme_bridge_repo?: string;
  resolved_viseme_bridge_repo_source?: string;
  resolved_backend_dir?: string;
  resolved_viseme_bridge_dir?: string;
  configuration_state: string;
  configuration_blockers: string[];
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

interface TalkingHeadBackendPresetOption {
  preset_id: string;
  display_name: string;
  description?: string;
  backend_family?: string;
  supports_auto_install?: boolean;
  contract_verification_mode?: string;
  declared_runtime_install_specs?: string[];
  declared_node_classes?: string[];
  default_backend_repo?: string;
  default_backend_ref?: string;
  default_viseme_repo?: string;
  default_viseme_ref?: string;
}

interface TalkingHeadBackendPresetsResponse {
  default_preset_id: string;
  presets: TalkingHeadBackendPresetOption[];
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
  talking_head_backend_preset: 'liveportrait_manual_bootstrap',
  talking_head_backend_repo: '',
  talking_head_backend_family: 'liveportrait_style_audio_driven_custom_nodes',
  talking_head_backend_ref: 'main',
  talking_head_backend_dir: '',
  talking_head_viseme_bridge_repo: '',
  talking_head_viseme_bridge_ref: 'main',
  talking_head_viseme_bridge_dir: '',
};

const displayValue = (value?: string | number | null) => {
  if (value == null) {
    return 'Not set';
  }
  const text = String(value).trim();
  return text || 'Not set';
};

const truthyLabel = (value: boolean) => (value ? 'yes' : 'no');

const deriveTalkingHeadDir = (installPath: string, dirName: string) => {
  const normalized = installPath.trim().replace(/\/+$/, '');
  if (!normalized) {
    return '';
  }
  return `${normalized}/custom_nodes/${dirName}`;
};

const FALLBACK_TALKING_HEAD_PRESET_OPTIONS: TalkingHeadBackendPresetOption[] = [
  {
    preset_id: 'liveportrait_manual_bootstrap',
    display_name: 'LivePortrait Manual Bootstrap',
    backend_family: 'liveportrait_style_audio_driven_custom_nodes',
  },
  {
    preset_id: 'custom_source_install',
    display_name: 'Custom Source Install',
    backend_family: 'custom_audio_driven_talking_head_runtime',
  },
  {
    preset_id: 'manual_existing_nodes',
    display_name: 'Manual Existing Nodes',
    backend_family: 'manual_existing_nodes',
  },
];

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
  const [presetOptions, setPresetOptions] = useState<TalkingHeadBackendPresetOption[]>(FALLBACK_TALKING_HEAD_PRESET_OPTIONS);

  useEffect(() => {
    void loadConfig();
  }, []);

  const loadConfig = async () => {
    try {
      setLoading(true);
      setError(null);
      const [data, presetsPayload] = await Promise.all([
        settingsApi.get<ComfyUIRuntimeSettingsResponse>('/api/v1/capabilities/comfyui_runtime/runtime-config'),
        settingsApi.get<TalkingHeadBackendPresetsResponse>('/api/v1/capabilities/comfyui_runtime/talking-head/backend-presets').catch(
          () => ({
            default_preset_id: defaultForm.talking_head_backend_preset || 'liveportrait_manual_bootstrap',
            presets: FALLBACK_TALKING_HEAD_PRESET_OPTIONS,
          }),
        ),
      ]);
      setConfig({
        ...defaultForm,
        ...data.configured,
      });
      setEffective(data.effective);
      setPresetOptions(presetsPayload.presets?.length ? presetsPayload.presets : FALLBACK_TALKING_HEAD_PRESET_OPTIONS);
      setValidationResult(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load ComfyUI runtime settings');
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
      talking_head_backend_dir:
        prev.talking_head_backend_dir?.trim()
          ? prev.talking_head_backend_dir
          : deriveTalkingHeadDir(path, 'mindscape_liveportrait_audio_runtime'),
      talking_head_viseme_bridge_dir:
        prev.talking_head_viseme_bridge_dir?.trim()
          ? prev.talking_head_viseme_bridge_dir
          : deriveTalkingHeadDir(path, 'mindscape_viseme_alignment_bridge'),
    }));
  };

  const validateHostPath = async (
    installPath: string,
    options?: { applySuggestions?: boolean; successMessage?: string },
  ) => {
    const trimmed = installPath.trim();
    if (!trimmed) {
      setError('Enter or choose the ComfyUI install path first');
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
        setSuccess(options?.successMessage || 'Host path, permissions, and standard ComfyUI structure verified');
      } else if (result.status === 'needs_overrides') {
        setSuccess(options?.successMessage || 'Host path and permissions are usable, but overrides are still required');
      } else if (result.issues.length > 0) {
        setError(result.issues[0]);
      }

      return result;
    } catch (err) {
      setValidationResult(null);
      setError(err instanceof Error ? err.message : 'Failed to validate ComfyUI host path');
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
        successMessage: 'Host directory selected and permissions verified',
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to open host directory picker');
    } finally {
      setChoosingDirectory(false);
    }
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!config.install_path?.trim()) {
      setError('ComfyUI install path cannot be empty');
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
          talking_head_backend_preset: config.talking_head_backend_preset || '',
          talking_head_backend_repo: config.talking_head_backend_repo || '',
          talking_head_backend_family: config.talking_head_backend_family || '',
          talking_head_backend_ref: config.talking_head_backend_ref || '',
          talking_head_backend_dir: config.talking_head_backend_dir || '',
          talking_head_viseme_bridge_repo: config.talking_head_viseme_bridge_repo || '',
          talking_head_viseme_bridge_ref: config.talking_head_viseme_bridge_ref || '',
          talking_head_viseme_bridge_dir: config.talking_head_viseme_bridge_dir || '',
        }
      );
      setEffective(response.effective);
      setConfig({
        ...defaultForm,
        ...response.configured,
      });
      setSuccess(response.message || 'ComfyUI runtime settings saved');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save ComfyUI runtime settings');
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
      setSuccess(response.message || 'ComfyUI runtime settings cleared');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to clear ComfyUI runtime settings');
    } finally {
      setClearing(false);
    }
  };

  const inputClass =
    'w-full rounded-md border border-default dark:border-gray-600 bg-surface-accent dark:bg-gray-900 px-3 py-2 text-sm text-primary dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-gray-500';
  const selectedPreset =
    presetOptions.find((option) => option.preset_id === (config.talking_head_backend_preset || ''))
    || presetOptions[0]
    || null;
  const effectiveTalkingHeadSourceInstall = effective?.talking_head_source_install || null;

  if (loading) {
    return <div className="text-center py-4 text-sm text-gray-500 dark:text-gray-400">Loading...</div>;
  }

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100 mb-2">
          ComfyUI Local Runtime
        </h3>
        <p className="text-sm text-gray-600 dark:text-gray-400">
          This panel manages the ComfyUI install point on the host. Use the local directory picker to grant path access, then validate read/write permissions and the derived ComfyUI structure. Machine-specific hardcoded fallbacks are not retained.
        </p>
      </div>

      {error && <InlineAlert type="error" message={error} onDismiss={() => setError(null)} />}
      {success && <InlineAlert type="success" message={success} onDismiss={() => setSuccess(null)} />}

      <div className="rounded-lg border border-default dark:border-gray-700 bg-surface-secondary dark:bg-gray-800 p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="text-sm font-medium text-primary dark:text-gray-100">Effective Settings</div>
            <div className="mt-1 text-xs text-secondary dark:text-gray-400">
              {effective?.install_path_configured
                ? 'Host install path is configured'
                : 'Not configured. install_path no longer falls back to hardcoded paths.'}
            </div>
          </div>
          <span
            className={`inline-flex items-center rounded-full px-3 py-1 text-xs font-medium ${
              effective?.install_path_configured
                ? 'bg-green-50 text-green-700 border border-green-200 dark:bg-green-900/20 dark:text-green-300 dark:border-green-800'
                : 'bg-yellow-50 text-yellow-700 border border-yellow-200 dark:bg-yellow-900/20 dark:text-yellow-300 dark:border-yellow-800'
            }`}
          >
            {effective?.install_path_configured ? 'Configured' : 'Not set'}
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
            <div>
              <div className="font-medium text-primary dark:text-gray-200">Talking-head backend preset</div>
              <div className="mt-1 break-all">{displayValue(effective.talking_head_backend_preset)}</div>
              <div className="mt-1 opacity-75">source: {effective.source_map.talking_head_backend_preset}</div>
            </div>
            <div>
              <div className="font-medium text-primary dark:text-gray-200">Talking-head backend family</div>
              <div className="mt-1 break-all">{displayValue(effective.talking_head_backend_family)}</div>
              <div className="mt-1 opacity-75">source: {effective.source_map.talking_head_backend_family}</div>
            </div>
            <div>
              <div className="font-medium text-primary dark:text-gray-200">Talking-head backend repo</div>
              <div className="mt-1 break-all">{displayValue(effective.talking_head_backend_repo)}</div>
              <div className="mt-1 opacity-75">source: {effective.source_map.talking_head_backend_repo}</div>
            </div>
            <div>
              <div className="font-medium text-primary dark:text-gray-200">Talking-head backend dir</div>
              <div className="mt-1 break-all">{displayValue(effective.talking_head_backend_dir)}</div>
              <div className="mt-1 opacity-75">source: {effective.source_map.talking_head_backend_dir}</div>
            </div>
            <div>
              <div className="font-medium text-primary dark:text-gray-200">Viseme bridge repo</div>
              <div className="mt-1 break-all">{displayValue(effective.talking_head_viseme_bridge_repo)}</div>
              <div className="mt-1 opacity-75">source: {effective.source_map.talking_head_viseme_bridge_repo}</div>
            </div>
            <div>
              <div className="font-medium text-primary dark:text-gray-200">Viseme bridge dir</div>
              <div className="mt-1 break-all">{displayValue(effective.talking_head_viseme_bridge_dir)}</div>
              <div className="mt-1 opacity-75">source: {effective.source_map.talking_head_viseme_bridge_dir}</div>
            </div>
          </div>
        )}

        {effectiveTalkingHeadSourceInstall ? (
          <div className="mt-4 rounded-lg border border-default dark:border-gray-700 bg-surface-accent dark:bg-gray-900/40 p-4 text-xs text-secondary dark:text-gray-400">
            <div className="text-sm font-medium text-primary dark:text-gray-100">
              Talking-head source-install summary
            </div>
            <div className="mt-3 grid gap-3 md:grid-cols-2">
              <div>
                <div className="font-medium text-primary dark:text-gray-200">configuration_state</div>
                <div className="mt-1 break-all">{displayValue(effectiveTalkingHeadSourceInstall.configuration_state)}</div>
              </div>
              <div>
                <div className="font-medium text-primary dark:text-gray-200">supports_auto_install</div>
                <div className="mt-1">{truthyLabel(effectiveTalkingHeadSourceInstall.supports_auto_install)}</div>
              </div>
              <div>
                <div className="font-medium text-primary dark:text-gray-200">backend_contract_verification_mode</div>
                <div className="mt-1 break-all">{displayValue(effectiveTalkingHeadSourceInstall.backend_contract_verification_mode)}</div>
              </div>
              <div>
                <div className="font-medium text-primary dark:text-gray-200">resolved_backend_repo_source</div>
                <div className="mt-1 break-all">{displayValue(effectiveTalkingHeadSourceInstall.resolved_backend_repo_source)}</div>
              </div>
              <div>
                <div className="font-medium text-primary dark:text-gray-200">resolved_viseme_bridge_repo_source</div>
                <div className="mt-1 break-all">{displayValue(effectiveTalkingHeadSourceInstall.resolved_viseme_bridge_repo_source)}</div>
              </div>
              <div>
                <div className="font-medium text-primary dark:text-gray-200">default backend repo</div>
                <div className="mt-1 break-all">{displayValue(effectiveTalkingHeadSourceInstall.default_backend_repo)}</div>
                <div className="mt-1 opacity-75">ref: {displayValue(effectiveTalkingHeadSourceInstall.default_backend_ref)}</div>
              </div>
              <div>
                <div className="font-medium text-primary dark:text-gray-200">default viseme bridge repo</div>
                <div className="mt-1 break-all">{displayValue(effectiveTalkingHeadSourceInstall.default_viseme_bridge_repo)}</div>
                <div className="mt-1 opacity-75">ref: {displayValue(effectiveTalkingHeadSourceInstall.default_viseme_bridge_ref)}</div>
              </div>
            </div>
            <div className="mt-3">
              <div className="font-medium text-primary dark:text-gray-200">declared_runtime_install_specs</div>
              {(effectiveTalkingHeadSourceInstall.declared_runtime_install_specs || []).length ? (
                <div className="mt-1 space-y-1">
                  {(effectiveTalkingHeadSourceInstall.declared_runtime_install_specs || []).map((item) => (
                    <div key={item}>- {item}</div>
                  ))}
                </div>
              ) : (
                <div className="mt-1">None</div>
              )}
            </div>
            <div className="mt-3">
              <div className="font-medium text-primary dark:text-gray-200">declared_node_classes</div>
              {(effectiveTalkingHeadSourceInstall.declared_node_classes || []).length ? (
                <div className="mt-1 space-y-1">
                  {(effectiveTalkingHeadSourceInstall.declared_node_classes || []).map((item) => (
                    <div key={item}>- {item}</div>
                  ))}
                </div>
              ) : (
                <div className="mt-1">None</div>
              )}
            </div>
            <div className="mt-3">
              <div className="font-medium text-primary dark:text-gray-200">configuration_blockers</div>
              {effectiveTalkingHeadSourceInstall.configuration_blockers.length ? (
                <div className="mt-1 space-y-1">
                  {effectiveTalkingHeadSourceInstall.configuration_blockers.map((item) => (
                    <div key={item}>- {item}</div>
                  ))}
                </div>
              ) : (
                <div className="mt-1">None</div>
              )}
            </div>
          </div>
        ) : null}
      </div>

      <form onSubmit={handleSave} className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-primary dark:text-gray-300 mb-2">
            ComfyUI install path
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
                title="Choose folder from host"
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
              {validatingPath ? 'Validating...' : 'Validate permissions'}
            </button>
          </div>
          <p className="mt-2 text-xs text-secondary dark:text-gray-400">
            The directory button calls the host Finder picker directly. Validation checks the real host path, read/write access, and derivable standard ComfyUI paths, not a fake in-container scan.
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
                ? 'Host path validation passed'
                : validationResult.status === 'needs_overrides'
                  ? 'Host path is usable, but overrides are required'
                  : 'Host path validation failed'}
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
              placeholder="Optional, auto-derived"
              className={inputClass}
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-primary dark:text-gray-300 mb-2">Python binary override</label>
            <input
              type="text"
              value={config.python_bin || ''}
              onChange={(e) => setConfig((prev) => ({ ...prev, python_bin: e.target.value }))}
              placeholder="Optional, auto-derived"
              className={inputClass}
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-primary dark:text-gray-300 mb-2">extra_model_paths.yaml override</label>
            <input
              type="text"
              value={config.extra_model_paths_config || ''}
              onChange={(e) => setConfig((prev) => ({ ...prev, extra_model_paths_config: e.target.value }))}
              placeholder="Optional, auto-derived"
              className={inputClass}
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-primary dark:text-gray-300 mb-2">Log file override</label>
            <input
              type="text"
              value={config.log_file || ''}
              onChange={(e) => setConfig((prev) => ({ ...prev, log_file: e.target.value }))}
              placeholder="Optional, auto-derived"
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

        <div className="rounded-lg border border-default dark:border-gray-700 bg-surface-secondary dark:bg-gray-800 p-4">
          <div className="mb-3">
            <div className="text-sm font-medium text-primary dark:text-gray-100">Talking-head Source Install</div>
            <p className="mt-1 text-xs text-secondary dark:text-gray-400">
              These fields drive the talking-head runtime bootstrap directly. When the repo URL is empty, the system only checks the specified custom node directory and does not auto-clone.
            </p>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div>
              <label className="block text-sm font-medium text-primary dark:text-gray-300 mb-2">Backend preset</label>
              <select
                value={config.talking_head_backend_preset || 'liveportrait_manual_bootstrap'}
                onChange={(e) => {
                  const presetId = e.target.value;
                  const preset = presetOptions.find((item) => item.preset_id === presetId);
                  setConfig((prev) => ({
                    ...prev,
                    talking_head_backend_preset: presetId,
                    talking_head_backend_family: preset?.backend_family || prev.talking_head_backend_family,
                  }));
                }}
                className={inputClass}
              >
                {presetOptions.map((option) => (
                  <option key={option.preset_id} value={option.preset_id}>
                    {option.display_name}
                  </option>
                ))}
              </select>
              {selectedPreset ? (
                <div className="mt-2 rounded-md border border-default dark:border-gray-700 bg-surface-accent dark:bg-gray-900/40 p-3 text-xs text-secondary dark:text-gray-400">
                  <div>{selectedPreset.description || 'This preset provides the backend family and deployment-level default repo/ref.'}</div>
                  <div className="mt-2">supports_auto_install: {truthyLabel(Boolean(selectedPreset.supports_auto_install))}</div>
                  <div className="mt-1">contract verification mode: {displayValue(selectedPreset.contract_verification_mode)}</div>
                  <div className="mt-1 break-all">default backend repo: {displayValue(selectedPreset.default_backend_repo)}</div>
                  <div className="mt-1">default backend ref: {displayValue(selectedPreset.default_backend_ref)}</div>
                  <div className="mt-1 break-all">default viseme bridge repo: {displayValue(selectedPreset.default_viseme_repo)}</div>
                  <div className="mt-1">default viseme bridge ref: {displayValue(selectedPreset.default_viseme_ref)}</div>
                  <div className="mt-2">declared runtime specs:</div>
                  {(selectedPreset.declared_runtime_install_specs || []).length ? (
                    <div className="mt-1 space-y-1">
                      {(selectedPreset.declared_runtime_install_specs || []).map((item) => (
                        <div key={item}>- {item}</div>
                      ))}
                    </div>
                  ) : (
                    <div className="mt-1">None</div>
                  )}
                  <div className="mt-2">declared node classes:</div>
                  {(selectedPreset.declared_node_classes || []).length ? (
                    <div className="mt-1 space-y-1">
                      {(selectedPreset.declared_node_classes || []).map((item) => (
                        <div key={item}>- {item}</div>
                      ))}
                    </div>
                  ) : (
                    <div className="mt-1">None</div>
                  )}
                </div>
              ) : null}
            </div>
            <div>
              <label className="block text-sm font-medium text-primary dark:text-gray-300 mb-2">Backend family</label>
              <select
                value={config.talking_head_backend_family || 'liveportrait_style_audio_driven_custom_nodes'}
                onChange={(e) => setConfig((prev) => ({ ...prev, talking_head_backend_family: e.target.value }))}
                className={inputClass}
              >
                <option value="liveportrait_style_audio_driven_custom_nodes">LivePortrait-style source install</option>
                <option value="custom_audio_driven_talking_head_runtime">Custom source-install runtime</option>
                <option value="manual_existing_nodes">Manual existing nodes</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-primary dark:text-gray-300 mb-2">Backend repo URL</label>
              <input
                type="text"
                value={config.talking_head_backend_repo || ''}
                onChange={(e) => setConfig((prev) => ({ ...prev, talking_head_backend_repo: e.target.value }))}
                placeholder="https://github.com/.../liveportrait-runtime.git"
                className={inputClass}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-primary dark:text-gray-300 mb-2">Backend git ref</label>
              <input
                type="text"
                value={config.talking_head_backend_ref || ''}
                onChange={(e) => setConfig((prev) => ({ ...prev, talking_head_backend_ref: e.target.value }))}
                placeholder="main"
                className={inputClass}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-primary dark:text-gray-300 mb-2">Backend custom node dir</label>
              <input
                type="text"
                value={config.talking_head_backend_dir || ''}
                onChange={(e) => setConfig((prev) => ({ ...prev, talking_head_backend_dir: e.target.value }))}
                placeholder="Optional, auto-derived"
                className={inputClass}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-primary dark:text-gray-300 mb-2">Viseme bridge repo URL</label>
              <input
                type="text"
                value={config.talking_head_viseme_bridge_repo || ''}
                onChange={(e) => setConfig((prev) => ({ ...prev, talking_head_viseme_bridge_repo: e.target.value }))}
                placeholder="https://github.com/.../viseme-bridge.git"
                className={inputClass}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-primary dark:text-gray-300 mb-2">Viseme bridge git ref</label>
              <input
                type="text"
                value={config.talking_head_viseme_bridge_ref || ''}
                onChange={(e) => setConfig((prev) => ({ ...prev, talking_head_viseme_bridge_ref: e.target.value }))}
                placeholder="main"
                className={inputClass}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-primary dark:text-gray-300 mb-2">Viseme bridge custom node dir</label>
              <input
                type="text"
                value={config.talking_head_viseme_bridge_dir || ''}
                onChange={(e) => setConfig((prev) => ({ ...prev, talking_head_viseme_bridge_dir: e.target.value }))}
                placeholder="Optional, auto-derived"
                className={inputClass}
              />
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <button
            type="submit"
            disabled={saving}
            className="px-4 py-2 bg-gray-700 text-white rounded-md hover:bg-gray-800 disabled:opacity-50"
          >
            {saving ? 'Saving...' : 'Save settings'}
          </button>
          <button
            type="button"
            onClick={handleClear}
            disabled={clearing}
            className="px-4 py-2 border border-default dark:border-gray-600 rounded-md text-primary dark:text-gray-200 hover:bg-surface-accent dark:hover:bg-gray-700 disabled:opacity-50"
          >
            {clearing ? 'Clearing...' : 'Clear override'}
          </button>
        </div>
      </form>
    </div>
  );
}
