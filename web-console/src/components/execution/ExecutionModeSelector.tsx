'use client';

import React, { useState, useRef, useEffect } from 'react';

export type ExecutionMode = 'qa' | 'execution' | 'hybrid' | 'meeting';
export type ExecutionPriority = 'low' | 'medium' | 'high';

interface ExecutionModeSelectorProps {
  mode: ExecutionMode;
  priority: ExecutionPriority;
  meetingEnabled?: boolean;
  onChange: (update: { mode?: ExecutionMode; priority?: ExecutionPriority }) => void;
  onMeetingToggle?: (enabled: boolean) => void;
  disabled?: boolean;
}

const modeConfig: Record<ExecutionMode, {
  label: string;
  icon: string;
  description: string;
}> = {
  qa: {
    label: '對話優先',
    icon: '💬',
    description: '對話優先：討論為主',
  },
  execution: {
    label: '執行優先',
    icon: '⚡',
    description: '執行優先：行動為主',
  },
  hybrid: {
    label: '邊做邊聊',
    icon: '🤝',
    description: '邊做邊聊：邊聊邊執行，平衡對話與動作',
  },
  meeting: {
    label: '會議模式',
    icon: '🧭',
    description: '多代理會議：聚焦決策、收斂與行動項',
  },
};

const selectableModes: ExecutionMode[] = ['qa', 'execution', 'hybrid'];

const priorityConfig: Record<ExecutionPriority, {
  label: string;
  indicator: string;
  description: string;
}> = {
  low: {
    label: '低',
    indicator: '▽',
    description: '高信心(>=0.9)才自動執行',
  },
  medium: {
    label: '中',
    indicator: '◇',
    description: '中等信心(>=0.8)觸發',
  },
  high: {
    label: '高',
    indicator: '△',
    description: '較積極(>=0.6)觸發',
  },
};

// Map enum priority to slider numeric value (0.5 - 1.0)
const priorityToValue = (p: ExecutionPriority): number => {
  if (p === 'high') return 1.0;
  if (p === 'medium') return 0.8;
  return 0.6;
};

// Map slider numeric value back to enum (thresholds chosen to keep backward compatibility)
const valueToPriority = (v: number): ExecutionPriority => {
  if (v >= 0.9) return 'high';
  if (v >= 0.7) return 'medium';
  return 'low';
};

export default function ExecutionModeSelector({
  mode,
  priority,
  meetingEnabled = true,
  onChange,
  onMeetingToggle,
  disabled = false,
}: ExecutionModeSelectorProps) {
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const [priorityValue, setPriorityValue] = useState<number>(priorityToValue(priority));

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

  // Sync slider with external priority
  useEffect(() => {
    setPriorityValue(priorityToValue(priority));
  }, [priority]);

  // Close dropdown when mode changes externally (e.g., from workspace update)
  useEffect(() => {
    if (isOpen) {
      // Optionally close dropdown when mode changes, or keep it open
      // For now, keep it open to allow smooth transitions
    }
  }, [mode, priority]);

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
        title={currentMode.description}
      >
        {/* Priority numeric value + indicator */}
        <span className="text-[11px] font-semibold text-purple-700 dark:text-purple-300">
          {priorityValue.toFixed(1)}
        </span>
        <span className={`text-[10px] ${priority === 'high' ? 'text-amber-500' :
          priority === 'medium' ? 'text-gray-500 dark:text-gray-400' :
            'text-gray-400 dark:text-gray-500'
          }`}>
          {currentPriority.indicator}
        </span>
        <span className="text-gray-600 dark:text-gray-400">AI Team</span>
        <span className="text-gray-700 dark:text-gray-300">{currentMode.label}</span>
        {/* More prominent dropdown indicator */}
        <span className="ml-auto text-gray-500 dark:text-gray-400 text-[10px] font-bold">▼</span>
      </button>

      {/* Dropdown menu */}
      {isOpen && (
        <div
          className="absolute top-full left-0 mt-1 z-50 min-w-[200px] bg-surface-secondary dark:bg-gray-800 rounded-lg shadow-lg border border-default dark:border-gray-700 py-2"
          style={{ animation: 'fadeIn 0.15s ease' }}
        >
          {/* Mode section */}
          <div className="px-3 py-1 text-[10px] font-semibold text-gray-400 uppercase tracking-wider">
            模式
          </div>
          {selectableModes.map((m) => (
            <button
              key={m}
              onClick={() => {
                onChange({ mode: m });
                setIsOpen(false);
              }}
              title={modeConfig[m].description}
              className={`
                w-full px-3 py-1.5 text-left text-sm flex items-center gap-2
                hover:bg-accent-10 dark:hover:bg-purple-900/20
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

          {/* Meeting toggle */}
          <div className="px-3 py-1.5 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="text-sm">🧭</span>
              <span className="text-sm text-gray-700 dark:text-gray-300">會議引擎</span>
            </div>
            <button
              onClick={() => onMeetingToggle?.(!meetingEnabled)}
              className={`
                relative w-9 h-5 rounded-full transition-colors duration-200
                ${meetingEnabled
                  ? 'bg-purple-500'
                  : 'bg-gray-300 dark:bg-gray-600'
                }
              `}
            >
              <span
                className={`
                  absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white shadow
                  transition-transform duration-200
                  ${meetingEnabled ? 'translate-x-4' : 'translate-x-0'}
                `}
              />
            </button>
          </div>

          {/* Divider */}
          <div className="my-2 border-t border-gray-100 dark:border-gray-700" />

          {/* Priority section */}
          <div className="px-3 py-1 text-[10px] font-semibold text-gray-400 uppercase tracking-wider flex items-center gap-2">
            <span>任務自動觸發（信心度）</span>
            <span className="text-purple-700 dark:text-purple-300 text-[11px] font-bold">
              {priorityValue.toFixed(1)}
            </span>
          </div>
          <div className="px-3 py-2">
            <div className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400 mb-1">
              <span>0.5</span>
              <div className="flex-1 h-px bg-gray-200 dark:bg-gray-700" />
              <span>1.0</span>
            </div>
            <input
              type="range"
              min={0.5}
              max={1.0}
              step={0.1}
              value={priorityValue}
              onChange={(e) => {
                const v = parseFloat(e.target.value);
                setPriorityValue(v);
                onChange({ priority: valueToPriority(v) });
              }}
              className="w-full accent-purple-600"
            />
            <div className="flex justify-between text-[10px] text-gray-400 dark:text-gray-500 mt-1">
              {[0.5, 0.6, 0.7, 0.8, 0.9, 1.0].map(v => (
                <span key={v}>{v.toFixed(1)}</span>
              ))}
            </div>
            <div className="mt-1 text-xs text-purple-700 dark:text-purple-300 font-medium">
              {priorityValue.toFixed(1)} ・ {priorityConfig[valueToPriority(priorityValue)].label}
            </div>
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
