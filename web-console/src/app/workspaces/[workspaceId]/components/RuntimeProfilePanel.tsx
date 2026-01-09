'use client';

import React, { useState, useEffect } from 'react';

interface RuntimeProfilePanelProps {
  workspaceId: string;
  apiUrl: string;
  onUpdate?: () => void;
}

interface Preset {
  name: string;
  label: string;
  description: string;
  icon: string;
}

interface RuntimeProfile {
  workspace_id: string;
  default_mode?: string;
  interaction_budget?: any;
  output_contract?: any;
  confirmation_policy?: any;
  tool_policy?: any;
  loop_budget?: any;
  stop_conditions?: any;
  quality_gates?: any;
  topology_routing?: any;
}

export default function RuntimeProfilePanel({
  workspaceId,
  apiUrl,
  onUpdate
}: RuntimeProfilePanelProps) {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [presets, setPresets] = useState<Preset[]>([]);
  const [selectedPreset, setSelectedPreset] = useState<string | null>(null);
  const [profile, setProfile] = useState<RuntimeProfile | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [showPreview, setShowPreview] = useState(false);

  // Load presets
  useEffect(() => {
    const loadPresets = async () => {
      try {
        const response = await fetch(`${apiUrl}/api/v1/workspaces/runtime-profile/presets`);
        if (response.ok) {
          const data = await response.json();
          setPresets(data.presets || []);
        }
      } catch (err) {
        console.error('Failed to load presets:', err);
      }
    };
    loadPresets();
  }, [apiUrl]);

  // Load current profile
  useEffect(() => {
    const loadProfile = async () => {
      try {
        setLoading(true);
        const response = await fetch(`${apiUrl}/api/v1/workspaces/${workspaceId}/runtime-profile`);
        if (response.ok) {
          const data = await response.json();
          setProfile(data);
        } else if (response.status === 404) {
          // Profile doesn't exist yet, will use default
          setProfile(null);
        }
      } catch (err) {
        console.error('Failed to load profile:', err);
        setError('Failed to load runtime profile');
      } finally {
        setLoading(false);
      }
    };
    loadProfile();
  }, [workspaceId, apiUrl]);

  const handleApplyPreset = async (presetName: string) => {
    try {
      setSaving(true);
      setError(null);
      setSuccess(false);

      const response = await fetch(
        `${apiUrl}/api/v1/workspaces/${workspaceId}/runtime-profile/apply-preset`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ preset_name: presetName }),
        }
      );

      if (response.ok) {
        const updatedProfile = await response.json();
        setProfile(updatedProfile);
        setSelectedPreset(presetName);
        setSuccess(true);
        setTimeout(() => setSuccess(false), 3000);
        if (onUpdate) {
          onUpdate();
        }
      } else {
        const errorData = await response.json();
        setError(errorData.detail || 'Failed to apply preset');
      }
    } catch (err) {
      console.error('Failed to apply preset:', err);
      setError('Failed to apply preset');
    } finally {
      setSaving(false);
    }
  };

  const handleResetToDefault = async () => {
    try {
      setSaving(true);
      setError(null);
      setSuccess(false);

      // Delete current profile to reset to default
      const deleteResponse = await fetch(
        `${apiUrl}/api/v1/workspaces/${workspaceId}/runtime-profile`,
        {
          method: 'DELETE',
        }
      );

      if (deleteResponse.ok || deleteResponse.status === 404) {
        // Reload profile (will return default)
        const getResponse = await fetch(
          `${apiUrl}/api/v1/workspaces/${workspaceId}/runtime-profile`
        );
        if (getResponse.ok) {
          const defaultProfile = await getResponse.json();
          setProfile(defaultProfile);
          setSelectedPreset(null);
          setSuccess(true);
          setTimeout(() => setSuccess(false), 3000);
          if (onUpdate) {
            onUpdate();
          }
        }
      } else {
        setError('Failed to reset to default');
      }
    } catch (err) {
      console.error('Failed to reset:', err);
      setError('Failed to reset to default');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="p-4">
        <div className="animate-pulse">
          <div className="h-4 bg-gray-200 rounded w-1/4 mb-4"></div>
          <div className="h-20 bg-gray-200 rounded"></div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
          運行時配置 (Runtime Profile)
        </h3>
        <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
          配置工作區的執行契約和操作策略
        </p>
      </div>

      {/* Preset Templates */}
      <div>
        <h4 className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-3">
          預設模板
        </h4>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {presets.map((preset) => (
            <div
              key={preset.name}
              className={`border rounded-lg p-4 cursor-pointer transition-all ${
                selectedPreset === preset.name
                  ? 'border-blue-500 bg-blue-50 dark:bg-blue-900/20'
                  : 'border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600'
              }`}
              onClick={() => handleApplyPreset(preset.name)}
            >
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-2xl">{preset.icon}</span>
                    <h5 className="font-medium text-gray-900 dark:text-gray-100">
                      {preset.label}
                    </h5>
                  </div>
                  <p className="text-sm text-gray-600 dark:text-gray-400">
                    {preset.description}
                  </p>
                </div>
                {selectedPreset === preset.name && (
                  <svg
                    className="w-5 h-5 text-blue-500"
                    fill="currentColor"
                    viewBox="0 0 20 20"
                  >
                    <path
                      fillRule="evenodd"
                      d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
                      clipRule="evenodd"
                    />
                  </svg>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Actions */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowPreview(!showPreview)}
            className="px-4 py-2 text-sm text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
          >
            {showPreview ? '隱藏預覽' : '顯示預覽'}
          </button>
          <button
            onClick={handleResetToDefault}
            disabled={saving}
            className="px-4 py-2 text-sm text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {saving ? '重置中...' : '重置為預設值'}
          </button>
        </div>
      </div>

      {/* Preview */}
      {showPreview && profile && (
        <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-4 bg-gray-50 dark:bg-gray-800/50">
          <h4 className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-3">
            配置預覽
          </h4>
          <pre className="text-xs text-gray-600 dark:text-gray-400 overflow-auto max-h-96">
            {JSON.stringify(profile, null, 2)}
          </pre>
        </div>
      )}

      {/* Success Message */}
      {success && (
        <div className="bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg p-4">
          <div className="flex items-start">
            <svg
              className="h-5 w-5 text-green-400"
              viewBox="0 0 20 20"
              fill="currentColor"
            >
              <path
                fillRule="evenodd"
                d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
                clipRule="evenodd"
              />
            </svg>
            <div className="ml-3 flex-1">
              <p className="text-sm text-green-700 dark:text-green-300">
                配置已成功更新
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Error Message */}
      {error && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4">
          <div className="flex items-start">
            <svg
              className="h-5 w-5 text-red-400"
              viewBox="0 0 20 20"
              fill="currentColor"
            >
              <path
                fillRule="evenodd"
                d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z"
                clipRule="evenodd"
              />
            </svg>
            <div className="ml-3 flex-1">
              <p className="text-sm text-red-700 dark:text-red-300">{error}</p>
            </div>
            <button
              onClick={() => setError(null)}
              className="ml-3 text-red-400 hover:text-red-500"
            >
              <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                <path
                  fillRule="evenodd"
                  d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z"
                  clipRule="evenodd"
                />
              </svg>
            </button>
          </div>
        </div>
      )}
    </div>
  );
}


