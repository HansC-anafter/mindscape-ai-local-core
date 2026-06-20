import type { QuickPrompt } from './types';

export function buildExecutionChatQuickPrompts(
  t: (key: any, params?: any) => string,
  executionStatus?: string
): QuickPrompt[] {
  return [
    {
      label: t('explainWhyFailed' as any),
      prompt: executionStatus === 'failed'
        ? t('explainWhyFailedPrompt' as any)
        : t('explainWhyFailedPromptAlt' as any),
    },
    {
      label: t('suggestNextSteps' as any),
      prompt: t('suggestNextStepsPrompt' as any),
    },
    {
      label: t('reviewPlaybookSteps' as any),
      prompt: t('reviewPlaybookStepsPrompt' as any),
    },
  ];
}
