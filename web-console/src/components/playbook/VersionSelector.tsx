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
    <div className="flex items-center gap-6">
      <h3 className="text-sm font-semibold text-gray-900 whitespace-nowrap">目前執行版本</h3>

      <div className="flex items-center gap-4 flex-1">
        {!hasPersonalVariant ? (
          <>
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
            <div className="flex items-center gap-2 ml-auto">
              <button
                onClick={onCopyClick}
                className="px-3 py-1.5 text-xs text-gray-700 hover:text-gray-900 border border-gray-300 rounded hover:bg-gray-50"
              >
                直接複製
              </button>
              <button
                onClick={onLLMClick}
                className="px-3 py-1.5 text-xs text-blue-600 hover:text-blue-800 border border-blue-300 rounded hover:bg-blue-50"
              >
                LLM 客製化
              </button>
            </div>
          </>
        ) : (
          <>
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
            <div className="flex items-center gap-2 ml-auto">
              <button
                onClick={() => {/* TODO: Show diff */}}
                className="px-3 py-1.5 text-xs text-gray-700 hover:text-gray-900 border border-gray-300 rounded hover:bg-gray-50"
              >
                查看差異
              </button>
              <button
                onClick={onLLMClick}
                className="px-3 py-1.5 text-xs text-blue-600 hover:text-blue-800 border border-blue-300 rounded hover:bg-blue-50"
              >
                重新調整
              </button>
            </div>
          </>
        )}
      </div>

      {/* Execution Status Summary */}
      <div className="flex items-center gap-4">
        {activeExecutionsCount > 0 ? (
          <div className="flex items-center gap-2">
            <span className="inline-block w-2 h-2 bg-green-500 rounded-full animate-pulse"></span>
            <span className="text-xs text-green-600 font-medium">
              {activeExecutionsCount} 個執行中
            </span>
          </div>
        ) : (
          <span className="text-xs text-gray-500">尚無執行記錄</span>
        )}
      </div>
    </div>
  );
}
