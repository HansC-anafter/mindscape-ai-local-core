'use client';

import React, { useState, useEffect } from 'react';
import { t } from '@/lib/i18n';

interface Tool {
  tool_id: string;
  tool_name: string;
  danger_level: 'low' | 'medium' | 'high';
}

interface ToolWhitelistEditorProps {
  availableTools: Tool[];
  selectedToolIds: string[];
  onSelectionChange: (toolIds: string[]) => void;
}

export default function ToolWhitelistEditor({
  availableTools,
  selectedToolIds,
  onSelectionChange,
}: ToolWhitelistEditorProps) {
  const [searchTerm, setSearchTerm] = useState('');

  const filteredTools = availableTools.filter(tool =>
    tool.tool_name.toLowerCase().includes(searchTerm.toLowerCase()) ||
    tool.tool_id.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const handleToggleTool = (toolId: string) => {
    if (selectedToolIds.includes(toolId)) {
      onSelectionChange(selectedToolIds.filter(id => id !== toolId));
    } else {
      onSelectionChange([...selectedToolIds, toolId]);
    }
  };

  const handleSelectAll = () => {
    onSelectionChange(filteredTools.map(tool => tool.tool_id));
  };

  const handleDeselectAll = () => {
    const filteredIds = filteredTools.map(tool => tool.tool_id);
    onSelectionChange(selectedToolIds.filter(id => !filteredIds.includes(id)));
  };

  const getDangerLevelColor = (level: string) => {
    switch (level) {
      case 'low':
        return 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300';
      case 'medium':
        return 'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-300';
      case 'high':
        return 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300';
      default:
        return 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300';
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h4 className="text-sm font-medium text-gray-900 dark:text-gray-100">
            {t('toolWhitelist' as any)}
          </h4>
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
            {t('toolWhitelistDescription' as any)}
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={handleSelectAll}
            className="px-2 py-1 text-xs text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300"
          >
            {t('selectAll' as any)}
          </button>
          <button
            onClick={handleDeselectAll}
            className="px-2 py-1 text-xs text-gray-600 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300"
          >
            {t('deselectAll' as any)}
          </button>
        </div>
      </div>

      <div>
        <input
          type="text"
          placeholder={t('searchTools' as any)}
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 text-sm"
        />
      </div>

      <div className="max-h-64 overflow-y-auto border border-gray-200 dark:border-gray-700 rounded-md">
        {filteredTools.length === 0 ? (
          <div className="p-4 text-center text-sm text-gray-500 dark:text-gray-400">
            {t('noToolsFound' as any)}
          </div>
        ) : (
          <div className="divide-y divide-gray-200 dark:divide-gray-700">
            {filteredTools.map((tool) => (
              <label
                key={tool.tool_id}
                className="flex items-center gap-3 p-3 hover:bg-gray-50 dark:hover:bg-gray-800 cursor-pointer"
              >
                <input
                  type="checkbox"
                  checked={selectedToolIds.includes(tool.tool_id)}
                  onChange={() => handleToggleTool(tool.tool_id)}
                  className="rounded border-gray-300 dark:border-gray-600 text-blue-600 focus:ring-blue-500"
                />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">
                      {tool.tool_name}
                    </span>
                    <span className={`text-xs px-2 py-0.5 rounded ${getDangerLevelColor(tool.danger_level)}`}>
                      {tool.danger_level.toUpperCase()}
                    </span>
                  </div>
                  <span className="text-xs text-gray-500 dark:text-gray-400 truncate block">
                    {tool.tool_id}
                  </span>
                </div>
              </label>
            ))}
          </div>
        )}
      </div>

      <div className="text-xs text-gray-500 dark:text-gray-400">
        {selectedToolIds.length === 0 ? (
          <span>{t('allToolsAllowed' as any)}</span>
        ) : (
          <span>{t('toolsSelected' as any, { count: String(selectedToolIds.length) })}</span>
        )}
      </div>
    </div>
  );
}

