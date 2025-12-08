'use client';

import React from 'react';
import { SandboxFileContent } from '@/lib/sandbox-api';

interface CodeDiffPreviewProps {
  file: SandboxFileContent;
  fromVersion?: string;
  toVersion?: string;
}

export default function CodeDiffPreview({
  file,
  fromVersion,
  toVersion,
}: CodeDiffPreviewProps) {
  return (
    <div className="code-diff-preview h-full overflow-auto p-4">
      <div className="mb-4 text-sm text-gray-600 dark:text-gray-400">
        {fromVersion && toVersion ? (
          <span>Comparing {fromVersion} → {toVersion}</span>
        ) : (
          <span>Code diff preview</span>
        )}
      </div>
      <pre className="text-sm font-mono bg-gray-900 text-gray-100 p-4 rounded overflow-x-auto">
        <code>{file.content}</code>
      </pre>
    </div>
  );
}

