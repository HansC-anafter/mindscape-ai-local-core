'use client';

import React from 'react';
import { t } from '../../lib/i18n';

interface PlaybookTabsProps {
  activeTab: 'info' | 'sop' | 'suggestions' | 'history';
  onTabChange: (tab: 'info' | 'sop' | 'suggestions' | 'history') => void;
  selectedVersion: 'system' | 'personal';
  playbook: {
    metadata: {
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
  return (
    <div className="bg-white shadow rounded-lg mb-6">
      <div className="border-b border-gray-200">
        <nav className="flex -mb-px">
          {[
            { id: 'info', label: '資訊' },
            { id: 'sop', label: 'SOP 流程' },
            { id: 'suggestions', label: '使用建議' },
            { id: 'history', label: '執行記錄' }
          ].map(tab => (
            <button
              key={tab.id}
              onClick={() => onTabChange(tab.id as any)}
              className={`px-6 py-3 text-sm font-medium border-b-2 ${
                activeTab === tab.id
                  ? 'border-blue-500 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
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
              <div className="text-sm text-gray-600">
                <span className="font-medium">AI 角色:</span> {playbook.metadata.entry_agent_type}
              </div>
            )}
            {playbook.metadata.required_tools && playbook.metadata.required_tools.length > 0 && (
              <div className="text-sm text-gray-600">
                <span className="font-medium">{t('requiredTools')}:</span> {playbook.metadata.required_tools.join(', ')}
              </div>
            )}
            {playbook.user_meta && (
              <div className="text-sm text-gray-500">
                <span className="font-medium">{t('usageCount')}:</span> {playbook.user_meta.use_count || 0} {t('times')}
              </div>
            )}
            <div>
              <h4 className="text-sm font-medium text-gray-700 mb-2">關聯的長期意圖</h4>
              {playbook.associated_intents && playbook.associated_intents.length > 0 ? (
                <div className="grid grid-cols-1 gap-2">
                  {playbook.associated_intents.map(intent => (
                    <div key={intent.intent_id} className="p-3 bg-gray-50 rounded-lg border border-gray-200 hover:border-blue-300 transition-colors">
                      <div className="font-medium text-sm text-gray-900">{intent.title}</div>
                      {intent.status && (
                        <div className="text-xs text-gray-500 mt-1">
                          <span className={`inline-block px-2 py-0.5 rounded ${
                            intent.status === 'active' ? 'bg-green-100 text-green-700' :
                            intent.status === 'completed' ? 'bg-blue-100 text-blue-700' :
                            'bg-gray-100 text-gray-700'
                          }`}>
                            {intent.status === 'active' ? '進行中' :
                             intent.status === 'completed' ? '已完成' :
                             intent.status}
                          </span>
                          {intent.priority && (
                            <span className={`ml-2 inline-block px-2 py-0.5 rounded ${
                              intent.priority === 'high' ? 'bg-red-100 text-red-700' :
                              intent.priority === 'medium' ? 'bg-yellow-100 text-yellow-700' :
                              'bg-gray-100 text-gray-700'
                            }`}>
                              {intent.priority === 'high' ? '高優先級' :
                               intent.priority === 'medium' ? '中優先級' :
                               intent.priority === 'low' ? '低優先級' :
                               intent.priority}
                            </span>
                          )}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="p-4 bg-gray-50 rounded-lg border border-gray-200 text-center">
                  <p className="text-sm text-gray-500">尚未關聯任何長期意圖</p>
                  <p className="text-xs text-gray-400 mt-1">可以在「心智空間」中建立意圖並關聯到此 Playbook</p>
                </div>
              )}
            </div>
          </div>
        )}

        {activeTab === 'sop' && (
          <div>
            {selectedVersion === 'personal' && playbook.version_info?.default_variant ? (
              <div className="mb-4 p-3 bg-blue-50 border border-blue-200 rounded-lg">
                <p className="text-sm text-blue-800">
                  你正在查看：個人版本（{playbook.version_info.default_variant.variant_name}），
                  來源：系統版 v{playbook.version_info.system_version}
                </p>
              </div>
            ) : (
              <div className="mb-4 p-3 bg-gray-50 border border-gray-200 rounded-lg">
                <p className="text-sm text-gray-600">
                  你正在查看：系統版本 v{playbook.version_info?.system_version || playbook.metadata.version}
                </p>
              </div>
            )}
            <div className="prose max-w-none">
              <pre className="whitespace-pre-wrap text-sm text-gray-700 bg-gray-50 p-4 rounded-lg border border-gray-200">
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
                <p className="text-gray-600 mb-4">你還沒有個人版本，可以讓 LLM 幫你生成：</p>
                <div className="flex gap-3 justify-center">
                  <button
                    onClick={onCopyClick}
                    className="px-4 py-2 text-sm text-gray-700 hover:text-gray-900 border border-gray-300 rounded hover:bg-gray-50"
                  >
                    直接複製為我的版本
                  </button>
                  <button
                    onClick={onLLMClick}
                    className="px-4 py-2 text-sm text-blue-600 hover:text-blue-800 border border-blue-300 rounded hover:bg-blue-50"
                  >
                    讓 LLM 根據我的使用情境，做一份個人版本
                  </button>
                </div>
              </div>
            ) : (
              <div>
                <p className="text-gray-600 mb-4">你已經有個人版本了。可以重新用 LLM 調整：</p>
                <button
                  onClick={onLLMClick}
                  className="px-4 py-2 text-sm text-blue-600 hover:text-blue-800 border border-blue-300 rounded hover:bg-blue-50"
                >
                  重新用 LLM 調整我的版本
                </button>
              </div>
            )}
          </div>
        )}

        {activeTab === 'history' && (
          <div>
            {playbook.execution_status ? (
              <div className="space-y-4">
                {playbook.execution_status.active_executions && playbook.execution_status.active_executions.length > 0 && (
                  <div>
                    <h4 className="text-sm font-medium text-gray-700 mb-3 flex items-center gap-2">
                      <span className="inline-block w-2 h-2 bg-green-500 rounded-full animate-pulse"></span>
                      執行中 ({playbook.execution_status.active_executions.length})
                    </h4>
                    {playbook.execution_status.active_executions.map(exec => (
                      <div key={exec.execution_id} className="p-4 bg-green-50 border-2 border-green-300 rounded-lg mb-3 shadow-sm">
                        <div className="flex items-start justify-between">
                          <div className="flex-1">
                            <div className="text-sm font-medium text-green-900 mb-1">
                              執行 ID: <code className="text-xs bg-green-100 px-1 rounded">{exec.execution_id.slice(0, 12)}...</code>
                            </div>
                            <div className="text-xs text-green-700 mb-1">
                              狀態: <span className="font-medium">{exec.status === 'running' ? '運行中' : exec.status}</span>
                            </div>
                            {exec.started_at && (
                              <div className="text-xs text-green-600">
                                開始時間: {new Date(exec.started_at).toLocaleString('zh-TW')}
                              </div>
                            )}
                          </div>
                          <span className="px-2 py-1 text-xs bg-green-200 text-green-800 rounded font-medium">
                            🔄 進行中
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
                {playbook.execution_status.recent_executions && playbook.execution_status.recent_executions.length > 0 && (
                  <div>
                    <h4 className="text-sm font-medium text-gray-700 mb-3">最近執行記錄</h4>
                    {playbook.execution_status.recent_executions.map(exec => (
                      <div key={exec.execution_id} className="p-4 bg-gray-50 border border-gray-200 rounded-lg mb-2 hover:border-gray-300 transition-colors">
                        <div className="flex items-start justify-between">
                          <div className="flex-1">
                            <div className="text-sm font-medium text-gray-800 mb-1">
                              執行 ID: <code className="text-xs bg-gray-100 px-1 rounded">{exec.execution_id.slice(0, 12)}...</code>
                            </div>
                            <div className="flex items-center gap-2 mb-1">
                              <span className={`text-xs px-2 py-0.5 rounded font-medium ${
                                exec.status === 'completed' ? 'bg-green-100 text-green-700' :
                                exec.status === 'failed' ? 'bg-red-100 text-red-700' :
                                'bg-gray-100 text-gray-700'
                              }`}>
                                {exec.status === 'completed' ? '✅ 完成' :
                                 exec.status === 'failed' ? '❌ 失敗' :
                                 exec.status}
                              </span>
                            </div>
                            {exec.started_at && (
                              <div className="text-xs text-gray-500">
                                開始: {new Date(exec.started_at).toLocaleString('zh-TW')}
                                {exec.completed_at && (
                                  <span className="ml-2">
                                    | 完成: {new Date(exec.completed_at).toLocaleString('zh-TW')}
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
                    <p className="text-gray-500 mb-2">尚無執行記錄</p>
                    <p className="text-xs text-gray-400">點擊下方的「執行」按鈕開始使用此 Playbook</p>
                  </div>
                )}
              </div>
            ) : (
              <div className="text-center py-12">
                <p className="text-gray-500 mb-2">尚無執行記錄</p>
                <p className="text-xs text-gray-400">點擊下方的「執行」按鈕開始使用此 Playbook</p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
