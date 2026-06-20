'use client';

import type { AgentMode, CliAgent } from './types';

interface ModeSwitcherProps {
  agent: CliAgent;
  activeMode: AgentMode;
  onModeChange: (mode: AgentMode) => void;
}

export function ModeSwitcher({ agent, activeMode, onModeChange }: ModeSwitcherProps) {
  return (
    <div className="flex flex-wrap gap-2">
      {agent.modeOptions.map((option) => (
        <button
          key={option.value}
          type="button"
          onClick={() => onModeChange(option.value)}
          className={`px-3 py-1.5 text-xs font-medium rounded-full border transition-colors ${
            activeMode === option.value
              ? 'border-blue-500 bg-blue-50 text-blue-600 dark:border-blue-400 dark:bg-blue-900/20 dark:text-blue-300'
              : 'border-gray-300 text-gray-600 hover:bg-gray-50 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-800'
          }`}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
