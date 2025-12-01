'use client';

import React from 'react';

interface VersionSelectorProps {
  hasPersonalVariant: boolean;
  defaultVariant?: {
    variant_name: string;
  };
  systemVersion: string;
  selectedVersion: 'system' | 'personal';
  onVersionChange: (version: 'system' | 'personal') => void;
  onCopyClick: () => void;
  onLLMClick: () => void;
  activeExecutionsCount?: number;
}

export default function VersionSelector({
  hasPersonalVariant,
  defaultVariant,
  systemVersion,
  selectedVersion,
  onVersionChange,
  onCopyClick,
  onLLMClick,
  activeExecutionsCount = 0
}: VersionSelectorProps) {
  return (
    <div className="bg-white shadow rounded-lg p-6">
      <h3 className="text-lg font-semibold text-gray-900 mb-4">目前執行版本</h3>

      {!hasPersonalVariant ? (
        // No personal variant yet
        <div className="space-y-3">
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="radio"
              name="version"
              value="system"
              checked={selectedVersion === 'system'}
              onChange={() => onVersionChange('system')}
              className="w-4 h-4"
            />
            <span className="text-sm">系統版本（v{systemVersion}）</span>
          </label>
          <label className="flex items-center gap-2 cursor-pointer opacity-50">
            <input
              type="radio"
              name="version"
              value="personal"
              disabled
              className="w-4 h-4"
            />
            <span className="text-sm">我的版本（尚未建立）</span>
          </label>

          <div className="mt-4 pt-4 border-t border-gray-200">
            <p className="text-xs text-gray-500 mb-3">
              你還沒有個人版本，可以讓 LLM 幫你生成：
            </p>
            <div className="flex flex-col gap-2">
              <button
                onClick={onCopyClick}
                className="px-3 py-2 text-xs text-gray-700 hover:text-gray-900 border border-gray-300 rounded hover:bg-gray-50"
              >
                直接複製為我的版本
              </button>
              <button
                onClick={onLLMClick}
                className="px-3 py-2 text-xs text-blue-600 hover:text-blue-800 border border-blue-300 rounded hover:bg-blue-50"
              >
                請 LLM 幫我客製化
              </button>
            </div>
          </div>
        </div>
      ) : (
        // Has personal variant
        <div className="space-y-3">
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="radio"
              name="version"
              value="personal"
              checked={selectedVersion === 'personal'}
              onChange={() => onVersionChange('personal')}
              className="w-4 h-4"
            />
            <span className="text-sm font-medium">
              我的版本：{defaultVariant?.variant_name || '我的版本'}
            </span>
          </label>
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="radio"
              name="version"
              value="system"
              checked={selectedVersion === 'system'}
              onChange={() => onVersionChange('system')}
              className="w-4 h-4"
            />
            <span className="text-sm">系統版本（v{systemVersion}）</span>
          </label>

          <div className="mt-4 pt-4 border-t border-gray-200 flex gap-2">
            <button
              onClick={() => {/* TODO: Show diff */}}
              className="flex-1 px-3 py-2 text-xs text-gray-700 hover:text-gray-900 border border-gray-300 rounded hover:bg-gray-50"
            >
              查看差異
            </button>
            <button
              onClick={onLLMClick}
              className="flex-1 px-3 py-2 text-xs text-blue-600 hover:text-blue-800 border border-blue-300 rounded hover:bg-blue-50"
            >
              重新用 LLM 調整
            </button>
          </div>
        </div>
      )}

      {/* Execution Status Summary */}
      <div className="mt-6 pt-6 border-t border-gray-200">
        <h4 className="text-sm font-medium text-gray-700 mb-2">執行狀態</h4>
        {activeExecutionsCount > 0 ? (
          <div className="space-y-1">
            <p className="text-xs text-green-600 font-medium">
              🔄 {activeExecutionsCount} 個執行中
            </p>
            <p className="text-xs text-gray-500">
              此 Playbook 目前正在運行
            </p>
          </div>
        ) : (
          <div>
            <p className="text-xs text-gray-500">尚無執行記錄</p>
            <p className="text-xs text-gray-400 mt-1">此 Playbook 目前未在運行</p>
          </div>
        )}
      </div>
    </div>
  );
}
