'use client';

import type { EnabledModel } from '@/app/settings/hooks/useEnabledModels';

import {
  CHAT_PROFILES,
  DeploymentScope,
  ModelTypeFilter,
  MULTIMODAL_PROFILES,
} from './types';

interface ModelsAndQuotaDynamicAllocationProps {
  deploymentScope: DeploymentScope;
  enabledChatModels: EnabledModel[];
  enabledMultimodalModels: EnabledModel[];
  modelTypeFilter: Extract<ModelTypeFilter, 'chat' | 'multimodal'>;
  profileBindings: Record<DeploymentScope, Record<string, string>>;
  profileSaving: boolean;
  onDeploymentScopeChange: (deploymentScope: DeploymentScope) => void;
  onSaveProfileBindings: (updated: Record<DeploymentScope, Record<string, string>>) => void;
}

export function ModelsAndQuotaDynamicAllocation({
  deploymentScope,
  enabledChatModels,
  enabledMultimodalModels,
  modelTypeFilter,
  profileBindings,
  profileSaving,
  onDeploymentScopeChange,
  onSaveProfileBindings,
}: ModelsAndQuotaDynamicAllocationProps) {
  const profiles = modelTypeFilter === 'chat' ? CHAT_PROFILES : MULTIMODAL_PROFILES;
  const options = modelTypeFilter === 'multimodal' ? enabledMultimodalModels : enabledChatModels;
  const currentProfileMap = profileBindings[deploymentScope] || {};

  return (
    <div className="flex-1">
      <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-1">Dynamic Allocation</h3>
      <p className="text-xs text-gray-500 dark:text-gray-400 mb-4">
        Set the model used by each capability level. Empty values use the system default chat model. Changes are saved immediately.
      </p>
      <div className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs text-gray-500 dark:text-gray-400">Execution Target</span>
          <button
            onClick={() => onDeploymentScopeChange('local')}
            data-filter-button="dynamic-local"
            className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors border ${
              deploymentScope === 'local'
                ? 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300 border-green-400/40 dark:border-green-700'
                : 'bg-surface-accent dark:bg-gray-700 text-primary dark:text-gray-300 border-default dark:border-gray-600 hover:bg-surface-secondary dark:hover:bg-gray-600'
            }`}
          >
            Local Development
          </button>
          <button
            onClick={() => onDeploymentScopeChange('cloud')}
            data-filter-button="dynamic-cloud"
            className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors border ${
              deploymentScope === 'cloud'
                ? 'bg-sky-100 dark:bg-sky-900/30 text-sky-700 dark:text-sky-300 border-sky-400/40 dark:border-sky-700'
                : 'bg-surface-accent dark:bg-gray-700 text-primary dark:text-gray-300 border-default dark:border-gray-600 hover:bg-surface-secondary dark:hover:bg-gray-600'
            }`}
          >
            Cloud VM
          </button>
        </div>
        <div className="text-xs text-gray-400 dark:text-gray-500">
          Editing:
          <span className="ml-1 font-medium text-gray-600 dark:text-gray-300">
            {deploymentScope === 'local' ? 'Local Development' : 'Cloud VM'}
          </span>
          <span className="ml-2">
            {deploymentScope === 'local'
              ? 'Workstation and local runtimes use these model bindings.'
              : 'Remote executor / GPU VM uses these model bindings by default.'}
          </span>
        </div>
        {profiles.map(({ description, key, label }) => (
          <div
            key={key}
            className="flex items-center gap-3 p-3 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800"
          >
            <div className="flex-1 min-w-0">
              <div className="text-sm font-medium text-gray-900 dark:text-gray-100">{label}</div>
              <div className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{description}</div>
            </div>
            <select
              value={currentProfileMap[key] || ''}
              onChange={(event) => {
                const updatedScopeMap = { ...currentProfileMap, [key]: event.target.value };
                if (!event.target.value) {
                  delete updatedScopeMap[key];
                }
                onSaveProfileBindings({
                  local: { ...(profileBindings.local || {}) },
                  cloud: { ...(profileBindings.cloud || {}) },
                  [deploymentScope]: updatedScopeMap,
                });
              }}
              disabled={profileSaving}
              className="w-56 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-accent/50 dark:focus:ring-gray-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 disabled:opacity-50"
            >
              <option value="">Default: system chat model</option>
              {options.map((model) => (
                <option key={model.model_name} value={model.model_name}>
                  {model.display_name || model.model_name}
                </option>
              ))}
            </select>
          </div>
        ))}
      </div>
    </div>
  );
}
