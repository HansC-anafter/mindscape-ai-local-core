import { ArrowLeft } from 'lucide-react';
import ErrorDialog from '@/components/ErrorDialog';
import { useT } from '@/lib/i18n';
import type { WorkspaceCreationMethod, WorkspaceWizardData, WorkspaceWizardStep } from './workspaceHomeTypes';

interface WorkspaceHomeCreateViewProps {
  wizardStep: WorkspaceWizardStep;
  wizardData: WorkspaceWizardData;
  wizardSeedText: string;
  errorDialogMessage: string | null;
  isCreateDisabled: boolean;
  onBack: () => void;
  onSelectMethod: (method: WorkspaceCreationMethod) => void;
  onWizardDataChange: (wizardData: WorkspaceWizardData) => void;
  onWizardSeedTextChange: (value: string) => void;
  onCreate: () => void | Promise<void>;
  onCloseErrorDialog: () => void;
}

export function WorkspaceHomeCreateView({
  wizardStep,
  wizardData,
  wizardSeedText,
  errorDialogMessage,
  isCreateDisabled,
  onBack,
  onSelectMethod,
  onWizardDataChange,
  onWizardSeedTextChange,
  onCreate,
  onCloseErrorDialog,
}: WorkspaceHomeCreateViewProps) {
  const t = useT();
  return (
    <div className="min-h-screen bg-surface dark:bg-gray-950">
      <div className="max-w-7xl mx-auto px-6 py-8">
        {wizardStep === 'method' && (
          <div className="max-w-6xl mx-auto">
            <div className="flex items-center gap-4 mb-6">
              <button
                onClick={onBack}
                className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-primary dark:text-gray-300 bg-surface-accent dark:bg-gray-800 border border-default dark:border-gray-700 rounded-lg hover:bg-surface-secondary dark:hover:bg-gray-700 transition-colors"
              >
                <ArrowLeft className="w-4 h-4" />
                {t('back' as any)}
              </button>
              <h1 className="text-3xl font-bold text-primary dark:text-gray-100">{t('createWorkspace' as any)}</h1>
            </div>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <div className="bg-surface-accent dark:bg-gray-900 rounded-lg border border-default dark:border-gray-800 p-6 shadow-sm">
                <h2 className="text-xl font-semibold text-primary dark:text-gray-100 mb-4">{t('selectCreationMethod' as any)}</h2>
                <div className="space-y-4">
                  <button
                    onClick={() => onSelectMethod('quick')}
                    className={`w-full p-4 text-left border-2 rounded-lg transition-colors ${
                      wizardData.method === 'quick'
                        ? 'border-blue-500 dark:border-blue-600 bg-blue-50 dark:bg-blue-900/20'
                        : 'border-default dark:border-gray-700 hover:border-blue-500 dark:hover:border-blue-600'
                    }`}
                  >
                    <h3 className="font-semibold text-primary dark:text-gray-100 mb-2">{t('quickCreate' as any)}</h3>
                    <p className="text-sm text-secondary dark:text-gray-400">{t('quickCreateDescription' as any)}</p>
                  </button>
                  <button
                    onClick={() => onSelectMethod('llm-guided')}
                    className={`w-full p-4 text-left border-2 rounded-lg transition-colors ${
                      wizardData.method === 'llm-guided'
                        ? 'border-blue-500 dark:border-blue-600 bg-blue-50 dark:bg-blue-900/20'
                        : 'border-default dark:border-gray-700 hover:border-blue-500 dark:hover:border-blue-600'
                    }`}
                  >
                    <h3 className="font-semibold text-primary dark:text-gray-100 mb-2">{t('llmGuidedCreate' as any)}</h3>
                    <p className="text-sm text-secondary dark:text-gray-400">{t('llmGuidedCreateDescription' as any)}</p>
                  </button>
                </div>
              </div>

              <div className="bg-surface-accent dark:bg-gray-900 rounded-lg border border-default dark:border-gray-800 p-6 shadow-sm">
                {!wizardData.method ? (
                  <div className="flex items-center justify-center h-full min-h-[200px] text-secondary dark:text-gray-400">
                    <p>{t('pleaseSelectCreationMethod' as any)}</p>
                  </div>
                ) : (
                  <div className="space-y-6">
                    <div>
                      <div className="flex items-center justify-between mb-4">
                        <h2 className="text-xl font-semibold text-primary dark:text-gray-100">
                          {wizardData.method === 'quick' ? t('quickCreate' as any) : t('llmGuidedCreate' as any)}
                        </h2>
                        <button
                          onClick={() => onWizardDataChange({ ...wizardData, method: undefined })}
                          className="inline-flex items-center gap-2 px-3 py-1.5 text-sm font-medium text-primary dark:text-gray-300 bg-surface-accent dark:bg-gray-800 border border-default dark:border-gray-700 rounded-lg hover:bg-surface-secondary dark:hover:bg-gray-700 transition-colors"
                        >
                          <ArrowLeft className="w-4 h-4" />
                          {t('previous' as any)}
                        </button>
                      </div>
                      <div className="space-y-4">
                        <div>
                          <label className="block text-sm font-medium text-primary dark:text-gray-300 mb-1">
                            {t('workspaceNameRequired' as any)}
                          </label>
                          <input
                            type="text"
                            value={wizardData.title || ''}
                            onChange={(event) => onWizardDataChange({ ...wizardData, title: event.target.value })}
                            placeholder={t('workspaceNamePlaceholder' as any)}
                            className="w-full px-3 py-2 border border-default dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 bg-surface-accent dark:bg-gray-700 text-primary dark:text-gray-100"
                          />
                        </div>
                        <div>
                          <label className="block text-sm font-medium text-primary dark:text-gray-300 mb-1">
                            {wizardData.method === 'quick' ? t('workspaceDescriptionOptional' as any) : t('workspaceDescriptionRequired' as any)}
                            {wizardData.method === 'llm-guided' && <span className="text-red-500">*</span>}
                          </label>
                          <textarea
                            value={wizardData.description || ''}
                            onChange={(event) => onWizardDataChange({ ...wizardData, description: event.target.value })}
                            placeholder={
                              wizardData.method === 'quick'
                                ? t('workspaceDescriptionPlaceholder' as any)
                                : t('workspaceDescriptionLLMPlaceholder' as any)
                            }
                            rows={wizardData.method === 'quick' ? 3 : 5}
                            className="w-full px-3 py-2 border border-default dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 bg-surface-accent dark:bg-gray-700 text-primary dark:text-gray-100"
                          />
                        </div>
                      </div>
                    </div>

                    <div className="border-t border-default dark:border-gray-700 pt-6">
                      <h3 className="text-lg font-semibold text-primary dark:text-gray-100 mb-2">{t('addReferenceSeed' as any)}</h3>
                      <p className="text-sm text-secondary dark:text-gray-400 mb-4">{t('addReferenceSeedDescription' as any)}</p>
                      <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                          {t('pasteText' as any)}
                        </label>
                        <textarea
                          value={wizardSeedText}
                          onChange={(event) => onWizardSeedTextChange(event.target.value)}
                          placeholder={t('pasteTextPlaceholder' as any)}
                          rows={5}
                          className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
                        />
                      </div>
                    </div>

                    <div className="border-t border-default dark:border-gray-700 pt-6">
                      <button
                        onClick={onCreate}
                        disabled={isCreateDisabled}
                        className="w-full px-4 py-2 bg-blue-600 dark:bg-blue-700 text-white rounded-lg hover:bg-blue-700 dark:hover:bg-blue-600 disabled:bg-gray-400 dark:disabled:bg-gray-600 disabled:cursor-not-allowed"
                      >
                        {t('createAndComplete' as any)}
                      </button>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </div>

      <ErrorDialog
        isOpen={!!errorDialogMessage}
        onClose={onCloseErrorDialog}
        message={errorDialogMessage || ''}
      />
    </div>
  );
}
