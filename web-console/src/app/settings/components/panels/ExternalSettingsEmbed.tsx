'use client';

import React, { useEffect, useRef } from 'react';

interface ExternalSettingsEmbedProps {
  title: string;
  description?: string;
  embedPath: string;
  height?: string;
  onMessage?: (event: MessageEvent) => void;
}

export function ExternalSettingsEmbed({
  title,
  description,
  embedPath,
  height = '700px',
  onMessage,
}: ExternalSettingsEmbedProps) {
  const iframeRef = useRef<HTMLIFrameElement>(null);

  useEffect(() => {
    const handleMessage = (event: MessageEvent) => {
      // Security: Only process messages from expected origins
      // In production, validate event.origin matches the expected domain
      if (onMessage) {
        onMessage(event);
      }
    };

    window.addEventListener('message', handleMessage);
    return () => {
      window.removeEventListener('message', handleMessage);
    };
  }, [onMessage]);

  return (
    <div className="w-full h-full flex flex-col">
      {description && (
        <div className="mb-4 text-sm text-gray-600 dark:text-gray-400">
          {description}
        </div>
      )}
      <div className="flex-1 border border-gray-300 dark:border-gray-600 rounded-md overflow-hidden">
        <iframe
          ref={iframeRef}
          src={embedPath}
          className="w-full h-full border-0"
          style={{ height }}
          title={title}
          sandbox="allow-same-origin allow-scripts allow-forms allow-popups allow-modals"
        />
      </div>
    </div>
  );
}

