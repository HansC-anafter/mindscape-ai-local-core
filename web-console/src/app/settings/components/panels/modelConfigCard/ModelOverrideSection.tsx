'use client';

import { t } from '../../../../../lib/i18n';
import type { ModelOverrideSectionProps } from './types';

export function ModelOverrideSection({
  model,
  showModelOverride,
  saving,
  modelApiKey,
  modelBaseUrl,
  modelProjectId,
  modelLocation,
  runtimeEngine,
  temperature,
  maxOutputTokenSliderMax,
  effectiveMaxOutputTokens,
  defaultMaxTokens,
  localRuntimeMaxTokensCap,
  onToggleShowModelOverride,
  onSaveModelOverride,
  onModelApiKeyChange,
  onModelBaseUrlChange,
  onModelProjectIdChange,
  onModelLocationChange,
  onRuntimeEngineChange,
  onTemperatureChange,
  onMaxOutputTokensChange,
}: ModelOverrideSectionProps) {
  return (
    <div className="border-t border-gray-200 dark:border-gray-700 pt-4">
      <div className="flex items-center justify-between mb-3">
        <button
          onClick={onToggleShowModelOverride}
          className="flex items-center gap-2 text-sm font-medium text-gray-700 dark:text-gray-300 hover:text-gray-900 dark:hover:text-gray-100"
        >
          <span>{t('modelOverride' as any) || 'Model Override (Advanced)'}</span>
          <svg
            className={`w-4 h-4 transition-transform ${showModelOverride ? 'rotate-180' : ''}`}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </button>
        {showModelOverride && (
          <button
            onClick={onSaveModelOverride}
            disabled={saving}
            className="px-4 py-1.5 text-sm bg-purple-50 dark:bg-purple-900/20 text-purple-700 dark:text-purple-300 border border-purple-300 dark:border-purple-700 rounded-md hover:bg-purple-100 dark:hover:bg-purple-900/30 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {saving ? (t('saving' as any) || 'Saving...') : (t('saveModelOverride' as any) || 'Save Model Override')}
          </button>
        )}
      </div>

      {showModelOverride && (
        <div className="mt-3 space-y-3 pt-3 border-t border-gray-200 dark:border-gray-700">
          <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">
            {t('modelOverrideDescription' as any) || 'Override provider settings for this specific model (usually not needed)'}
          </p>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              {t('apiKey' as any)} ({t('override' as any) || 'Override'}){['ollama', 'llama-cpp', 'llamacpp', 'huggingface'].includes(model.provider) && <span className="text-gray-400 font-normal ml-1">({t('optional' as any) || 'Optional'})</span>}
            </label>
            <input
              type="password"
              value={modelApiKey}
              onChange={(event) => onModelApiKeyChange(event.target.value)}
              placeholder={t('enterApiKey' as any) || 'Enter API Key'}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
            />
          </div>

          {model.provider === 'ollama' && (
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                {t('baseUrl' as any) || 'Base URL'} ({t('override' as any) || 'Override'})
              </label>
              <input
                type="text"
                value={modelBaseUrl}
                onChange={(event) => onModelBaseUrlChange(event.target.value)}
                placeholder="http://localhost:11434"
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
              />
            </div>
          )}

          {model.provider === 'vertex-ai' && (
            <>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  {t('gcpProjectId' as any)} ({t('override' as any) || 'Override'})
                </label>
                <input
                  type="text"
                  value={modelProjectId}
                  onChange={(event) => onModelProjectIdChange(event.target.value)}
                  placeholder="your-project-id"
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  {t('location' as any) || 'Location'} ({t('override' as any) || 'Override'})
                </label>
                <input
                  type="text"
                  value={modelLocation}
                  onChange={(event) => onModelLocationChange(event.target.value)}
                  placeholder="us-central1"
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                />
              </div>
            </>
          )}

          {['huggingface', 'ollama'].includes(model.provider) && (
            <div className="mt-4 pt-4 border-t border-gray-200 dark:border-gray-700">
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                {t('runtimeEngineOverride' as any) || 'Runtime Engine Override'}
              </label>
              <select
                value={runtimeEngine}
                onChange={(event) => onRuntimeEngineChange(event.target.value)}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-purple-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
              >
                <option value="auto">Auto (Default Detection)</option>
                <option value="mlx">MLX Local Server (Apple Silicon)</option>
                <option value="llama-cpp">Llama.cpp</option>
                <option value="huggingface">HuggingFace Transformers</option>
              </select>
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                Force the execution engine for this model. Essential if downloading MLX/GGUF models via HF.
              </p>
            </div>
          )}

          <div className="mt-4 pt-4 border-t border-gray-200 dark:border-gray-700">
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              {t('temperature' as any) || 'Temperature'}
            </label>
            <div className="flex items-center gap-3">
              <input
                type="range"
                min={0.0}
                max={2.0}
                step={0.1}
                value={temperature}
                onChange={(event) => onTemperatureChange(Number(event.target.value))}
                className="flex-1 h-2 bg-gray-200 dark:bg-gray-700 rounded-lg appearance-none cursor-pointer accent-purple-500"
              />
              <span className="text-sm font-mono text-gray-700 dark:text-gray-300 min-w-[3rem] text-right">
                {temperature.toFixed(1)}
              </span>
            </div>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
              Controls randomness: Lowering results in less random completions.
            </p>
          </div>

          <div className="mt-4 pt-4 border-t border-gray-200 dark:border-gray-700">
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              {t('maxOutputTokens' as any) || 'Max Output Tokens'}
            </label>
            <div className="flex items-center gap-3">
              <input
                type="range"
                min={256}
                max={maxOutputTokenSliderMax}
                step={256}
                value={effectiveMaxOutputTokens}
                onChange={(event) => onMaxOutputTokensChange(Math.min(Number(event.target.value), maxOutputTokenSliderMax))}
                className="flex-1 h-2 bg-gray-200 dark:bg-gray-700 rounded-lg appearance-none cursor-pointer accent-purple-500"
              />
              <span className="text-sm font-mono text-gray-700 dark:text-gray-300 min-w-[5rem] text-right">
                {effectiveMaxOutputTokens.toLocaleString()}
              </span>
            </div>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
              {localRuntimeMaxTokensCap
                ? (t('maxOutputTokensLocalMlxCapHint' as any) || 'Upstream default: {default}. Local MLX stable cap: {cap}; the runtime clamps higher values to avoid server instability.')
                  .replace('{default}', defaultMaxTokens.toLocaleString())
                  .replace('{cap}', localRuntimeMaxTokensCap.toLocaleString())
                : (t('maxOutputTokensHint' as any) || 'Default: {default}. Set higher for thinking models.').replace('{default}', defaultMaxTokens.toLocaleString())}
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
