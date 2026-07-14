'use client';

import React from 'react';
import ChevronRight from 'lucide-react/dist/esm/icons/chevron-right.js';
import { t } from '../../../lib/i18n';
import type { SettingsTab } from '../types';
import {
  activeExpandableItemIds,
  navigationItemMatches,
  navigationItems,
  type NavigationItem,
} from '../navigation/settingsNavigationRegistry';

interface SettingsNavigationProps {
  activeTab: SettingsTab;
  activeSection?: string;
  activeProvider?: string;
  activeModel?: string;
  activeService?: string;
  onNavigate: (tab: SettingsTab, section?: string, provider?: string, model?: string, service?: string) => void;
}

function useActiveContext({
  activeTab,
  activeSection,
  activeProvider,
  activeModel,
  activeService,
}: Omit<SettingsNavigationProps, 'onNavigate'>) {
  return React.useMemo(
    () => ({
      activeTab,
      activeSection,
      activeProvider,
      activeModel,
      activeService,
    }),
    [activeModel, activeProvider, activeSection, activeService, activeTab],
  );
}

function firstNavigableChild(item: NavigationItem): NavigationItem | null {
  if (!item.children?.length) return null;
  const [firstChild] = item.children;
  if (!firstChild) return null;
  return firstChild.children?.length ? firstNavigableChild(firstChild) || firstChild : firstChild;
}

export function SettingsNavigation({
  activeTab,
  activeSection,
  activeProvider,
  activeModel,
  activeService,
  onNavigate,
}: SettingsNavigationProps) {
  const [hoveredItemId, setHoveredItemId] = React.useState<string | null>(null);
  const [expandedItems, setExpandedItems] = React.useState<Set<string>>(
    new Set(['basic', 'credentials']),
  );
  const activeContext = useActiveContext({
    activeTab,
    activeSection,
    activeProvider,
    activeModel,
    activeService,
  });

  React.useEffect(() => {
    const ids = activeExpandableItemIds(activeContext);
    if (!ids.length) return;
    setExpandedItems((prev) => {
      const next = new Set(prev);
      ids.forEach((id) => next.add(id));
      return next;
    });
  }, [activeContext]);

  const toggleExpand = (itemId: string) => {
    setExpandedItems((prev) => {
      const next = new Set(prev);
      if (next.has(itemId)) {
        next.delete(itemId);
      } else {
        next.add(itemId);
      }
      return next;
    });
  };

  const navigateToItem = (item: NavigationItem) => {
    if (item.children?.length) {
      const child = firstNavigableChild(item);
      if (child) {
        onNavigate(child.tab, child.section, child.provider, child.model, child.service);
        return;
      }
    }
    if (item.tab === 'social_media' && item.provider) {
      onNavigate(item.tab, undefined, item.provider, item.model, item.service);
      return;
    }
    onNavigate(item.tab, item.section, item.provider, item.model, item.service);
  };

  const renderItem = (item: NavigationItem, depth: number = 0): React.ReactNode => {
    const hasChildren = Boolean(item.children?.length);
    const isExpanded = expandedItems.has(item.id);
    const isActive = navigationItemMatches(item, activeContext);
    const Icon = item.icon;
    const paddingClass = depth === 0 ? 'px-2 py-1.5' : depth === 1 ? 'px-2 py-1' : 'px-2 py-0.5';
    const childIndentClass = depth === 0 ? 'ml-4' : 'ml-3';
    const textClass = depth === 0 ? 'text-primary dark:text-gray-300' : 'text-secondary dark:text-gray-400';
    const activeClass = depth === 0
      ? 'bg-accent-10 dark:bg-purple-900/30 text-accent dark:text-purple-300 border-l-4 border-accent dark:border-purple-500'
      : 'bg-accent-10 dark:bg-purple-900/40 text-accent dark:text-purple-300 font-medium';

    return (
      <div key={item.id}>
        <div className="flex items-center justify-between">
          <button
            type="button"
            aria-current={isActive && !hasChildren ? 'page' : undefined}
            onClick={() => {
              if (hasChildren && !isExpanded) {
                toggleExpand(item.id);
              }
              navigateToItem(item);
            }}
            className={`flex-1 rounded-md text-left text-xs transition-colors ${paddingClass} ${depth === 0 ? 'font-medium flex items-center gap-1.5' : ''} ${
              isActive
                ? activeClass
                : hoveredItemId === item.id
                  ? `bg-tertiary dark:hover:bg-gray-700 ${textClass}`
                  : textClass
            }`}
            onMouseEnter={(event) => {
              event.stopPropagation();
              if (!isActive) setHoveredItemId(item.id);
            }}
            onMouseLeave={(event) => {
              event.stopPropagation();
              setHoveredItemId(null);
            }}
          >
            {Icon && <Icon className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />}
            <span id={`settings-navigation-label-${item.id}`}>{t(item.label as any) || item.label}</span>
          </button>
          {hasChildren && (
            <button
              type="button"
              aria-labelledby={`settings-navigation-label-${item.id}`}
              aria-expanded={isExpanded}
              onClick={(event) => {
                event.stopPropagation();
                toggleExpand(item.id);
              }}
              className="rounded-md px-1 py-1.5 transition-colors hover:bg-surface-secondary dark:hover:bg-gray-700"
            >
              <ChevronRight
                className={`h-3 w-3 transition-transform ${isExpanded ? 'rotate-90' : ''}`}
                aria-hidden="true"
              />
            </button>
          )}
        </div>
        {hasChildren ? (
          <div
            className={`${childIndentClass} mt-1 space-y-0.5 overflow-hidden transition-all duration-300 ease-in-out ${
              isExpanded ? 'max-h-[1000px] opacity-100' : 'max-h-0 opacity-0'
            }`}
          >
            {item.children!.map((child) => renderItem(child, depth + 1))}
          </div>
        ) : null}
      </div>
    );
  };

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <nav className="min-h-0 flex-1 space-y-1 overflow-y-auto px-2 pt-2">
        {navigationItems.map((item) => renderItem(item))}
      </nav>
    </div>
  );
}
