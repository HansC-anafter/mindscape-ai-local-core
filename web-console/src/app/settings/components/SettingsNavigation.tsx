'use client';

import React from 'react';
import { t } from '../../../lib/i18n';
import type { SettingsTab } from '../types';

interface NavigationItem {
  id: string;
  label: string;
  icon?: string;
  tab: SettingsTab;
  section?: string;
  provider?: string;      // 品牌/提供商
  model?: string;         // 具體模型
  service?: string;       // 服務類型
  children?: NavigationItem[];
}

interface SettingsNavigationProps {
  activeTab: SettingsTab;
  activeSection?: string;
  activeProvider?: string;
  activeModel?: string;
  activeService?: string;
  onNavigate: (tab: SettingsTab, section?: string, provider?: string, model?: string, service?: string) => void;
}

// Helper function to check if a navigation item is active
function isItemActive(
  item: NavigationItem,
  activeTab: SettingsTab,
  activeSection?: string,
  activeProvider?: string,
  activeService?: string
): boolean {
  if (item.tab !== activeTab) return false;
  if (activeSection && item.section !== activeSection) return false;
  if (activeProvider && item.provider !== activeProvider) return false;
  if (activeService && item.service !== activeService) return false;
  return true;
}

const navigationItems: NavigationItem[] = [
  {
    id: 'basic',
    label: 'basicSettings',
    icon: '📋',
    tab: 'basic',
    children: [
      {
        id: 'backend-mode',
        label: 'backendMode',
        tab: 'basic',
        section: 'backend-mode',
      },
      {
        id: 'models-and-quota',
        label: 'modelsAndQuota',
        tab: 'basic',
        section: 'models-and-quota',
      },
      {
        id: 'api-quota',
        label: 'apiAndQuota',
        tab: 'basic',
        section: 'api-quota',
      },
      {
        id: 'embedding',
        label: 'embeddingModel',
        tab: 'basic',
        section: 'embedding',
      },
      {
        id: 'llm-chat',
        label: 'llmChatModel',
        tab: 'basic',
        section: 'llm-chat',
      },
      {
        id: 'oauth',
        label: 'oauthIntegration',
        tab: 'basic',
        section: 'oauth',
      },
    ],
  },
  {
    id: 'mindscape',
    label: 'mindscapeConfiguration',
    icon: '🧠',
    tab: 'mindscape',
  },
  {
    id: 'tools',
    label: 'toolsAndIntegrations',
    icon: '🔧',
    tab: 'tools',
    children: [
      {
        id: 'system-tools',
        label: 'systemTools',
        tab: 'tools',
        section: 'system-tools',
      },
      {
        id: 'external-saas-tools',
        label: 'externalSAASTools',
        tab: 'tools',
        section: 'external-saas-tools',
      },
      {
        id: 'mcp-server',
        label: 'mcpServer',
        tab: 'tools',
        section: 'mcp-server',
        children: [
          {
            id: 'mcp-openai',
            label: 'OpenAI',
            tab: 'tools',
            section: 'mcp-server',
            provider: 'openai',
          },
          {
            id: 'mcp-anthropic',
            label: 'Anthropic',
            tab: 'tools',
            section: 'mcp-server',
            provider: 'anthropic',
          },
          {
            id: 'mcp-github',
            label: 'GitHub',
            tab: 'tools',
            section: 'mcp-server',
            provider: 'github',
          },
          {
            id: 'mcp-google',
            label: 'Google',
            tab: 'tools',
            section: 'mcp-server',
            provider: 'google',
          },
          {
            id: 'mcp-custom',
            label: 'customMCP',
            tab: 'tools',
            section: 'mcp-server',
            provider: 'custom',
          },
        ],
      },
      {
        id: 'third-party-workflow',
        label: 'thirdPartyWorkflow',
        tab: 'tools',
        section: 'third-party-workflow',
        children: [
          {
            id: 'workflow-zapier',
            label: 'Zapier',
            tab: 'tools',
            section: 'third-party-workflow',
            provider: 'zapier',
          },
          {
            id: 'workflow-n8n',
            label: 'n8n',
            tab: 'tools',
            section: 'third-party-workflow',
            provider: 'n8n',
          },
          {
            id: 'workflow-make',
            label: 'Make',
            tab: 'tools',
            section: 'third-party-workflow',
            provider: 'make',
          },
          {
            id: 'workflow-integromat',
            label: 'Integromat',
            tab: 'tools',
            section: 'third-party-workflow',
            provider: 'integromat',
          },
          {
            id: 'workflow-custom',
            label: 'customWorkflow',
            tab: 'tools',
            section: 'third-party-workflow',
            provider: 'custom',
          },
        ],
      },
    ],
  },
  {
    id: 'social_media',
    label: 'socialMediaIntegration',
    icon: '📱',
    tab: 'social_media',
    children: [
      {
        id: 'twitter',
        label: 'twitterIntegration',
        tab: 'social_media',
        provider: 'twitter',
      },
      {
        id: 'facebook',
        label: 'facebookIntegration',
        tab: 'social_media',
        provider: 'facebook',
      },
      {
        id: 'instagram',
        label: 'instagramIntegration',
        tab: 'social_media',
        provider: 'instagram',
      },
      {
        id: 'linkedin',
        label: 'linkedinIntegration',
        tab: 'social_media',
        provider: 'linkedin',
      },
      {
        id: 'youtube',
        label: 'youtubeIntegration',
        tab: 'social_media',
        provider: 'youtube',
      },
      {
        id: 'line',
        label: 'lineIntegration',
        tab: 'social_media',
        provider: 'line',
      },
    ],
  },
  {
    id: 'localization',
    label: 'localization',
    icon: '🌐',
    tab: 'localization',
    children: [
      {
        id: 'auto-translation',
        label: 'autoTranslation',
        tab: 'localization',
        section: 'auto-translation',
      },
      {
        id: 'translation-management',
        label: 'translationManagement',
        tab: 'localization',
        section: 'translation-management',
      },
    ],
  },
  {
    id: 'service_status',
    label: 'serviceStatus',
    icon: '📊',
    tab: 'service_status',
  },
];

