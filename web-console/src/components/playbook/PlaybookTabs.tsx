'use client';

import React from 'react';
import { t, useLocale } from '../../lib/i18n';
import PlaybookUsageStats from './PlaybookUsageStats';

interface PlaybookTabsProps {
  activeTab: 'info' | 'sop' | 'suggestions' | 'history';
  onTabChange: (tab: 'info' | 'sop' | 'suggestions' | 'history') => void;
  selectedVersion: 'system' | 'personal';
  playbook: {
    metadata: {
      playbook_code: string;
      entry_agent_type?: string;
      required_tools: string[];
      version: string;
    };
    sop_content: string;
    user_meta?: {
      use_count?: number;
    };
    associated_intents: Array<{
      intent_id: string;
      title: string;
      status?: string;
      priority?: string;
    }>;
    execution_status?: {
      active_executions: Array<{
        execution_id: string;
        status: string;
        started_at?: string;
      }>;
      recent_executions: Array<{
        execution_id: string;
        status: string;
        started_at?: string;
        completed_at?: string;
      }>;
    };
    version_info?: {
      has_personal_variant: boolean;
      default_variant?: {
        variant_name: string;
        personalized_sop_content?: string;
      };
      system_version: string;
    };
  };
  onCopyClick: () => void;
  onLLMClick: () => void;
}

