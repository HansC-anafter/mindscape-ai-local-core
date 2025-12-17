'use client';

import React, { useEffect, useRef, useState } from 'react';
import {
  SandboxFileContent,
  listSandboxFiles,
  getSandboxFileContent,
  startPreviewServer,
  stopPreviewServer,
  getPreviewServerStatus,
  PreviewServerStatus,
} from '@/lib/sandbox-api';
import { useT } from '@/lib/i18n';

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
  const iframeRef = useRef<HTMLIFrameElement | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [portConflict, setPortConflict] = useState(false);
  const [actualPort, setActualPort] = useState<number | null>(null);
  const t = useT();

  useEffect(() => {
    let isMounted = true;

    const loadPreview = async () => {
      try {
        setLoading(true);
        setError(null);
        setPortConflict(false);
        setActualPort(null);

        const status = await getPreviewServerStatus(workspaceId, sandboxId);
        if (status.running && status.url) {
          if (isMounted) {
            setPreviewUrl(status.url);
            setActualPort(status.port);
            setLoading(false);
          }
          return;
        }

        const result: PreviewServerStatus = await startPreviewServer(
          workspaceId,
          sandboxId,
          3000
        );

        if (!isMounted) return;

        if (result.success && result.url) {
          setPreviewUrl(result.url);
          setActualPort(result.port);
          if (result.port_conflict) {
            setPortConflict(true);
          }
        } else {
          setError(result.error || 'Failed to start preview server');
          if (result.port_conflict) {
            setPortConflict(true);
          }
        }
      } catch (err) {
        if (isMounted) {
          setError(err instanceof Error ? err.message : 'Failed to load preview');
        }
      } finally {
        if (isMounted) {
          setLoading(false);
        }
      }
    };

    loadPreview();

    return () => {
      isMounted = false;
      stopPreviewServer(workspaceId, sandboxId).catch(() => {
        // Ignore errors when stopping
      });
    };
  }, [workspaceId, sandboxId, version]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-sm text-gray-500">{t('loadingPreview')}</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-full p-4">
        <div className="text-sm text-red-500 mb-2">{t('previewError')}: {error}</div>
        {portConflict && (
          <div className="text-xs text-yellow-600 dark:text-yellow-400 mt-2">
            {t('portConflictMessage')} {actualPort && `(${t('usingPort')} ${actualPort})`}
          </div>
        )}
      </div>
    );
  }

  if (previewUrl) {
    return (
      <div className="web-page-preview h-full w-full flex flex-col">
        {portConflict && (
          <div className="bg-yellow-50 dark:bg-yellow-900/20 border-b border-yellow-200 dark:border-yellow-800 px-4 py-2 text-xs text-yellow-800 dark:text-yellow-200">
            {t('portConflictWarning')} {actualPort && `(${t('usingPort')} ${actualPort})`}
          </div>
        )}
        <iframe
          ref={iframeRef}
          src={previewUrl}
          className="flex-1 w-full border-0"
          title="Web Page Preview"
        />
      </div>
    );
  }

  return (
    <div className="flex items-center justify-center h-full">
      <div className="text-sm text-gray-500">{t('noPreviewAvailable')}</div>
    </div>
  );
}