export function SettingsNavigation({
  activeTab,
  activeSection,
  activeProvider,
  activeModel,
  activeService,
  onNavigate,
}: SettingsNavigationProps) {
  const [expandedItems, setExpandedItems] = React.useState<Set<string>>(
    new Set(['basic']) // 默認展開基礎設定
  );

  const toggleExpand = (itemId: string) => {
    setExpandedItems(prev => {
      const next = new Set(prev);
      if (next.has(itemId)) {
        next.delete(itemId);
      } else {
        next.add(itemId);
      }
      return next;
    });
  };

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <nav className="space-y-1 flex-1 overflow-y-auto min-h-0 px-2 pt-2">
        {navigationItems.map((item) => {
          const isActive = activeTab === item.tab && !activeSection;
          const hasChildren = item.children && item.children.length > 0;
          const isExpanded = expandedItems.has(item.id);

          return (
            <div key={item.id}>
              <button
                onClick={() => {
                  if (hasChildren) {
                    // If not expanded, expand first
                    if (!isExpanded) {
                      toggleExpand(item.id);
                    }
                    // For social_media, navigate to overview (parent level)
                    if (item.tab === 'social_media') {
                      onNavigate(item.tab);
                      return;
                    }
                    // For other items, navigate to first child
                    const firstChild = item.children![0];
                    if (firstChild) {
                      onNavigate(firstChild.tab, firstChild.section, firstChild.provider, firstChild.model, firstChild.service);
                      return;
                    }
                  }
                  onNavigate(item.tab);
                }}
                className={`w-full text-left px-2 py-1.5 rounded-md text-xs font-medium transition-colors flex items-center justify-between ${
                  isActive
                    ? 'bg-purple-50 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300 border-l-4 border-purple-500 dark:border-purple-500'
                    : 'text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700'
                }`}
              >
                <div className="flex items-center gap-1.5">
                  {item.icon && <span className="text-xs">{item.icon}</span>}
                  <span>{t(item.label as any)}</span>
                </div>
                {hasChildren && (
                  <svg
                    className={`w-3 h-3 transition-transform ${isExpanded ? 'rotate-90' : ''}`}
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                  </svg>
                )}
              </button>

              {hasChildren && isExpanded && (
                <div className="ml-4 mt-1 space-y-0.5">
                  {item.children!.map((child) => {
                    const hasGrandchildren = child.children && child.children.length > 0;
                    const isChildExpanded = expandedItems.has(child.id);
                    // For social_media, check if provider matches
                    const isChildActive = activeTab === child.tab &&
                      (child.tab === 'social_media'
                        ? activeProvider === child.provider
                        : activeSection === child.section && !activeProvider);

                    return (
                      <div key={child.id}>
                        <button
                          onClick={() => {
                            if (hasGrandchildren) {
                              // Expand if collapsed
                              if (!expandedItems.has(child.id)) {
                                toggleExpand(child.id);
                              }
                              // Always navigate to first grandchild when clicking child with grandchildren
                              const firstGrandchild = child.children![0];
                              if (firstGrandchild) {
                                onNavigate(firstGrandchild.tab, firstGrandchild.section, firstGrandchild.provider, firstGrandchild.model, firstGrandchild.service);
                                return;
                              }
                            }
                            // For social_media sub-items, navigate to overview with provider anchor
                            if (child.tab === 'social_media' && child.provider) {
                              onNavigate(child.tab, undefined, child.provider);
                              return;
                            }
                            onNavigate(child.tab, child.section);
                          }}
                          className={`w-full text-left px-2 py-1 rounded-md text-xs transition-colors flex items-center justify-between ${
                            isChildActive
                              ? 'bg-purple-100 dark:bg-purple-900/40 text-purple-700 dark:text-purple-300 font-medium'
                              : 'text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-700'
                          }`}
                        >
                          <span>{t(child.label as any)}</span>
                          {hasGrandchildren && (
                            <svg
                              className={`w-2.5 h-2.5 transition-transform ${isChildExpanded ? 'rotate-90' : ''}`}
                              fill="none"
                              stroke="currentColor"
                              viewBox="0 0 24 24"
                            >
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                            </svg>
                          )}
                        </button>

                        {/* 第三層：品牌/提供商 */}
                        {hasGrandchildren && isChildExpanded && (
                          <div className="ml-3 mt-0.5 space-y-0.5">
                            {child.children!.map((grandchild) => {
                              const isGrandchildActive = activeTab === grandchild.tab &&
                                activeSection === grandchild.section &&
                                activeProvider === grandchild.provider;

                              return (
                                <button
                                  key={grandchild.id}
                                  onClick={() => onNavigate(grandchild.tab, grandchild.section, grandchild.provider, grandchild.model)}
                                  className={`w-full text-left px-2 py-0.5 rounded text-xs transition-colors ${
                                    isGrandchildActive
                                      ? 'bg-purple-200 dark:bg-purple-900/50 text-purple-800 dark:text-purple-200 font-medium'
                                      : 'text-gray-500 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-700'
                                  }`}
                                >
                                  {t(grandchild.label as any) || grandchild.label}
                                </button>
                              );
                            })}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </nav>
    </div>
  );
}

