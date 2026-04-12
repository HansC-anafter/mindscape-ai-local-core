import React from 'react';
import { Grid3x3 } from 'lucide-react';

import type { WorkbenchModuleType } from '../types';
import { WORKBENCH_MODULES } from '../moduleRegistry';
import type { IGVisionExecutionMode } from '../../visionExecution';

export function WorkbenchSidebar(props: {
  activeModule: WorkbenchModuleType | null;
  onModuleChange: (module: WorkbenchModuleType | null) => void;
  visionExecutionMode: IGVisionExecutionMode;
  visionExecutionModeSaving?: boolean;
  onVisionExecutionModeChange: (mode: IGVisionExecutionMode) => void;
}) {
  const {
    activeModule,
    onModuleChange,
    visionExecutionMode,
    visionExecutionModeSaving = false,
    onVisionExecutionModeChange,
  } = props;

  return (
    <div className="w-64 border-r dark:border-gray-700 bg-gray-50 dark:bg-gray-900 flex flex-col">
      <div className="p-4 border-b dark:border-gray-700">
        <h2 className="text-lg font-bold text-gray-900 dark:text-gray-100 mb-1">
          IG Workbench
        </h2>
        <p className="text-xs text-gray-500 dark:text-gray-400">
          Content Pipeline Control Panel
        </p>
      </div>
      <div className="flex-1 overflow-y-auto p-2">
        {activeModule && (
          <>
            <button
              onClick={() => onModuleChange(null)}
              className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg mb-2 transition-colors bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600 border border-gray-200 dark:border-gray-600"
            >
              <Grid3x3 className="w-5 h-5" />
              <span className="text-sm font-medium">Back to Content</span>
            </button>
            <div className="h-px bg-gray-200 dark:bg-gray-700 mb-2" />
          </>
        )}

        {WORKBENCH_MODULES.map((module) => {
          const Icon = module.icon;
          const isActive = activeModule === module.id;
          return (
            <button
              key={module.id}
              onClick={() => onModuleChange(module.id)}
              className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg mb-1 transition-colors ${
                isActive
                  ? 'bg-blue-50 dark:bg-blue-900/20 text-blue-600 dark:text-blue-400'
                  : 'text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700'
              }`}
            >
              <Icon className="w-5 h-5" />
              <span className="text-sm font-medium">{module.label}</span>
            </button>
          );
        })}
      </div>

      <div className="p-3 border-t dark:border-gray-700">
        <div className="text-[11px] font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400 mb-2">
          Vision Analyze
        </div>
        <div className="grid grid-cols-2 gap-2">
          <button
            onClick={() => onVisionExecutionModeChange('local')}
            disabled={visionExecutionModeSaving}
            className={`px-3 py-2 text-xs font-medium rounded-lg border transition-colors ${
              visionExecutionMode === 'local'
                ? 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300 border-green-400/40 dark:border-green-700'
                : 'bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 border-gray-200 dark:border-gray-600 hover:bg-gray-100 dark:hover:bg-gray-700'
            } ${visionExecutionModeSaving ? 'opacity-70 cursor-wait' : ''}`}
          >
            本地
          </button>
          <button
            onClick={() => onVisionExecutionModeChange('cloud')}
            disabled={visionExecutionModeSaving}
            className={`px-3 py-2 text-xs font-medium rounded-lg border transition-colors ${
              visionExecutionMode === 'cloud'
                ? 'bg-sky-100 dark:bg-sky-900/30 text-sky-700 dark:text-sky-300 border-sky-400/40 dark:border-sky-700'
                : 'bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 border-gray-200 dark:border-gray-600 hover:bg-gray-100 dark:hover:bg-gray-700'
            } ${visionExecutionModeSaving ? 'opacity-70 cursor-wait' : ''}`}
          >
            雲端 VM
          </button>
        </div>
        <p className="mt-2 text-[11px] leading-relaxed text-gray-500 dark:text-gray-400">
          只切換 IG 參考圖分析的執行位置；本地走工作站，雲端走 remote executor。
        </p>
        {visionExecutionModeSaving && (
          <p className="mt-1 text-[11px] text-gray-400 dark:text-gray-500">
            正在更新執行策略…
          </p>
        )}
      </div>
    </div>
  );
}
