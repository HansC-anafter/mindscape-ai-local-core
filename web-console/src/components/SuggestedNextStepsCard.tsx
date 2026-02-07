'use client';

import React from 'react';
import { t } from '@/lib/i18n';
import HelpIcon from './HelpIcon';

interface NextStep {
  type?: string;
  title: string;
  description: string;
  action: string;
  params?: Record<string, any>;
  cta_label: string;
  priority: 'high' | 'medium' | 'low';
  side_effect_level?: 'readonly' | 'soft_write' | 'hard_write';
  llm_analysis?: {
    confidence?: number;
    reason?: string;
    content_tags?: string[];
  };
}

interface SuggestedNextStepsCardProps {
  nextSteps: NextStep[];
  workspaceId: string;
  apiUrl?: string;
  suggestionHistory?: Array<{
    round_id: string;
    timestamp: string;
    suggestions: NextStep[];
  }>;
}

export default function SuggestedNextStepsCard({
  nextSteps,
  workspaceId,
  apiUrl = '',
  suggestionHistory = []
}: SuggestedNextStepsCardProps) {
  const [showHistory, setShowHistory] = React.useState(false);
  const [executingSteps, setExecutingSteps] = React.useState<Set<number>>(new Set());
  const [executedSteps, setExecutedSteps] = React.useState<Set<number>>(new Set());

  const translateText = (text: string): string => {
    if (!text) return text;

    // Check if it starts with an i18n key followed by space and more text
    // e.g., "suggestion.run_playbook_cta 專案拆解 & 里程碑"
    // Match pattern: suggestion.xxx or suggestions.xxx followed by space and text
    const keyMatch = text.match(/^(suggestion\.|suggestions\.)([^\s]+)\s+(.+)$/);
    if (keyMatch) {
      const fullKey = keyMatch[1] + keyMatch[2];
      const restText = keyMatch[3];
      let translated: string;
      try {
        translated = t(fullKey as any);
      } catch (e) {
        // If translation fails, just return the rest text without the key
        return restText;
      }
      // If translation found and different from key, use it
      if (translated && translated !== fullKey) {
        return `${translated} ${restText}`;
      }
      // If translation not found (returned same as key), remove the key and just show rest text
      // This handles cases where backend sends untranslated key + text
      return restText;
    }

    // Check if it's a pure i18n key (no additional text after)
    if (text.startsWith('suggestion.') || text.startsWith('suggestions.')) {
      let translated: string;
      try {
        translated = t(text as any);
      } catch (e) {
        // If translation fails, return empty to avoid showing raw key
        return '';
      }
      // If translation found, return it; otherwise return empty to avoid showing raw key
      if (translated !== text) {
        return translated;
      }
      // If key not found, return empty string to avoid showing raw i18n key
      return '';
    }

    return text;
  };

  const handleAction = async (action: string, step: NextStep, stepIndex: number) => {
    console.log('[SuggestedNextStepsCard] handleAction called:', {
      action,
      stepIndex,
      stepTitle: step.title,
      stepAction: step.action,
      params: step.params || (step as any).action_params
    });

    if (action === 'start_chat') {
      const chatInput = document.querySelector('textarea[name="workspace-chat-input"]') as HTMLTextAreaElement;
      if (chatInput) {
        chatInput.focus();
      }
      return;
    }

    if (action === 'upload_file') {
      // For upload_file action, trigger file input and let file upload handler process it
      // We'll mark it as executing to show feedback, but the actual execution happens after file selection
      setExecutingSteps(prev => {
        const newSet = new Set(prev);
        newSet.add(stepIndex);
        return newSet;
      });

      const fileInput = document.querySelector('#file-upload-input') as HTMLInputElement;
      if (fileInput) {
        // Add event listener to handle file selection (only once)
        const handleFileChange = () => {
          // File selection will trigger upload, which will trigger workspace-chat-updated event
          // Mark as executed after a delay to allow upload to process
          setTimeout(() => {
            setExecutedSteps(prev => {
              const newSet = new Set(prev);
              newSet.add(stepIndex);
              return newSet;
            });
            setExecutingSteps(prev => {
              const newSet = new Set(prev);
              newSet.delete(stepIndex);
              return newSet;
            });
          }, 1000);
          fileInput.removeEventListener('change', handleFileChange);
        };
        fileInput.addEventListener('change', handleFileChange);
        fileInput.click();
      } else {
        // If file input not found, remove executing state
        setExecutingSteps(prev => {
          const newSet = new Set(prev);
          newSet.delete(stepIndex);
          return newSet;
        });
        console.error('[SuggestedNextStepsCard] File upload input not found');
      }
      return;
    }

    // Mark step as executing
    setExecutingSteps(prev => {
      const newSet = new Set(prev);
      newSet.add(stepIndex);
      return newSet;
    });

    // Send action to backend with params
    try {
      const requestBody = {
        action: action,
        action_params: (step as any).params || (step as any).action_params || {},
        files: [],
        mode: 'auto'
      };

      console.log('[SuggestedNextStepsCard] Sending action request:', {
        url: `${apiUrl}/api/v1/workspaces/${workspaceId}/chat`,
        method: 'POST',
        body: requestBody
      });

      const response = await fetch(
        `${apiUrl}/api/v1/workspaces/${workspaceId}/chat`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(requestBody)
        }
      );

      console.log('[SuggestedNextStepsCard] Action response:', {
        status: response.status,
        statusText: response.statusText,
        ok: response.ok
      });

      if (response.ok) {
        const data = await response.json();
        console.log('[SuggestedNextStepsCard] Action success:', data);

        // Mark step as executed (hide it)
        setExecutedSteps(prev => {
          const newSet = new Set(prev);
          newSet.add(stepIndex);
          return newSet;
        });
        setExecutingSteps(prev => {
          const newSet = new Set(prev);
          newSet.delete(stepIndex);
          return newSet;
        });

        // Handle redirect if present
        if (data.redirect) {
          window.location.href = data.redirect;
          return;
        }

        // Trigger unified update event (both components will listen to this)
        // Use single event to avoid duplicate refreshes
        window.dispatchEvent(new Event('workspace-chat-updated'));
        // Note: workbench-refresh is redundant if workspace-chat-updated also triggers workbench update
        // Only dispatch if workbench needs separate refresh timing
        // window.dispatchEvent(new Event('workbench-refresh'));

        // Scroll timeline to top to show latest task (not bottom)
        setTimeout(() => {
          const timelineContainer = document.querySelector('[data-timeline-container]') as HTMLElement;
          if (timelineContainer) {
            timelineContainer.scrollTop = 0;
          }
        }, 200);
      } else {
        console.error('Failed to execute action:', await response.text());
        setExecutingSteps(prev => {
          const newSet = new Set(prev);
          newSet.delete(stepIndex);
          return newSet;
        });
      }
    } catch (err) {
      console.error('Error executing action:', err);
      setExecutingSteps(prev => {
        const newSet = new Set(prev);
        newSet.delete(stepIndex);
        return newSet;
      });
    }
  };

  if (!nextSteps || nextSteps.length === 0) {
    return null;
  }

  return (
    <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded p-2 shadow-sm">
      <div className="flex items-center justify-between gap-1 mb-2">
        <div className="flex items-center gap-1">
          <h3 className="font-semibold text-xs text-gray-900 dark:text-gray-100">{t('suggestedNextSteps' as any)}</h3>
          <HelpIcon helpKey="suggestedNextStepsHelp" />
        </div>
        {suggestionHistory && suggestionHistory.length > 0 && (
          <button
            onClick={() => setShowHistory(!showHistory)}
            className="text-[10px] text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 underline"
          >
            {showHistory ? t('hideDetails' as any) : `${t('timelineHistory' as any)} (${suggestionHistory.length})`}
          </button>
        )}
      </div>

      {/* History section (collapsible) */}
      {showHistory && suggestionHistory && suggestionHistory.length > 0 && (
        <div className="mb-2 space-y-1.5 border-b border-gray-200 dark:border-gray-700 pb-2">
          {suggestionHistory.map((round, roundIdx) => (
            <div key={round.round_id} className="bg-gray-50 dark:bg-gray-800/50 border border-gray-200 dark:border-gray-700 rounded p-1.5">
              <div className="text-[10px] text-gray-500 dark:text-gray-400 mb-1">
                {new Date(round.timestamp).toLocaleTimeString()}
              </div>
              <div className="space-y-1">
                {round.suggestions
                  .filter((step) => {
                    const title = step.title || '';
                    const description = step.description || '';
                    const action = step.action || '';
                    return !title.includes('系統狀態正常') &&
                      !title.includes('System Status Normal') &&
                      !description.includes('目前這個工作空間還缺以下設定') &&
                      !description.includes('目前這個工作空間還缺以下設定：') &&
                      !action.includes('system_status') &&
                      !action.includes('system-status');
                  })
                  .map((step, idx) => (
                    <div
                      key={idx}
                      className="p-1.5 rounded border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800"
                    >
                      <div className="font-medium text-gray-700 dark:text-gray-300 text-[10px] mb-0.5">
                        {translateText(step.title)}
                      </div>
                      <div className="text-[9px] text-gray-500 dark:text-gray-400">
                        {translateText(step.description)}
                      </div>
                    </div>
                  ))}
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="space-y-1.5">
        {nextSteps
          .filter((step, idx) => {
            // Hide executed steps
            if (executedSteps.has(idx)) {
              return false;
            }
            const title = step.title || '';
            const description = step.description || '';
            const action = step.action || '';
            return !title.includes('系統狀態正常') &&
              !title.includes('System Status Normal') &&
              !description.includes('目前這個工作空間還缺以下設定') &&
              !description.includes('目前這個工作空間還缺以下設定：') &&
              !action.includes('system_status') &&
              !action.includes('system-status');
          })
          .map((step, idx) => {
            const originalIndex = nextSteps.findIndex(s => s === step);
            const isExecuting = executingSteps.has(originalIndex);
            const isExecuted = executedSteps.has(originalIndex);

            return (
              <div
                key={originalIndex}
                className={`p-2 rounded border transition-opacity ${isExecuted ? 'opacity-0 h-0 overflow-hidden' : 'opacity-100'
                  } ${step.priority === 'high'
                    ? 'border-blue-300 dark:border-blue-700 bg-blue-50 dark:bg-blue-900/20'
                    : step.priority === 'medium'
                      ? 'border-yellow-300 dark:border-yellow-700 bg-yellow-50 dark:bg-yellow-900/20'
                      : 'border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800'
                  } ${isExecuting ? 'animate-pulse' : ''}`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-1.5 mb-0.5 flex-wrap">
                      <div className="font-medium text-gray-900 dark:text-gray-100 text-xs">
                        {translateText(step.title)}
                      </div>
                      {/* Confidence score badge if available */}
                      {step.llm_analysis?.confidence !== undefined && (
                        <span
                          className="text-[10px] px-1.5 py-0.5 rounded bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 border border-gray-400 dark:border-gray-600 flex-shrink-0 whitespace-nowrap"
                          title={t('llmConfidenceScore', { confidence: step.llm_analysis.confidence.toFixed(2) })}
                        >
                          {t('confidence' as any)}{step.llm_analysis.confidence.toFixed(2)}
                        </span>
                      )}
                    </div>
                    <div className="text-[10px] text-gray-600 dark:text-gray-400">
                      {translateText(step.description)}
                    </div>
                    {isExecuting && (
                      <div className="text-[9px] text-blue-600 dark:text-blue-400 mt-1">
                        {t('executing' as any)}
                      </div>
                    )}
                  </div>
                  <button
                    onClick={() => handleAction(step.action, step, originalIndex)}
                    disabled={isExecuting}
                    className={`flex-shrink-0 px-2 py-1 text-[10px] font-medium rounded transition-all ${isExecuting
                        ? 'opacity-50 cursor-not-allowed'
                        : 'cursor-pointer'
                      } ${step.priority === 'high'
                        ? 'bg-blue-600 dark:bg-blue-700 text-white hover:bg-blue-700 dark:hover:bg-blue-600'
                        : step.priority === 'medium'
                          ? 'bg-yellow-600 dark:bg-yellow-700 text-white hover:bg-yellow-700 dark:hover:bg-yellow-600'
                          : 'bg-gray-600 dark:bg-gray-700 text-white hover:bg-gray-700 dark:hover:bg-gray-600'
                      }`}
                  >
                    {isExecuting ? t('executing' as any) : t('execute' as any)}
                  </button>
                </div>
              </div>
            );
          })}
      </div>
    </div>
  );
}
