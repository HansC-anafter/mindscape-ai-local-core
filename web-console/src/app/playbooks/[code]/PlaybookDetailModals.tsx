import CopyVariantModal from '../../../components/playbook/CopyVariantModal';
import LLMDrawer from '../../../components/playbook/LLMDrawer';
import { useT } from '../../../lib/i18n';
import type { OptimizationSuggestion } from './playbookDetailTypes';

interface PlaybookDetailModalsProps {
  playbookName: string;
  playbookCode: string;
  systemSOP: string;
  showCopyModal: boolean;
  onCloseCopyModal: () => void;
  onConfirmCopy: (variantName: string, variantDescription: string) => void | Promise<void>;
  showLLMDrawer: boolean;
  onCloseLLMDrawer: () => void;
  onVariantCreated: () => void | Promise<void>;
  showOptimizeModal: boolean;
  optimizationLoading: boolean;
  optimizationSuggestions: OptimizationSuggestion[];
  onCloseOptimizeModal: () => void;
  onApplySuggestion: (suggestion: OptimizationSuggestion) => void | Promise<void>;
  showNotesModal: boolean;
  userNotes: string;
  onUserNotesChange: (value: string) => void;
  onCloseNotesModal: () => void;
  onSaveNotes: () => void | Promise<void>;
}

export function PlaybookDetailModals({
  playbookName,
  playbookCode,
  systemSOP,
  showCopyModal,
  onCloseCopyModal,
  onConfirmCopy,
  showLLMDrawer,
  onCloseLLMDrawer,
  onVariantCreated,
  showOptimizeModal,
  optimizationLoading,
  optimizationSuggestions,
  onCloseOptimizeModal,
  onApplySuggestion,
  showNotesModal,
  userNotes,
  onUserNotesChange,
  onCloseNotesModal,
  onSaveNotes,
}: PlaybookDetailModalsProps) {
  const t = useT();
  return (
    <>
      <CopyVariantModal
        isOpen={showCopyModal}
        onClose={onCloseCopyModal}
        onConfirm={onConfirmCopy}
        playbookName={playbookName}
      />

      <LLMDrawer
        isOpen={showLLMDrawer}
        onClose={onCloseLLMDrawer}
        playbookCode={playbookCode}
        systemSOP={systemSOP}
        onVariantCreated={onVariantCreated}
      />

      {showOptimizeModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-surface-secondary dark:bg-gray-800 rounded-lg p-6 max-w-4xl w-full mx-4 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100">{t('playbookOptimizationSuggestions' as any)}</h2>
              <button
                onClick={onCloseOptimizeModal}
                className="text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 text-2xl"
              >
                {t('close' as any)}
              </button>
            </div>

            {optimizationLoading ? (
              <div className="text-center py-8">
                <p className="text-gray-600 dark:text-gray-400">{t('analyzingPatterns' as any)}</p>
              </div>
            ) : optimizationSuggestions.length > 0 ? (
              <div className="space-y-4">
                <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
                  {t('basedOnUsagePattern' as any)}
                </p>
                {optimizationSuggestions.map((suggestion, index) => (
                  <div
                    key={index}
                    className="p-4 border border-default dark:border-gray-700 rounded-lg hover:border-accent/30 dark:hover:border-blue-600 transition-colors bg-surface-accent dark:bg-gray-800"
                  >
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <h3 className="font-medium text-gray-900 dark:text-gray-100 mb-1">{suggestion.title}</h3>
                        <p className="text-sm text-gray-600 dark:text-gray-400 mb-2">{suggestion.description}</p>
                        <p className="text-xs text-gray-500 dark:text-gray-400">{suggestion.rationale}</p>
                        {suggestion.step_number && (
                          <span className="inline-block mt-2 px-2 py-1 text-xs bg-yellow-100 dark:bg-yellow-900/30 text-yellow-800 dark:text-yellow-300 rounded">
                            {t('step' as any)} {suggestion.step_number}
                          </span>
                        )}
                      </div>
                      <button
                        onClick={() => onApplySuggestion(suggestion)}
                        className="ml-4 px-3 py-1 text-sm bg-accent dark:bg-blue-700 text-white rounded hover:bg-accent/90 dark:hover:bg-blue-600"
                      >
                        {t('apply' as any)}
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center py-8">
                <p className="text-gray-600 dark:text-gray-400">{t('noOptimizationSuggestions' as any)}</p>
              </div>
            )}
          </div>
        </div>
      )}

      {showNotesModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-surface-secondary dark:bg-gray-800 rounded-lg p-6 max-w-2xl w-full mx-4 max-h-[80vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100">{t('myNotes' as any)}</h2>
              <button
                onClick={onCloseNotesModal}
                className="text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 text-2xl"
              >
                {t('close' as any)}
              </button>
            </div>
            <textarea
              value={userNotes}
              onChange={(event) => onUserNotesChange(event.target.value)}
              className="w-full px-4 py-2 border border-default dark:border-gray-600 rounded-md mb-4 focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-500 bg-surface-accent dark:bg-gray-700 text-gray-900 dark:text-gray-100"
              rows={8}
              placeholder={t('writeYourNotesHere' as any)}
            />
            <div className="flex justify-end gap-2">
              <button
                onClick={onCloseNotesModal}
                className="px-4 py-2 text-gray-700 dark:text-gray-300 border border-default dark:border-gray-600 rounded-md hover:bg-tertiary dark:hover:bg-gray-700 bg-surface-accent dark:bg-gray-800"
              >
                {t('cancel' as any)}
              </button>
              <button
                onClick={onSaveNotes}
                className="px-4 py-2 bg-accent dark:bg-blue-700 text-white rounded-md hover:bg-accent/90 dark:hover:bg-blue-600"
              >
                {t('saveNotes' as any)}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
