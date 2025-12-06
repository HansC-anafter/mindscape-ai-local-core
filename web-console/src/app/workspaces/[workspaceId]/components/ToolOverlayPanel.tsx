'use client';

import React, { useState, useEffect } from 'react';
import { useToolOverlay, ToolWithOverlay } from '@/hooks/useToolOverlay';
import ToolWhitelistEditor from './ToolWhitelistEditor';
import ToolDangerLevelOverride from './ToolDangerLevelOverride';
import { t } from '@/lib/i18n';

interface ToolOverlayPanelProps {
  workspaceId: string;
}

export default function ToolOverlayPanel({ workspaceId }: ToolOverlayPanelProps) {
  const {
    overlay,
    loading,
    error,
    tools,
    loadTools,
    updateOverlay,
    validateDangerLevel,
  } = useToolOverlay(workspaceId);

  const [toolWhitelist, setToolWhitelist] = useState<string[]>([]);
  const [dangerLevelOverride, setDangerLevelOverride] = useState<'low' | 'medium' | 'high' | null>(null);
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saveSuccess, setSaveSuccess] = useState(false);

  useEffect(() => {
    loadTools();
  }, [loadTools]);

  useEffect(() => {
    if (overlay) {
      setToolWhitelist(overlay.tool_whitelist || []);
      setDangerLevelOverride(overlay.danger_level_override || null);
      setEnabled(overlay.enabled !== undefined ? overlay.enabled : null);
    } else {
      setToolWhitelist([]);
      setDangerLevelOverride(null);
      setEnabled(null);
    }
  }, [overlay]);

  const handleSave = async () => {
    setSaving(true);
    setSaveError(null);
    setSaveSuccess(false);

    try {
      await updateOverlay({
        tool_whitelist: toolWhitelist.length > 0 ? toolWhitelist : undefined,
        danger_level_override: dangerLevelOverride || undefined,
        enabled: enabled !== null ? enabled : undefined,
      });

      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 3000);
      await loadTools();
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : 'Failed to update tool overlay');
    } finally {
      setSaving(false);
    }
  };

  const availableTools: Array<{ tool_id: string; tool_name: string; danger_level: 'low' | 'medium' | 'high' }> = tools.map(tool => ({
    tool_id: tool.tool_id,
    tool_name: tool.tool_name,
    danger_level: tool.original_danger_level,
  }));

  const hasChanges = () => {
    if (!overlay) {
      return toolWhitelist.length > 0 || dangerLevelOverride !== null || enabled !== null;
    }
    return (
      JSON.stringify(toolWhitelist.sort()) !== JSON.stringify((overlay.tool_whitelist || []).sort()) ||
      dangerLevelOverride !== (overlay.danger_level_override || null) ||
      enabled !== (overlay.enabled !== undefined ? overlay.enabled : null)
    );
  };

  if (loading && !overlay) {
    return (
      <div className="p-4">
        <div className="text-gray-500 dark:text-gray-400">Loading tool overlay...</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-2">
          {t('toolOverlaySettings')}
        </h3>
        <p className="text-sm text-gray-600 dark:text-gray-400">
          {t('toolOverlayDescription')}
        </p>
      </div>

      {error && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-3">
          <p className="text-sm text-red-700 dark:text-red-300">{error}</p>
        </div>
      )}

      <div className="space-y-6">
        <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg p-4">
          <ToolWhitelistEditor
            availableTools={availableTools}
            selectedToolIds={toolWhitelist}
            onSelectionChange={setToolWhitelist}
          />
        </div>

        <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg p-4">
          <ToolDangerLevelOverride
            originalDangerLevel="medium"
            currentOverride={dangerLevelOverride || undefined}
            onOverrideChange={(override) => setDangerLevelOverride(override)}
            validateDangerLevel={validateDangerLevel}
          />
        </div>

        <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg p-4">
          <div className="space-y-2">
            <h4 className="text-sm font-medium text-gray-900 dark:text-gray-100">
              Enable/Disable Tools
            </h4>
            <p className="text-xs text-gray-500 dark:text-gray-400">
              Control whether tools are enabled in this workspace
            </p>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={enabled !== null ? enabled : true}
                onChange={(e) => setEnabled(e.target.checked)}
                className="rounded border-gray-300 dark:border-gray-600 text-blue-600 focus:ring-blue-500"
              />
              <span className="text-sm text-gray-700 dark:text-gray-300">
                Enable tools in this workspace
              </span>
            </label>
          </div>
        </div>
      </div>

      {saveError && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-3">
          <p className="text-sm text-red-700 dark:text-red-300">{saveError}</p>
        </div>
      )}

      {saveSuccess && (
        <div className="bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg p-3">
          <p className="text-sm text-green-700 dark:text-green-300">{t('toolOverlaySaved')}</p>
        </div>
      )}

      <div className="flex justify-end">
          <button
            onClick={handleSave}
            disabled={saving || !hasChanges()}
            className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors"
          >
            {saving ? t('saving') : t('saveSettings')}
          </button>
      </div>
    </div>
  );
}

