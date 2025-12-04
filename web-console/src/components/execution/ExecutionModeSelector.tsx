'use client';

import React, { useState, useRef, useEffect } from 'react';

export type ExecutionMode = 'qa' | 'execution' | 'hybrid';
export type ExecutionPriority = 'low' | 'medium' | 'high';

interface ExecutionModeSelectorProps {
  mode: ExecutionMode;
  priority: ExecutionPriority;
  onChange: (update: { mode?: ExecutionMode; priority?: ExecutionPriority }) => void;
  disabled?: boolean;
}

const modeConfig: Record<ExecutionMode, {
  label: string;
  icon: string;
  description: string;
}> = {
  qa: {
    label: '對話模式',
    icon: '💬',
    description: '對話模式：討論為主',
  },
  execution: {
    label: '協作模式',
    icon: '⚡',
    description: '協作模式：行動優先',
  },
  hybrid: {
    label: '混合模式',
    icon: '🔄',
    description: '混合模式：平衡兩者',
  },
};

const priorityConfig: Record<ExecutionPriority, {
  label: string;
  indicator: string;
  description: string;
}> = {
  low: {
    label: '低',
    indicator: '▽',
    description: '謹慎執行',
  },
  medium: {
    label: '中',
    indicator: '◇',
    description: '平衡',
  },
  high: {
    label: '高',
    indicator: '△',
    description: '積極執行',
  },
};

export default function ExecutionModeSelector({
  mode,
  priority,
  onChange,
  disabled = false,
}: ExecutionModeSelectorProps) {
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const currentMode = modeConfig[mode];
  const currentPriority = priorityConfig[priority];

  return (
    <div className="relative" ref={dropdownRef}>
{/* Trigger button */}
      <button
        onClick={() => !disabled && setIsOpen(!isOpen)}
        disabled={disabled}
        className={`
          flex items-center gap-1.5 px-2 py-1 rounded-lg text-xs font-medium
          transition-all duration-200
          ${disabled
            ? 'opacity-50 cursor-not-allowed'
            : 'cursor-pointer hover:opacity-80'
          }
        `}
        style={{
          background: 'rgba(139, 92, 246, 0.05)',
          border: '1px solid rgba(139, 92, 246, 0.15)',
        }}
      >
        {/* Priority indicator - moved to front */}
        <span className={`text-[10px] ${
          priority === 'high' ? 'text-amber-500' :
          priority === 'medium' ? 'text-gray-500 dark:text-gray-400' :
          'text-gray-400 dark:text-gray-500'
        }`}>
          {currentPriority.indicator}
        </span>
        <span className="text-gray-600 dark:text-gray-400">AI Team</span>
        <span>{currentMode.icon}</span>
        <span className="text-gray-700 dark:text-gray-300">{currentMode.label}</span>
        {/* More prominent dropdown indicator */}
        <span className="ml-auto text-gray-500 dark:text-gray-400 text-[10px] font-bold">▼</span>
      </button>

      {/* Dropdown menu */}
      {isOpen && (
        <div
          className="absolute top-full left-0 mt-1 z-50 min-w-[200px] bg-white dark:bg-gray-800 rounded-lg shadow-lg border border-gray-200 dark:border-gray-700 py-2"
          style={{ animation: 'fadeIn 0.15s ease' }}
        >
          {/* Mode section */}
          <div className="px-3 py-1 text-[10px] font-semibold text-gray-400 uppercase tracking-wider">
            模式
          </div>
          {(Object.keys(modeConfig) as ExecutionMode[]).map((m) => (
            <button
              key={m}
              onClick={() => {
                onChange({ mode: m });
                setIsOpen(false);
              }}
              className={`
                w-full px-3 py-1.5 text-left text-sm flex items-center gap-2
                hover:bg-purple-50 dark:hover:bg-purple-900/20
                ${mode === m ? 'text-purple-600 dark:text-purple-400' : 'text-gray-700 dark:text-gray-300'}
              `}
            >
              <span>{modeConfig[m].icon}</span>
              <span>{modeConfig[m].label}</span>
              {mode === m && <span className="ml-auto">✓</span>}
            </button>
          ))}

          {/* Divider */}
          <div className="my-2 border-t border-gray-100 dark:border-gray-700" />

          {/* Priority section */}
          <div className="px-3 py-1 text-[10px] font-semibold text-gray-400 uppercase tracking-wider">
            執行優先級
          </div>
          <div className="px-3 py-1.5 flex gap-2">
            {(Object.keys(priorityConfig) as ExecutionPriority[]).map((p) => (
              <button
                key={p}
                onClick={() => onChange({ priority: p })}
                className={`
                  flex-1 px-2 py-1 rounded text-xs font-medium transition-all
                  ${priority === p
                    ? 'bg-purple-100 dark:bg-purple-900/40 text-purple-700 dark:text-purple-300 border border-purple-300 dark:border-purple-700'
                    : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400 border border-transparent hover:border-gray-300 dark:hover:border-gray-600'
                  }
                `}
                title={priorityConfig[p].description}
              >
                {priorityConfig[p].label} {priorityConfig[p].indicator}
              </button>
            ))}
          </div>
        </div>
      )}

      <style jsx>{`
        @keyframes fadeIn {
          from { opacity: 0; transform: translateY(-4px); }
          to { opacity: 1; transform: translateY(0); }
        }
      `}</style>
    </div>
  );
}

