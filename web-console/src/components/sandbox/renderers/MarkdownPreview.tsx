'use client';

import React from 'react';
import { SandboxFileContent } from '@/lib/sandbox-api';

interface MarkdownPreviewProps {
  file: SandboxFileContent;
}

export default function MarkdownPreview({ file }: MarkdownPreviewProps) {
  return (
    <div className="markdown-preview h-full overflow-auto p-4">
      <div className="prose prose-sm dark:prose-invert max-w-none">
        <pre className="whitespace-pre-wrap font-sans">{file.content}</pre>
      </div>
    </div>
  );
}

