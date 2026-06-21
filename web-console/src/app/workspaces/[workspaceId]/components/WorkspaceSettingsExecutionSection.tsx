import type {
  ExecutionMode,
  ExecutionPriority,
  ProjectAssignmentMode,
  SgrMode,
} from './workspaceSettingsTypes';
import {
  COMMON_ARTIFACTS,
  EXECUTION_MODE_OPTIONS,
  EXECUTION_PRIORITY_OPTIONS,
  PROJECT_ASSIGNMENT_MODE_OPTIONS,
} from './workspaceSettingsState';

interface WorkspaceSettingsExecutionSectionProps {
  executionMode: ExecutionMode;
  executionPriority: ExecutionPriority;
  projectAssignmentMode: ProjectAssignmentMode;
  expectedArtifacts: string[];
  executionSettingsChanged: boolean;
  savingExecution: boolean;
  executionError: string | null;
  executionSuccess: boolean;
  intentExtractionAutoExecute: boolean;
  intentExtractionThreshold: number;
  intentExtractionChanged: boolean;
  savingIntentExtraction: boolean;
  intentExtractionError: string | null;
  intentExtractionSuccess: boolean;
  sgrEnabled: boolean;
  sgrMode: SgrMode;
  sgrChanged: boolean;
  savingSgr: boolean;
  sgrError: string | null;
  sgrSuccess: boolean;
  onExecutionModeChange: (value: ExecutionMode) => void;
  onExecutionPriorityChange: (value: ExecutionPriority) => void;
  onProjectAssignmentModeChange: (value: ProjectAssignmentMode) => void;
  onToggleArtifact: (artifact: string) => void;
  onIntentExtractionAutoExecuteChange: (value: boolean) => void;
  onIntentExtractionThresholdChange: (value: number) => void;
  onSgrEnabledChange: (value: boolean) => void;
  onSgrModeChange: (value: SgrMode) => void;
  onSaveExecutionSettings: () => Promise<void>;
  onSaveIntentExtraction: () => Promise<void>;
  onSaveSgr: () => Promise<void>;
}

