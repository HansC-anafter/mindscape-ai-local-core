'use client';

import React, { useState, useEffect } from 'react';
import { ThinkingPanel } from '@/components/workspace/ThinkingPanel';
import { useT } from '@/lib/i18n';

interface InstalledCapability {
  id?: string;
  code?: string;
  display_name?: string;
  version?: string;
  description?: string;
  scope?: string;
  ui_components?: Array<{
    code: string;
    path: string;
    description: string;
    export: string;
    artifact_types: string[];
    playbook_codes: string[];
    import_path: string;
  }>;
}

interface PackPanelProps {
  workspaceId: string;
  apiUrl: string;
  storyThreadId?: string;
}

type PackSubTab = 'thinking' | 'capabilities' | 'apps';

export function PackPanel({
  workspaceId,
  apiUrl,
  storyThreadId,
}: PackPanelProps) {
  const t = useT();
  const [activeSubTab, setActiveSubTab] = useState<PackSubTab>('apps');
  const [installedCapabilities, setInstalledCapabilities] = useState<InstalledCapability[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadInstalledCapabilities();
  }, []);

  const loadInstalledCapabilities = async () => {
    try {
      const response = await fetch(`${apiUrl}/api/v1/capability-packs/installed-capabilities`);
      if (response.ok) {
        const data = await response.json();
        setInstalledCapabilities(data || []);
      } else {
        setInstalledCapabilities([]);
      }
    } catch (err) {
      setInstalledCapabilities([]);
    } finally {
      setLoading(false);
    }
  };

  const openCapabilityUI = (capabilityCode: string) => {
    // 在新标签页中打开该 capability 的 UI 页面
    const url = `/workspaces/${workspaceId}/capabilities/${capabilityCode}`;
    window.open(url, '_blank');
  };

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Mini Tab Header */}
      <div className="flex-shrink-0 border-b dark:border-gray-700">
        <div className="flex items-center gap-1 px-2 pt-2 pb-1">
          <button
            onClick={() => setActiveSubTab('apps')}
            className={`p-1.5 rounded transition-colors ${
              activeSubTab === 'apps'
                ? 'bg-accent-10 dark:bg-blue-900/30 text-accent dark:text-blue-300'
                : 'text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 hover:text-gray-700 dark:hover:text-gray-300'
            }`}
            title={t('appsWithUI' as any) || 'Apps'}
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="h-4 w-4"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"
              />
            </svg>
          </button>
          <button
            onClick={() => setActiveSubTab('thinking')}
            className={`p-1.5 rounded transition-colors ${
              activeSubTab === 'thinking'
                ? 'bg-accent-10 dark:bg-blue-900/30 text-accent dark:text-blue-300'
                : 'text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 hover:text-gray-700 dark:hover:text-gray-300'
            }`}
            title={t('tabBackgroundTasks' as any) || 'Thinking'}
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="h-4 w-4"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"
              />
            </svg>
          </button>
          <button
            onClick={() => setActiveSubTab('capabilities')}
            className={`p-1.5 rounded transition-colors ${
              activeSubTab === 'capabilities'
                ? 'bg-accent-10 dark:bg-blue-900/30 text-accent dark:text-blue-300'
                : 'text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 hover:text-gray-700 dark:hover:text-gray-300'
            }`}
            title={t('installedCapabilities' as any) || 'Capabilities'}
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="h-4 w-4"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4"
              />
            </svg>
          </button>
        </div>
      </div>

      {/* Tab Content */}
      <div className="flex-1 overflow-y-auto min-h-0">
        {activeSubTab === 'apps' && (
          <div className="p-3 space-y-3">
            {loading ? (
              <div className="text-xs text-secondary dark:text-gray-400">
                {t('loading' as any) || 'Loading...'}
              </div>
            ) : (() => {
              const appsWithUI = installedCapabilities.filter(
                cap => cap.ui_components && cap.ui_components.length > 0
              );

              return appsWithUI.length === 0 ? (
                <div className="text-xs text-tertiary dark:text-gray-500">
                  {t('noAppsWithUI' as any) || 'No apps with UI available'}
                </div>
              ) : (
                <div className="space-y-2">
                  <div className="text-xs font-semibold text-gray-700 dark:text-gray-300 mb-2">
                    {t('appsWithUI' as any) || 'Apps with UI'} ({appsWithUI.length})
                  </div>
                  {appsWithUI.map((cap, index) => {
                    // 后端 API 使用 id 来匹配，所以优先使用 id，如果没有则使用 code
                    const capabilityIdentifier = cap.id || cap.code;

                    return (
                      <div
                        key={`app-${capabilityIdentifier || 'unknown'}-${index}`}
                        className="p-3 bg-surface-secondary dark:bg-gray-800 rounded border border-gray-200 dark:border-gray-700 hover:border-blue-300 dark:hover:border-blue-600 transition-colors cursor-pointer"
                        onClick={() => capabilityIdentifier && openCapabilityUI(capabilityIdentifier)}
                      >
                        <div className="flex items-start justify-between mb-2">
                          <div className="flex-1 min-w-0">
                            <div className="text-xs font-medium text-primary dark:text-gray-300 mb-1">
                              {cap.display_name || cap.code}
                            </div>
                            <div className="text-[10px] text-tertiary dark:text-gray-500">
                              {capabilityIdentifier} v{cap.version || '1.0.0'}
                            </div>
                          </div>
                          {cap.scope === 'system' && (
                            <span className="px-1.5 py-0.5 text-[10px] bg-blue-100 dark:bg-blue-900 text-blue-800 dark:text-blue-200 rounded flex-shrink-0 ml-2">
                              Official
                            </span>
                          )}
                        </div>
                        {cap.description && (
                          <div className="text-[10px] text-secondary dark:text-gray-400 mb-2">
                            {cap.description}
                          </div>
                        )}
                        <div className="flex items-center justify-between mt-2 pt-2 border-t dark:border-gray-700">
                          <div className="text-[10px] text-tertiary dark:text-gray-500">
                            {cap.ui_components!.length} UI component{cap.ui_components!.length > 1 ? 's' : ''}
                          </div>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              capabilityIdentifier && openCapabilityUI(capabilityIdentifier);
                            }}
                            className="px-2 py-1 text-[10px] bg-blue-500 hover:bg-blue-600 dark:bg-blue-600 dark:hover:bg-blue-700 text-white rounded transition-colors"
                          >
                            {t('openUI' as any) || '打开 UI'}
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              );
            })()}
          </div>
        )}

        {activeSubTab === 'thinking' && (
          <div className="h-full">
            <ThinkingPanel
              workspaceId={workspaceId}
              apiUrl={apiUrl}
              storyThreadId={storyThreadId}
            />
          </div>
        )}

        {activeSubTab === 'capabilities' && (
          <div className="p-3 space-y-3">
            {loading ? (
              <div className="text-xs text-secondary dark:text-gray-400">
                {t('loading' as any) || 'Loading...'}
              </div>
            ) : installedCapabilities.length === 0 ? (
              <div className="text-xs text-tertiary dark:text-gray-500">
                {t('noCapabilityPacksInstalled' as any) || 'No capability packs installed'}
              </div>
            ) : (
              <div className="space-y-2">
                <div className="text-xs font-semibold text-gray-700 dark:text-gray-300 mb-2">
                  {t('installedCapabilityPacks' as any) || 'Installed Capability Packs'}
                </div>
                {installedCapabilities.map((cap, index) => {
                  const capabilityCode = cap.code || cap.id;
                  const hasUIComponents = cap.ui_components && cap.ui_components.length > 0;

                  return (
                    <div
                      key={`installed-cap-${capabilityCode || 'unknown'}-${index}`}
                      className="p-3 bg-surface-secondary dark:bg-gray-800 rounded border border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600 transition-colors"
                    >
                      <div className="flex items-start justify-between mb-2">
                        <div className="flex-1 min-w-0">
                          <div className="text-xs font-medium text-primary dark:text-gray-300 mb-1">
                            {cap.display_name || cap.code}
                          </div>
                          <div className="text-[10px] text-tertiary dark:text-gray-500">
                            {capabilityCode} v{cap.version || '1.0.0'}
                          </div>
                        </div>
                        {cap.scope === 'system' && (
                          <span className="px-1.5 py-0.5 text-[10px] bg-blue-100 dark:bg-blue-900 text-blue-800 dark:text-blue-200 rounded flex-shrink-0 ml-2">
                            Official
                          </span>
                        )}
                      </div>
                      {cap.description && (
                        <div className="text-[10px] text-secondary dark:text-gray-400 mb-2">
                          {cap.description}
                        </div>
                      )}
                      {hasUIComponents && (
                        <div className="flex items-center justify-between mt-2 pt-2 border-t dark:border-gray-700">
                          <div className="text-[10px] text-tertiary dark:text-gray-500">
                            {cap.ui_components!.length} UI component{cap.ui_components!.length > 1 ? 's' : ''} available
                          </div>
                          <button
                            onClick={() => capabilityCode && openCapabilityUI(capabilityCode)}
                            className="px-2 py-1 text-[10px] bg-blue-500 hover:bg-blue-600 dark:bg-blue-600 dark:hover:bg-blue-700 text-white rounded transition-colors"
                          >
                            {t('openUI' as any) || '打开 UI'}
                          </button>
                        </div>
                      )}
                      {!hasUIComponents && (
                        <div className="text-[10px] text-tertiary dark:text-gray-500 mt-2 pt-2 border-t dark:border-gray-700">
                          No UI components available
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
