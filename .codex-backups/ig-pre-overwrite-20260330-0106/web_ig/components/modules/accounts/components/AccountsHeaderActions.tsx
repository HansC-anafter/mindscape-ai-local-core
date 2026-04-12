import React from 'react';
import { Grid3x3, List, Plus, Users } from 'lucide-react';

import type { AccountsTabKey } from './AccountsTabs';

export function AccountsHeaderActions(props: {
  activeTab: AccountsTabKey;
  targetsViewMode: 'grid' | 'list';
  onTargetsViewModeChange: (mode: 'grid' | 'list') => void;
  onOpenFollowingAnalyzer: () => void;
  onOpenImportDialog: () => void;
}) {
  const {
    activeTab,
    targetsViewMode,
    onTargetsViewModeChange,
    onOpenFollowingAnalyzer,
    onOpenImportDialog,
  } = props;

  return (
    <div className="flex items-center gap-2 shrink-0">
      {activeTab === 'targets' && (
        <div className="flex items-center gap-1">
          <button
            onClick={() => onTargetsViewModeChange('grid')}
            className={`p-1.5 rounded ${
              targetsViewMode === 'grid'
                ? 'bg-gray-200 dark:bg-gray-700'
                : 'hover:bg-gray-100 dark:hover:bg-gray-800'
            }`}
            title="Grid"
          >
            <Grid3x3 className="w-4 h-4 text-gray-700 dark:text-gray-200" />
          </button>
          <button
            onClick={() => onTargetsViewModeChange('list')}
            className={`p-1.5 rounded ${
              targetsViewMode === 'list'
                ? 'bg-gray-200 dark:bg-gray-700'
                : 'hover:bg-gray-100 dark:hover:bg-gray-800'
            }`}
            title="List"
          >
            <List className="w-4 h-4 text-gray-700 dark:text-gray-200" />
          </button>
        </div>
      )}

      {activeTab === 'captures' && (
        <>
          <button
            onClick={onOpenFollowingAnalyzer}
            className="px-2.5 py-1.5 text-xs bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-200 rounded hover:bg-gray-200 dark:hover:bg-gray-600 flex items-center gap-2"
          >
            <Users className="w-3.5 h-3.5" />
            Following Analyzer
          </button>
          <button
            onClick={onOpenImportDialog}
            className="px-2.5 py-1.5 text-xs bg-blue-600 text-white rounded hover:bg-blue-700 flex items-center gap-2"
          >
            <Plus className="w-3.5 h-3.5" />
            Import Accounts
          </button>
        </>
      )}
    </div>
  );
}