export default function PlaybookTabs({
  activeTab,
  onTabChange,
  selectedVersion,
  playbook,
  onCopyClick,
  onLLMClick
}: PlaybookTabsProps) {
  const [locale] = useLocale();
  return (
    <div className="bg-surface-secondary dark:bg-gray-800 shadow rounded-lg mb-6">
      <div className="border-b border-default dark:border-gray-700">
        <nav className="flex -mb-px">
          {[
            { id: 'info', label: t('playbookTabInfo' as any) },
            { id: 'sop', label: t('sopDocument' as any) },
            { id: 'suggestions', label: t('playbookTabSuggestions' as any) },
            { id: 'history', label: t('playbookTabHistory' as any) }
          ].map(tab => (
            <button
              key={tab.id}
              onClick={() => onTabChange(tab.id as any)}
              className={`px-6 py-3 text-sm font-medium border-b-2 ${activeTab === tab.id
                  ? 'border-blue-500 dark:border-blue-400 text-blue-600 dark:text-blue-400'
                  : 'border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 hover:border-gray-300 dark:hover:border-gray-600'
                }`}
            >
              {tab.label}
            </button>
          ))}
        </nav>
      </div>

      {/* Tab Content */}
      <div className="p-6">
        {activeTab === 'info' && (
          <div className="space-y-4">
            {playbook.metadata.entry_agent_type && (
              <div className="text-sm text-gray-600 dark:text-gray-400">
                <span className="font-medium">{t('aiRole' as any)}:</span> {playbook.metadata.entry_agent_type}
              </div>
            )}
            {playbook.metadata.required_tools && playbook.metadata.required_tools.length > 0 && (
              <div className="text-sm text-gray-600 dark:text-gray-400">
                <span className="font-medium">{t('requiredTools' as any)}:</span> {playbook.metadata.required_tools.join(', ')}
              </div>
            )}
            {playbook.user_meta && (
              <div className="text-sm text-gray-500 dark:text-gray-400">
                <span className="font-medium">{t('usageCount' as any)}:</span> {playbook.user_meta.use_count || 0} {t('times' as any)}
              </div>
            )}
            <div>
              <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">{t('associatedLongTermIntents' as any)}</h4>
              {playbook.associated_intents && playbook.associated_intents.length > 0 ? (
                <div className="grid grid-cols-1 gap-2">
                  {playbook.associated_intents.map(intent => (
                    <div key={intent.intent_id} className="p-3 bg-gray-50 dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 hover:border-blue-300 dark:hover:border-blue-600 transition-colors">
                      <div className="font-medium text-sm text-gray-900 dark:text-gray-100">{intent.title}</div>
                      {intent.status && (
                        <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                          <span className={`inline-block px-2 py-0.5 rounded ${intent.status === 'active' ? 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300' :
                              intent.status === 'completed' ? 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300' :
                                'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300'
                            }`}>
                            {intent.status === 'active' ? t('playbookIntentStatusActive' as any) :
                              intent.status === 'completed' ? t('playbookIntentStatusCompleted' as any) :
                                intent.status}
                          </span>
                          {intent.priority && (
                            <span className={`ml-2 inline-block px-2 py-0.5 rounded ${intent.priority === 'high' ? 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300' :
                                intent.priority === 'medium' ? 'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-300' :
                                  'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300'
                              }`}>
                              {intent.priority === 'high' ? t('playbookIntentPriorityHigh' as any) :
                                intent.priority === 'medium' ? t('playbookIntentPriorityMedium' as any) :
                                  intent.priority === 'low' ? t('playbookIntentPriorityLow' as any) :
                                    intent.priority}
                            </span>
                          )}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="p-4 bg-gray-50 dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 text-center">
                  <p className="text-sm text-gray-500 dark:text-gray-400">{t('noAssociatedIntents' as any)}</p>
                  <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">{t('createIntentInMindscape' as any)}</p>
                </div>
              )}
            </div>
          </div>
        )}

        {activeTab === 'sop' && (
          <div>
            {selectedVersion === 'personal' && playbook.version_info?.default_variant ? (
              <div className="mb-4 p-3 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg">
                <p className="text-sm text-blue-800 dark:text-blue-300">
                  {t('youAreViewingPersonal', { name: playbook.version_info.default_variant.variant_name })}
                  {' ' + t('sourceSystemVersion', { version: playbook.version_info.system_version })}
                </p>
              </div>
            ) : (
              <div className="mb-4 p-3 bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg">
                <p className="text-sm text-gray-600 dark:text-gray-400">
                  {t('youAreViewingSystem', { version: playbook.version_info?.system_version || playbook.metadata.version })}
                </p>
              </div>
            )}
            <div className="prose max-w-none">
              <pre className="whitespace-pre-wrap text-sm text-gray-700 dark:text-gray-300 bg-gray-50 dark:bg-gray-800 p-4 rounded-lg border border-gray-200 dark:border-gray-700">
                {selectedVersion === 'personal' && playbook.version_info?.default_variant?.personalized_sop_content
                  ? playbook.version_info.default_variant.personalized_sop_content
                  : playbook.sop_content}
              </pre>
            </div>
          </div>
        )}

        {activeTab === 'suggestions' && (
          <div>
            {!playbook.version_info?.has_personal_variant ? (
              <div className="text-center py-8">
                <p className="text-gray-600 dark:text-gray-400 mb-4">{t('youDontHavePersonalVersion' as any)}</p>
                <div className="flex gap-3 justify-center">
                  <button
                    onClick={onCopyClick}
                    className="px-4 py-2 text-sm text-primary dark:text-gray-300 hover:text-primary dark:hover:text-gray-100 border border-default dark:border-gray-600 rounded hover:bg-surface-secondary dark:hover:bg-gray-700 bg-surface-accent dark:bg-gray-800"
                  >
                    {t('copyAsMyVersion' as any)}
                  </button>
                  <button
                    onClick={onLLMClick}
                    className="px-4 py-2 text-sm text-accent dark:text-blue-400 hover:text-accent dark:hover:text-blue-300 border border-accent dark:border-blue-700 rounded hover:bg-accent-10 dark:hover:bg-blue-900/20 bg-surface-accent dark:bg-gray-800"
                  >
                    {t('letLLMCreatePersonalVersion' as any)}
                  </button>
                </div>
              </div>
            ) : (
              <div>
                <p className="text-gray-600 dark:text-gray-400 mb-4">{t('youAlreadyHavePersonalVersion' as any)}</p>
                <button
                  onClick={onLLMClick}
                  className="px-4 py-2 text-sm text-accent dark:text-blue-400 hover:text-accent dark:hover:text-blue-300 border border-accent dark:border-blue-700 rounded hover:bg-accent-10 dark:hover:bg-blue-900/20 bg-surface-accent dark:bg-gray-800"
                >
                  {t('readjustWithLLM' as any)}
                </button>
              </div>
            )}
          </div>
        )}

        {activeTab === 'history' && (
          <div>
            {/* Usage Statistics */}
            <div className="mb-6">
              <PlaybookUsageStats playbookCode={playbook.metadata.playbook_code} />
            </div>

            {/* Execution History */}
            {playbook.execution_status ? (
              <div className="space-y-4">
                {playbook.execution_status.active_executions && playbook.execution_status.active_executions.length > 0 && (
                  <div>
                    <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3 flex items-center gap-2">
                      <span className="inline-block w-2 h-2 bg-green-500 dark:bg-green-400 rounded-full animate-pulse"></span>
                      {(t as any)('executingWithCount', { count: playbook.execution_status.active_executions.length })}
                    </h4>
                    {playbook.execution_status.active_executions.map(exec => (
                      <div key={exec.execution_id} className="p-4 bg-green-50 dark:bg-green-900/20 border-2 border-green-300 dark:border-green-700 rounded-lg mb-3 shadow-sm">
                        <div className="flex items-start justify-between">
                          <div className="flex-1">
                            <div className="text-sm font-medium text-green-900 dark:text-green-300 mb-1">
                              {t('executionId' as any)}: <code className="text-xs bg-green-100 dark:bg-green-900/30 px-1 rounded">{exec.execution_id.slice(0, 12)}...</code>
                            </div>
                            <div className="text-xs text-green-700 dark:text-green-400 mb-1">
                              {t('status' as any)}: <span className="font-medium">{exec.status === 'running' ? t('playbookExecStatusRunning' as any) : exec.status}</span>
                            </div>
                            {exec.started_at && (
                              <div className="text-xs text-green-600 dark:text-green-400">
                                {t('startedAt' as any)}: {new Date(exec.started_at).toLocaleString(locale === 'en' ? 'en-US' : locale === 'ja' ? 'ja-JP' : 'zh-TW')}
                              </div>
                            )}
                          </div>
                          <span className="px-2 py-1 text-xs bg-green-200 dark:bg-green-800 text-green-800 dark:text-green-300 rounded font-medium">
                            {t('inProgress' as any)}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
                {playbook.execution_status.recent_executions && playbook.execution_status.recent_executions.length > 0 && (
                  <div>
                    <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">{t('recentExecutionHistory' as any)}</h4>
                    {playbook.execution_status.recent_executions.map(exec => (
                      <div key={exec.execution_id} className="p-4 bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg mb-2 hover:border-gray-300 dark:hover:border-gray-600 transition-colors">
                        <div className="flex items-start justify-between">
                          <div className="flex-1">
                            <div className="text-sm font-medium text-gray-800 dark:text-gray-200 mb-1">
                              {t('executionId' as any)}: <code className="text-xs bg-gray-100 dark:bg-gray-700 px-1 rounded">{exec.execution_id.slice(0, 12)}...</code>
                            </div>
                            <div className="flex items-center gap-2 mb-1">
                              <span className={`text-xs px-2 py-0.5 rounded font-medium ${exec.status === 'completed' ? 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300' :
                                  exec.status === 'failed' ? 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300' :
                                    'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300'
                                }`}>
                                {exec.status === 'completed' ? t('completed' as any) :
                                  exec.status === 'failed' ? t('failed' as any) :
                                    exec.status}
                              </span>
                            </div>
                            {exec.started_at && (
                              <div className="text-xs text-gray-500 dark:text-gray-400">
                                {t('started' as any)}: {new Date(exec.started_at).toLocaleString(locale === 'en' ? 'en-US' : locale === 'ja' ? 'ja-JP' : 'zh-TW')}
                                {exec.completed_at && (
                                  <span className="ml-2">
                                    | {t('completedLabel' as any)}: {new Date(exec.completed_at).toLocaleString(locale === 'en' ? 'en-US' : locale === 'ja' ? 'ja-JP' : 'zh-TW')}
                                  </span>
                                )}
                              </div>
                            )}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
                {(!playbook.execution_status.active_executions || playbook.execution_status.active_executions.length === 0) &&
                  (!playbook.execution_status.recent_executions || playbook.execution_status.recent_executions.length === 0) && (
                    <div className="text-center py-12">
                      <p className="text-gray-500 dark:text-gray-400 mb-2">{t('noExecutionRecord' as any)}</p>
                      <p className="text-xs text-gray-400 dark:text-gray-500">{t('clickExecuteButton' as any)}</p>
                    </div>
                  )}
              </div>
            ) : (
              <div className="text-center py-12">
                <p className="text-gray-500 dark:text-gray-400 mb-2">{t('noExecutionRecord' as any)}</p>
                <p className="text-xs text-gray-400 dark:text-gray-500">{t('clickExecuteButton' as any)}</p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
