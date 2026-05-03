'use client';

import { useEffect, useState } from 'react';

import type { AddressableObjectSummary } from '@/lib/addressable-object-layer';

function isPreviewRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function isApiPreviewPath(previewUrl: string): boolean {
  return /^https?:\/\/[^/]+\/api\//.test(previewUrl) || previewUrl.startsWith('/api/');
}

function buildApiPreviewUrl(previewUrl: string, apiUrl: string): string {
  if (/^https?:\/\//.test(previewUrl)) {
    return previewUrl;
  }

  if (apiUrl) {
    return new URL(previewUrl, `${apiUrl.replace(/\/$/, '')}/`).toString();
  }

  if (typeof window !== 'undefined') {
    return new URL(previewUrl, window.location.origin).toString();
  }

  return previewUrl;
}

function buildIframePreviewUrl(previewUrl: string): string {
  if (/^https?:\/\//.test(previewUrl)) {
    return previewUrl;
  }

  if (typeof window !== 'undefined') {
    return new URL(previewUrl, window.location.origin).toString();
  }

  return previewUrl;
}

function formatPreviewLabel(key: string): string {
  return key
    .replace(/_/g, ' ')
    .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

function RuntimeObjectPreviewValue({
  value,
  depth = 0,
}: {
  value: unknown;
  depth?: number;
}) {
  if (value === null || value === undefined || value === '') {
    return null;
  }

  if (typeof value === 'string') {
    return (
      <div className="whitespace-pre-wrap break-words text-sm leading-6 text-slate-700 dark:text-slate-200">
        {value}
      </div>
    );
  }

  if (typeof value === 'number' || typeof value === 'boolean') {
    return (
      <div className="text-sm font-medium text-slate-800 dark:text-slate-100">{String(value)}</div>
    );
  }

  if (Array.isArray(value)) {
    const scalarItems = value.every(
      (item) =>
        typeof item === 'string' ||
        typeof item === 'number' ||
        typeof item === 'boolean',
    );

    if (scalarItems) {
      return (
        <div className="flex flex-wrap gap-2">
          {value.map((item, index) => (
            <span
              key={`${String(item)}-${index}`}
              className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs font-medium text-slate-600 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300"
            >
              {String(item)}
            </span>
          ))}
        </div>
      );
    }

    return (
      <div className="space-y-3">
        {value.map((item, index) => (
          <div
            key={index}
            className="rounded-2xl border border-slate-200 bg-white/90 p-3 dark:border-slate-800 dark:bg-slate-950/60"
          >
            <RuntimeObjectPreviewValue value={item} depth={depth + 1} />
          </div>
        ))}
      </div>
    );
  }

  if (isPreviewRecord(value)) {
    const entries = Object.entries(value).filter(([, item]) => item !== null && item !== undefined && item !== '');

    if (entries.length === 0) {
      return null;
    }

    if (depth >= 3) {
      return (
        <pre className="overflow-x-auto rounded-2xl bg-slate-950 px-4 py-3 text-xs leading-6 text-slate-100">
          {JSON.stringify(value, null, 2)}
        </pre>
      );
    }

    return (
      <div className="space-y-4">
        {entries.map(([key, item]) => (
          <div
            key={key}
            className="rounded-2xl border border-slate-200 bg-white/90 p-4 dark:border-slate-800 dark:bg-slate-950/60"
          >
            <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500 dark:text-slate-400">
              {formatPreviewLabel(key)}
            </div>
            <div className="mt-3">
              <RuntimeObjectPreviewValue value={item} depth={depth + 1} />
            </div>
          </div>
        ))}
      </div>
    );
  }

  return (
    <pre className="overflow-x-auto rounded-2xl bg-slate-950 px-4 py-3 text-xs leading-6 text-slate-100">
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}

export function RuntimeObjectSourcePreview({
  summary,
  apiUrl,
  fallbackSurfaceRoute,
}: {
  summary: AddressableObjectSummary | null;
  apiUrl: string;
  fallbackSurfaceRoute?: string | null;
}) {
  const previewUrl = summary?.owner_surface_url || fallbackSurfaceRoute || null;
  const [detailPayload, setDetailPayload] = useState<unknown>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    let isCancelled = false;

    if (!previewUrl || !isApiPreviewPath(previewUrl)) {
      setDetailPayload(null);
      setPreviewError(null);
      setIsLoading(false);
      return () => {
        isCancelled = true;
      };
    }

    const run = async () => {
      setIsLoading(true);
      setPreviewError(null);

      try {
        const response = await fetch(buildApiPreviewUrl(previewUrl, apiUrl));
        const text = await response.text();
        const payload = text ? JSON.parse(text) : null;

        if (!response.ok) {
          throw new Error(
            typeof payload?.detail === 'string'
              ? payload.detail
              : `Failed to load object preview (${response.status})`,
          );
        }

        if (!isCancelled) {
          setDetailPayload(payload);
        }
      } catch (error) {
        if (!isCancelled) {
          setDetailPayload(null);
          setPreviewError(
            error instanceof Error ? error.message : 'Failed to load owner-backed object preview.',
          );
        }
      } finally {
        if (!isCancelled) {
          setIsLoading(false);
        }
      }
    };

    void run();

    return () => {
      isCancelled = true;
    };
  }, [apiUrl, previewUrl]);

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center rounded-[22px] border border-slate-200 bg-white/80 px-4 py-6 text-xs text-slate-500 dark:border-slate-800 dark:bg-slate-950/60 dark:text-slate-300">
        Loading object preview...
      </div>
    );
  }

  if (detailPayload) {
    return (
      <div
        className="h-full overflow-y-auto rounded-[22px] border border-slate-200 bg-white/80 p-3 dark:border-slate-800 dark:bg-slate-950/60"
        data-testid="aol-object-preview-detail"
      >
        <RuntimeObjectPreviewValue value={detailPayload} />
      </div>
    );
  }

  if (previewUrl && !isApiPreviewPath(previewUrl)) {
    return (
      <div className="h-full overflow-hidden rounded-[22px] border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-950">
        <iframe
          src={buildIframePreviewUrl(previewUrl)}
          title={summary?.title || 'Selected object preview'}
          className="h-full w-full"
          data-testid="aol-object-preview-iframe"
        />
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto rounded-[22px] border border-slate-200 bg-white/80 p-3 dark:border-slate-800 dark:bg-slate-950/60">
      {previewError ? (
        <div className="rounded-[16px] border border-amber-200 bg-amber-50 px-3 py-2.5 text-xs text-amber-800 dark:border-amber-900/40 dark:bg-amber-950/20 dark:text-amber-200">
          {previewError}
        </div>
      ) : null}
      {summary?.summary_text ? (
        <div className="rounded-[16px] border border-slate-200 bg-white/90 p-3 dark:border-slate-800 dark:bg-slate-950/60">
          <div className="text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500 dark:text-slate-400">
            Summary
          </div>
          <div className="mt-2 whitespace-pre-wrap text-xs leading-5 text-slate-700 dark:text-slate-200">
            {summary.summary_text}
          </div>
        </div>
      ) : null}
      <div className="mt-3 rounded-[16px] border border-slate-200 bg-white/90 p-3 dark:border-slate-800 dark:bg-slate-950/60">
        <div className="text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500 dark:text-slate-400">
          Object metadata
        </div>
        <div className="mt-2 space-y-1.5 text-xs text-slate-700 dark:text-slate-200">
          <div>Owner: {summary?.ref.owner_pack || 'unknown'}</div>
          <div>Kind: {summary?.ref.object_kind || 'unknown'}</div>
          <div className="break-all">Object ID: {summary?.ref.object_id || 'unknown'}</div>
          {previewUrl ? (
            <a
              href={previewUrl}
              target="_blank"
              rel="noreferrer"
              className="inline-flex text-xs font-medium text-blue-600 hover:text-blue-700 dark:text-blue-300 dark:hover:text-blue-200"
            >
              Open source preview
            </a>
          ) : null}
        </div>
      </div>
    </div>
  );
}

export const AddressableObjectSourcePreview = RuntimeObjectSourcePreview;
