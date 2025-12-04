'use client';

import React from 'react';

interface ExpectedArtifactsBadgeProps {
  artifacts: string[];
  className?: string;
}

const artifactIcons: Record<string, string> = {
  pptx: '📊',
  xlsx: '📈',
  docx: '📄',
  pdf: '📕',
  csv: '📋',
  md: '📝',
  txt: '📃',
  html: '🌐',
  json: '🔧',
};

export default function ExpectedArtifactsBadge({
  artifacts,
  className = '',
}: ExpectedArtifactsBadgeProps) {
  if (!artifacts || artifacts.length === 0) return null;

  return (
    <div
      className={`
        inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs
        bg-emerald-50 dark:bg-emerald-900/20
        text-emerald-700 dark:text-emerald-400
        border border-emerald-200 dark:border-emerald-800
        ${className}
      `}
      title={`預期產出：${artifacts.join(', ')}`}
    >
      <span className="text-[10px]">📦</span>
      {artifacts.slice(0, 3).map((artifact) => (
        <span key={artifact} className="opacity-80">
          {artifactIcons[artifact.toLowerCase()] || '📄'}
        </span>
      ))}
      {artifacts.length > 3 && (
        <span className="text-[10px] opacity-60">+{artifacts.length - 3}</span>
      )}
    </div>
  );
}

