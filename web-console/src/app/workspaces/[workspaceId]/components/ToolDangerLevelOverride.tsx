'use client';

import React, { useState, useEffect } from 'react';

interface ToolDangerLevelOverrideProps {
  originalDangerLevel: 'low' | 'medium' | 'high';
  currentOverride?: 'low' | 'medium' | 'high';
  onOverrideChange: (override: 'low' | 'medium' | 'high' | null) => void;
  validateOverride: (original: string, override: string) => boolean;
}

const DANGER_LEVEL_ORDER: Record<string, number> = {
  low: 1,
  medium: 2,
  high: 3,
};

export default function ToolDangerLevelOverride({
  originalDangerLevel,
  currentOverride,
  onOverrideChange,
  validateOverride,
}: ToolDangerLevelOverrideProps) {
  const [selectedLevel, setSelectedLevel] = useState<'low' | 'medium' | 'high' | null>(currentOverride || null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setSelectedLevel(currentOverride || null);
  }, [currentOverride]);

  const handleLevelChange = (level: 'low' | 'medium' | 'high' | 'none') => {
    if (level === 'none') {
      setSelectedLevel(null);
      setError(null);
      onOverrideChange(null);
      return;
    }

    if (!validateOverride(originalDangerLevel, level)) {
      setError(`Cannot set danger level to ${level}. Override must be more restrictive than original (${originalDangerLevel}).`);
      return;
    }

    setSelectedLevel(level);
    setError(null);
    onOverrideChange(level);
  };

  const getLevelColor = (level: string) => {
    switch (level) {
      case 'low':
        return 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300 border-green-300 dark:border-green-700';
      case 'medium':
        return 'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-300 border-yellow-300 dark:border-yellow-700';
      case 'high':
        return 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300 border-red-300 dark:border-red-700';
      default:
        return 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 border-gray-300 dark:border-gray-600';
    }
  };

  const isLevelAllowed = (level: string): boolean => {
    if (level === 'none') return true;
    return validateOverride(originalDangerLevel, level);
  };

  return (
    <div className="space-y-4">
      <div>
        <h4 className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-1">
          Danger Level Override
        </h4>
        <p className="text-xs text-gray-500 dark:text-gray-400">
          Override can only be more restrictive than the original level ({originalDangerLevel}).
        </p>
      </div>

      <div className="space-y-2">
        <label className="flex items-center gap-2 p-2 border rounded-md cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800">
          <input
            type="radio"
            name="danger-level"
            checked={selectedLevel === null}
            onChange={() => handleLevelChange('none')}
            className="text-blue-600 focus:ring-blue-500"
          />
          <span className="text-sm text-gray-700 dark:text-gray-300">No Override (Use Original: {originalDangerLevel})</span>
        </label>

        {(['low', 'medium', 'high'] as const).map((level) => {
          const allowed = isLevelAllowed(level);
          const isSelected = selectedLevel === level;
          const isMoreRestrictive = DANGER_LEVEL_ORDER[level] >= DANGER_LEVEL_ORDER[originalDangerLevel];

          return (
            <label
              key={level}
              className={`flex items-center gap-2 p-2 border rounded-md cursor-pointer transition-colors ${
                !allowed
                  ? 'opacity-50 cursor-not-allowed bg-gray-50 dark:bg-gray-900'
                  : isSelected
                  ? getLevelColor(level)
                  : 'hover:bg-gray-50 dark:hover:bg-gray-800 border-gray-300 dark:border-gray-600'
              }`}
            >
              <input
                type="radio"
                name="danger-level"
                value={level}
                checked={isSelected}
                onChange={() => handleLevelChange(level)}
                disabled={!allowed}
                className="text-blue-600 focus:ring-blue-500 disabled:opacity-50"
              />
              <div className="flex-1">
                <span className={`text-sm font-medium ${isSelected ? '' : 'text-gray-700 dark:text-gray-300'}`}>
                  {level.toUpperCase()}
                </span>
                {!allowed && (
                  <span className="ml-2 text-xs text-red-600 dark:text-red-400">
                    (Not allowed - must be more restrictive)
                  </span>
                )}
                {allowed && !isMoreRestrictive && (
                  <span className="ml-2 text-xs text-yellow-600 dark:text-yellow-400">
                    (Less restrictive - not recommended)
                  </span>
                )}
              </div>
            </label>
          );
        })}
      </div>

      {error && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-3">
          <p className="text-sm text-red-700 dark:text-red-300">{error}</p>
        </div>
      )}

      {selectedLevel && (
        <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-3">
          <p className="text-xs text-blue-700 dark:text-blue-300">
            Override will apply {selectedLevel.toUpperCase()} danger level to tools in this workspace.
          </p>
        </div>
      )}
    </div>
  );
}

