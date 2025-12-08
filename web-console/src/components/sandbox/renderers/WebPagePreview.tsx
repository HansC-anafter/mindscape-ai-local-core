'use client';

import React, { useEffect, useRef, useState } from 'react';
import { SandboxFileContent, listSandboxFiles, getSandboxFileContent } from '@/lib/sandbox-api';

interface WebPagePreviewProps {
  workspaceId: string;
  sandboxId: string;
  version?: string;
}

export default function WebPagePreview({
  workspaceId,
  sandboxId,
  version,
}: WebPagePreviewProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const loadPreview = async () => {
      try {
        setLoading(true);
        setError(null);

        const files = await listSandboxFiles(workspaceId, sandboxId, '', version);
        const indexFile = files.find(f => f.path === 'pages/index.tsx' || f.path === 'index.tsx');

        if (!indexFile) {
          setError('No index file found');
          setLoading(false);
          return;
        }

        const indexContent = await getSandboxFileContent(
          workspaceId,
          sandboxId,
          indexFile.path,
          version
        );

        if (!containerRef.current) return;

        const container = containerRef.current;
        container.innerHTML = '';

        const iframe = document.createElement('iframe');
        iframe.style.width = '100%';
        iframe.style.height = '100%';
        iframe.style.border = 'none';

        const htmlContent = `
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Web Page Preview</title>
  <style>
    body { margin: 0; padding: 0; font-family: system-ui, -apple-system, sans-serif; }
  </style>
</head>
<body>
  <div id="root"></div>
  <script type="module">
    // React component code
    ${indexContent.content}
  </script>
</body>
</html>
        `;

        iframe.srcdoc = htmlContent;
        container.appendChild(iframe);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load preview');
      } finally {
        setLoading(false);
      }
    };

    loadPreview();
  }, [workspaceId, sandboxId, version]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-sm text-gray-500">Loading preview...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-sm text-red-500">Error: {error}</div>
      </div>
    );
  }

  return (
    <div className="web-page-preview h-full w-full" ref={containerRef} />
  );
}