export default function WorkspaceSettingsExecutionSection({
  executionMode,
  executionPriority,
  projectAssignmentMode,
  expectedArtifacts,
  executionSettingsChanged,
  savingExecution,
  executionError,
  executionSuccess,
  intentExtractionAutoExecute,
  intentExtractionThreshold,
  intentExtractionChanged,
  savingIntentExtraction,
  intentExtractionError,
  intentExtractionSuccess,
  sgrEnabled,
  sgrMode,
  sgrChanged,
  savingSgr,
  sgrError,
  sgrSuccess,
  onExecutionModeChange,
  onExecutionPriorityChange,
  onProjectAssignmentModeChange,
  onToggleArtifact,
  onIntentExtractionAutoExecuteChange,
  onIntentExtractionThresholdChange,
  onSgrEnabledChange,
  onSgrModeChange,
  onSaveExecutionSettings,
  onSaveIntentExtraction,
  onSaveSgr,
}: WorkspaceSettingsExecutionSectionProps) {
  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100 mb-2">Execution Mode</h2>
        <p className="text-sm text-gray-600 dark:text-gray-400">
          Configure the AI assistant behavior mode to balance conversation and execution.
        </p>
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
          Behavior Mode
        </label>
        <div className="grid grid-cols-3 gap-3">
          {EXECUTION_MODE_OPTIONS.map((option) => (
            <button
              key={option.value}
              onClick={() => onExecutionModeChange(option.value)}
              className={`
                p-3 rounded-lg border-2 text-left transition-all
                ${executionMode === option.value
                  ? 'border-blue-500 bg-blue-50 dark:bg-blue-900/20'
                  : 'border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600'
                }
              `}
            >
              <div className="flex items-center gap-2 mb-1">
                <span className="text-lg">{option.icon}</span>
                <span className={`font-medium ${executionMode === option.value ? 'text-blue-700 dark:text-blue-300' : 'text-gray-900 dark:text-gray-100'}`}>
                  {option.label}
                </span>
              </div>
              <p className="text-xs text-gray-500 dark:text-gray-400">{option.description}</p>
            </button>
          ))}
        </div>
      </div>

      {executionMode !== 'qa' && (
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
            Auto-Trigger Threshold
          </label>
          <div className="flex gap-2">
            {EXECUTION_PRIORITY_OPTIONS.map((option) => (
              <button
                key={option.value}
                onClick={() => onExecutionPriorityChange(option.value)}
                className={`
                  px-4 py-2 rounded-lg border text-sm transition-all
                  ${executionPriority === option.value
                    ? 'border-amber-500 bg-amber-50 dark:bg-amber-900/20 text-amber-700 dark:text-amber-300'
                    : 'border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300 hover:border-gray-300'
                  }
                `}
                title={option.description}
              >
                {option.label}
              </button>
            ))}
          </div>
          <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
            {EXECUTION_PRIORITY_OPTIONS.find((option) => option.value === executionPriority)?.description}
          </p>
        </div>
      )}

      <div>
        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
          Project Classification Mode
        </label>
        <div className="flex gap-2">
          {PROJECT_ASSIGNMENT_MODE_OPTIONS.map((option) => (
            <button
              key={option.value}
              onClick={() => onProjectAssignmentModeChange(option.value)}
              className={`
                px-4 py-2 rounded-lg border text-sm transition-all
                ${projectAssignmentMode === option.value
                  ? 'border-purple-500 bg-purple-50 dark:bg-purple-900/20 text-purple-700 dark:text-purple-300'
                  : 'border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300 hover:border-gray-300'
                }
              `}
              title={option.description}
            >
              {option.label}
            </button>
          ))}
        </div>
        <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
          {PROJECT_ASSIGNMENT_MODE_OPTIONS.find((option) => option.value === projectAssignmentMode)?.description}
        </p>
      </div>

      <div className="border-t border-gray-200 dark:border-gray-700 pt-4 mt-4">
        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
          Intent Extraction Auto-Execute
        </label>
        <div className="space-y-3">
          <div className="flex items-center gap-3">
            <input
              type="checkbox"
              id="intent-extraction-auto-execute"
              checked={intentExtractionAutoExecute}
              onChange={(event) => onIntentExtractionAutoExecuteChange(event.target.checked)}
              className="w-4 h-4 text-purple-600 rounded focus:ring-purple-500"
            />
            <label htmlFor="intent-extraction-auto-execute" className="text-sm text-gray-700 dark:text-gray-300">
              Auto-execute intent extraction when confidence meets threshold
            </label>
          </div>
          {intentExtractionAutoExecute && (
            <div className="ml-7 space-y-2">
              <div className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
                <span>Confidence Threshold</span>
                <span className="text-purple-700 dark:text-purple-300 font-bold">
                  {intentExtractionThreshold.toFixed(1)}
                </span>
              </div>
              <input
                type="range"
                min={0.5}
                max={1.0}
                step={0.1}
                value={intentExtractionThreshold}
                onChange={(event) => onIntentExtractionThresholdChange(parseFloat(event.target.value))}
                className="w-full accent-purple-600"
              />
              <div className="flex justify-between text-[10px] text-gray-400 dark:text-gray-500">
                {[0.5, 0.6, 0.7, 0.8, 0.9, 1.0].map((value) => (
                  <span key={value}>{value.toFixed(1)}</span>
                ))}
              </div>
              <p className="text-xs text-gray-500 dark:text-gray-400">
                When intent extraction confidence {'>='}  {intentExtractionThreshold.toFixed(1)}, auto-execute without manual confirmation
              </p>
            </div>
          )}
          <button
            onClick={() => void onSaveIntentExtraction()}
            disabled={savingIntentExtraction || !intentExtractionChanged}
            className="px-3 py-1.5 text-sm bg-purple-600 text-white rounded-md hover:bg-purple-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors"
          >
            {savingIntentExtraction ? 'Saving...' : 'Save Intent Extraction Settings'}
          </button>
          {intentExtractionError && (
            <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-2">
              <p className="text-xs text-red-700 dark:text-red-300">{intentExtractionError}</p>
            </div>
          )}
          {intentExtractionSuccess && (
            <div className="bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg p-2">
              <p className="text-xs text-green-700 dark:text-green-300">Intent extraction settings saved</p>
            </div>
          )}
        </div>
      </div>

      <div className="border-t border-gray-200 dark:border-gray-700 pt-4 mt-4">
        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
          Self-Graph Reasoning (SGR)
        </label>
        <div className="space-y-3">
          <div className="flex items-center gap-3">
            <input
              type="checkbox"
              id="sgr-enabled"
              checked={sgrEnabled}
              onChange={(event) => onSgrEnabledChange(event.target.checked)}
              className="w-4 h-4 text-teal-600 rounded focus:ring-teal-500"
            />
            <label htmlFor="sgr-enabled" className="text-sm text-gray-700 dark:text-gray-300">
              Enable reasoning graph extraction from LLM responses
            </label>
          </div>
          {sgrEnabled && (
            <div className="ml-7 space-y-2">
              <div className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
                <span>SGR Mode</span>
              </div>
              <div className="flex gap-2">
                {(['inline', 'two_pass'] as const).map((mode) => (
                  <button
                    key={mode}
                    onClick={() => onSgrModeChange(mode)}
                    className={`
                      px-3 py-1.5 rounded-lg border text-sm transition-all
                      ${sgrMode === mode
                        ? 'border-teal-500 bg-teal-50 dark:bg-teal-900/20 text-teal-700 dark:text-teal-300'
                        : 'border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300 hover:border-gray-300'
                      }
                    `}
                  >
                    {mode === 'inline' ? 'Inline' : 'Two-Pass'}
                  </button>
                ))}
              </div>
              <p className="text-xs text-gray-500 dark:text-gray-400">
                {sgrMode === 'inline'
                  ? 'Reasoning graph extracted from single LLM call (lower cost)'
                  : 'Separate LLM call extracts reasoning from response (higher quality)'}
              </p>
            </div>
          )}
          <button
            onClick={() => void onSaveSgr()}
            disabled={savingSgr || !sgrChanged}
            className="px-3 py-1.5 text-sm bg-teal-600 text-white rounded-md hover:bg-teal-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors"
          >
            {savingSgr ? 'Saving...' : 'Save SGR Settings'}
          </button>
          {sgrError && (
            <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-2">
              <p className="text-xs text-red-700 dark:text-red-300">{sgrError}</p>
            </div>
          )}
          {sgrSuccess && (
            <div className="bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg p-2">
              <p className="text-xs text-green-700 dark:text-green-300">SGR settings saved</p>
            </div>
          )}
        </div>
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
          Expected Output Types
        </label>
        <div className="flex flex-wrap gap-2">
          {COMMON_ARTIFACTS.map((artifact) => (
            <button
              key={artifact}
              onClick={() => onToggleArtifact(artifact)}
              className={`
                px-3 py-1.5 rounded-full text-sm transition-all
                ${expectedArtifacts.includes(artifact)
                  ? 'bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300 border border-emerald-300 dark:border-emerald-700'
                  : 'bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 border border-gray-200 dark:border-gray-700 hover:bg-gray-200 dark:hover:bg-gray-700'
                }
              `}
            >
              {artifact.toUpperCase()}
            </button>
          ))}
        </div>
        <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
          Select the output file types for this workspace. AI will prioritize producing these document types.
        </p>
      </div>

      {executionError && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-3">
          <p className="text-sm text-red-700 dark:text-red-300">{executionError}</p>
        </div>
      )}

      {executionSuccess && (
        <div className="bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg p-3">
          <p className="text-sm text-green-700 dark:text-green-300">Execution mode settings saved</p>
        </div>
      )}

      <div className="flex justify-end">
        <button
          onClick={() => void onSaveExecutionSettings()}
          disabled={savingExecution || !executionSettingsChanged}
          className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors"
        >
          {savingExecution ? 'Saving...' : 'Save Execution Mode'}
        </button>
      </div>
    </div>
  );
}
