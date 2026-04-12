import React from 'react';
import { Lightbulb, Link, Plus, Settings, Users } from 'lucide-react';

export type AccountsTabKey = 'sources' | 'targets' | 'captures' | 'analytics' | 'insights';

export function AccountsTabs(props: {
  activeTab: AccountsTabKey;
  onTabChange: (key: AccountsTabKey) => void;
}) {
  const { activeTab, onTabChange } = props;

  const base =
    'px-3 py-1.5 text-sm font-medium border-b-2 transition-colors whitespace-nowrap';
  const active = 'border-blue-600 text-blue-600 dark:text-blue-400';
  const inactive =
    'border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300';

  return (
    <div className="flex items-center gap-2 overflow-x-auto">
      <button
        onClick={() => onTabChange('sources')}
        className={`${base} ${activeTab === 'sources' ? active : inactive}`}
      >
        <Link className="w-4 h-4 inline mr-1" />
        Sources
      </button>
      <button
        onClick={() => onTabChange('targets')}
        className={`${base} ${activeTab === 'targets' ? active : inactive}`}
      >
        <Users className="w-4 h-4 inline mr-1" />
        Targets
      </button>
      <button
        onClick={() => onTabChange('captures')}
        className={`${base} ${activeTab === 'captures' ? active : inactive}`}
      >
        <Plus className="w-4 h-4 inline mr-1" />
        Captures
      </button>
      <button
        onClick={() => onTabChange('analytics')}
        className={`${base} ${activeTab === 'analytics' ? active : inactive}`}
      >
        <Settings className="w-4 h-4 inline mr-1" />
        Analytics
      </button>
      <button
        onClick={() => onTabChange('insights')}
        className={`${base} ${activeTab === 'insights' ? active : inactive}`}
      >
        <Lightbulb className="w-4 h-4 inline mr-1" />
        Insights
      </button>
    </div>
  );
}
