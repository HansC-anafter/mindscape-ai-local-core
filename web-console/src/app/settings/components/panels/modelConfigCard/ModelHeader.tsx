'use client';

import { t } from '../../../../../lib/i18n';
import type { ModelHeaderProps } from './types';

export function ModelHeader({ model, pullStatus, onRemoveModel }: ModelHeaderProps) {
  return (
    <div className="flex items-center gap-3 pt-4 border-t border-gray-200 dark:border-gray-700">
      {model.icon && <span className="text-2xl">{model.icon}</span>}
      <div className="flex-1">
        <div className="flex items-center gap-2">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 flex items-center gap-2">
            {model.display_name}
            {model.enabled && ['ollama', 'huggingface', 'llama-cpp'].includes(model.provider) && (!pullStatus || !['pulling', 'starting', 'processing'].includes(pullStatus)) && (
              <span className="px-2 py-0.5 text-[10px] font-medium rounded-full bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400 border border-green-200 dark:border-green-800 tracking-wider">
                {t('modelReady' as any) || 'Ready'}
              </span>
            )}
            {model.enabled && ['openai', 'anthropic', 'vertex-ai'].includes(model.provider) && (
              <span className="px-2 py-0.5 text-[10px] font-medium rounded-full bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400 border border-blue-200 dark:border-blue-800 tracking-wider">
                {t('modelCloudConnected' as any) || 'Cloud Connected'}
              </span>
            )}
          </h3>
          {onRemoveModel && (
            <button
              onClick={onRemoveModel}
              className="text-gray-400 hover:text-red-500 dark:hover:text-red-400 transition-colors p-1 rounded"
              title="Remove model"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
              </svg>
            </button>
          )}
        </div>
        <p className="text-sm text-gray-500 dark:text-gray-400">
          {model.provider} - {model.model_type === 'chat' ? 'Chat Model' : model.model_type === 'multimodal' ? 'Multimodal Model' : 'Embedding Model'}
        </p>

        {model.provider === 'huggingface' && model.metadata?.hf_author && (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {model.metadata.hf_format && (
              <span className={`px-2 py-0.5 text-xs font-medium rounded-full ${
                model.metadata.hf_format === 'GGUF' ? 'bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300' :
                model.metadata.hf_format === 'MLX' ? 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300' :
                'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300'
              }`}>
                {model.metadata.hf_format}
              </span>
            )}
            {model.metadata.hf_quantization && (
              <span className="px-2 py-0.5 text-xs font-medium rounded-full bg-orange-100 dark:bg-orange-900/30 text-orange-700 dark:text-orange-300">
                {model.metadata.hf_quantization}
              </span>
            )}
            <span className="px-2 py-0.5 text-xs rounded-full bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300">
              Author: {model.metadata.hf_author}
            </span>
            {model.metadata.hf_parameters && (
              <span className="px-2 py-0.5 text-xs rounded-full bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300">
                {(model.metadata.hf_parameters / 1e9).toFixed(1)}B params
              </span>
            )}
            {model.metadata.hf_downloads > 0 && (
              <span className="px-2 py-0.5 text-xs rounded-full bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300">
                Downloads: {model.metadata.hf_downloads > 1000000 ? `${(model.metadata.hf_downloads / 1000000).toFixed(1)}M` : model.metadata.hf_downloads > 1000 ? `${(model.metadata.hf_downloads / 1000).toFixed(0)}K` : model.metadata.hf_downloads}
              </span>
            )}
            {model.metadata.hf_storage_bytes && (
              <span className="px-2 py-0.5 text-xs rounded-full bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300">
                Storage: {(model.metadata.hf_storage_bytes / (1024 * 1024 * 1024)).toFixed(1)} GB
              </span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
