'use client';

import React, { useEffect, useRef } from 'react';
import { SandboxFileContent } from '@/lib/sandbox-api';

interface ThreeJSPreviewProps {
  files: SandboxFileContent[];
}

export default function ThreeJSPreview({ files }: ThreeJSPreviewProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    const container = containerRef.current;
    container.innerHTML = '';

    const iframe = document.createElement('iframe' as any);
    iframe.style.width = '100%';
    iframe.style.height = '100%';
    iframe.style.border = 'none';

    const htmlFile = files.find(f => f.path.endsWith('.html') || f.path === 'index.html');
    const componentFile = files.find(f => f.path.endsWith('.tsx') || f.path.endsWith('.jsx'));

    if (htmlFile) {
      iframe.srcdoc = htmlFile.content;
    } else if (componentFile) {
      const htmlContent = `
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Three.js Preview</title>
  <style>
    body { margin: 0; padding: 0; overflow: hidden; }
    canvas { display: block; }
  </style>
</head>
<body>
  <script type="module">
    // Component code will be loaded here
    ${componentFile.content}
  </script>
</body>
</html>
      `;
      iframe.srcdoc = htmlContent;
    } else {
      container.innerHTML = '<div class="p-4 text-gray-500">No preview available. HTML or component file required.</div>';
      return;
    }

    container.appendChild(iframe);

    return () => {
      if (container.contains(iframe)) {
        container.removeChild(iframe);
      }
    };
  }, [files]);

  return (
    <div className="threejs-preview h-full w-full" ref={containerRef} />
  );
}

