'use client';

import React from 'react';
import { SandboxFileContent } from '@/lib/sandbox-api';

interface SandboxFilePreviewProps {
  file: SandboxFileContent;
  filePath: string;
}

export default function SandboxFilePreview({
  file,
  filePath,
}: SandboxFilePreviewProps) {
  const getLanguage = (filePath: string): string => {
    const ext = filePath.split('.').pop()?.toLowerCase();
    const languageMap: Record<string, string> = {
      ts: 'typescript',
      tsx: 'typescript',
      js: 'javascript',
      jsx: 'javascript',
      py: 'python',
      md: 'markdown',
      json: 'json',
      yaml: 'yaml',
      yml: 'yaml',
      html: 'html',
      css: 'css',
      scss: 'scss',
    };
    return languageMap[ext || ''] || 'text';
  };

  const language = getLanguage(filePath);

  const handleDownload = () => {
    const blob = new Blob([file.content], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a' as any);
    a.href = url;
    a.download = filePath.split('/').pop() || 'file';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  return (
    <div className="sandbox-file-preview h-full flex flex-col">
      <div className="border-b border-gray-200 dark:border-gray-800 p-2">
        <div className="flex items-center justify-between">
          <div className="text-sm font-medium">{filePath}</div>
          <div className="flex items-center gap-2">
            <div className="text-xs text-gray-500">
              {file.size} bytes
              {file.modified && ` • Modified: ${new Date(file.modified * 1000).toLocaleString()}`}
            </div>
            <button
              onClick={handleDownload}
              className="px-2 py-1 text-xs bg-gray-200 dark:bg-gray-700 rounded hover:bg-gray-300 dark:hover:bg-gray-600"
              title="Download file"
            >
              ⬇ Download
            </button>
          </div>
        </div>
      </div>
      <div className="flex-1 overflow-auto p-4">
        <pre className="text-sm font-mono">
          <code className={`language-${language}`}>{file.content}</code>
        </pre>
      </div>
    </div>
  );
}

