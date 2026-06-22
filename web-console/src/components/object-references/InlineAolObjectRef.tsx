'use client';

import React from 'react';
import { ExternalLink, Loader2 } from 'lucide-react';

import { getApiBaseUrl } from '@/lib/api-url';
import type { AddressableObjectRef } from '@/lib/addressable-object-layer';
import {
  readObjectReferencePreviewWithSync,
  type ObjectReferencePreviewResult,
} from '@/lib/object-reference-client';

const PREVIEW_CACHE_TTL_MS = 5 * 60 * 1000;
const PREVIEW_CLOSE_GRACE_MS = 240;

type CacheEntry = {
  expiresAt: number;
  result: ObjectReferencePreviewResult;
};

const previewCache = new Map<string, CacheEntry>();
const previewInflight = new Map<string, Promise<ObjectReferencePreviewResult>>();

export interface InlineAolObjectRefProps {
  workspaceId?: string | null;
  objectRef: AddressableObjectRef;
  label?: string;
  className?: string;
  apiUrl?: string;
  previewDelayMs?: number;
}

function getCacheKey(workspaceId: string, objectRef: AddressableObjectRef): string {
  return `${workspaceId}:${objectRef.uri}`;
}

function readCachedPreview(cacheKey: string): ObjectReferencePreviewResult | null {
  const entry = previewCache.get(cacheKey);
  if (!entry || entry.expiresAt <= Date.now()) {
    previewCache.delete(cacheKey);
    return null;
  }
  return entry.result;
}

async function loadPreview({
  cacheKey,
  apiUrl,
  workspaceId,
  objectRef,
  signal,
}: {
  cacheKey: string;
  apiUrl: string;
  workspaceId: string;
  objectRef: AddressableObjectRef;
  signal?: AbortSignal;
}): Promise<ObjectReferencePreviewResult> {
  const cached = readCachedPreview(cacheKey);
  if (cached) return cached;

  const existing = previewInflight.get(cacheKey);
  if (existing) return existing;

  const promise = readObjectReferencePreviewWithSync({
    apiUrl,
    workspaceId,
    objectRef,
    signal,
  })
    .then((result) => {
      previewCache.set(cacheKey, {
        expiresAt: Date.now() + PREVIEW_CACHE_TTL_MS,
        result,
      });
      return result;
    })
    .finally(() => {
      previewInflight.delete(cacheKey);
    });

  previewInflight.set(cacheKey, promise);
  return promise;
}

function buildSurfaceUrl(apiUrl: string, url?: string | null): string | null {
  if (!url) return null;
  if (/^(https?:|data:|blob:)/.test(url)) return url;
  if (!url.startsWith('/')) return url;
  return `${apiUrl.replace(/\/$/, '')}${url}`;
}

function buildOwnerSurfaceUrl(apiUrl: string, url?: string | null): string | null {
  if (!url) return null;
  if (/^(https?:|data:|blob:)/.test(url)) return url;
  if (!url.startsWith('/')) return url;
  if (url.startsWith('/workspaces/') || url.startsWith('/capability-ui-hosts/')) {
    return url;
  }
  return `${apiUrl.replace(/\/$/, '')}${url}`;
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError';
}

export function clearInlineObjectReferencePreviewCache() {
  previewCache.clear();
  previewInflight.clear();
}

export function InlineAolObjectRef({
  workspaceId,
  objectRef,
  label,
  className = '',
  apiUrl,
  previewDelayMs = 200,
}: InlineAolObjectRefProps) {
  const [open, setOpen] = React.useState(false);
  const [loading, setLoading] = React.useState(false);
  const [result, setResult] = React.useState<ObjectReferencePreviewResult | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [imageFailed, setImageFailed] = React.useState(false);
  const closeTimerRef = React.useRef<number | null>(null);
  const resolvedApiUrl = apiUrl ?? getApiBaseUrl();
  const displayLabel = label || objectRef.object_id || objectRef.uri;
  const resolvedWorkspaceId = workspaceId || objectRef.workspace_id || '';
  const cacheKey = resolvedWorkspaceId ? getCacheKey(resolvedWorkspaceId, objectRef) : '';
  const summary = result?.status === 'ready' ? result.summary : null;

  React.useEffect(() => {
    if (!open || !resolvedWorkspaceId || !cacheKey) return undefined;

    const cached = readCachedPreview(cacheKey);
    if (cached) {
      setResult(cached);
      setError(null);
      setLoading(false);
      return undefined;
    }

    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      setLoading(true);
      setError(null);
      void loadPreview({
        cacheKey,
        apiUrl: resolvedApiUrl,
        workspaceId: resolvedWorkspaceId,
        objectRef,
        signal: controller.signal,
      })
        .then((preview) => {
          setResult(preview);
        })
        .catch((err: unknown) => {
          if (isAbortError(err)) return;
          setError(err instanceof Error ? err.message : 'Unable to read object preview.');
        })
        .finally(() => {
          setLoading(false);
        });
    }, previewDelayMs);

    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [cacheKey, objectRef, open, previewDelayMs, resolvedApiUrl, resolvedWorkspaceId]);

  React.useEffect(() => {
    setImageFailed(false);
  }, [summary?.thumbnail_ref]);

  React.useEffect(() => {
    if (!open) return undefined;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setOpen(false);
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [open]);

  React.useEffect(() => {
    return () => {
      if (closeTimerRef.current !== null) {
        window.clearTimeout(closeTimerRef.current);
      }
    };
  }, []);

  if (!resolvedWorkspaceId) {
    return <span className={className}>{displayLabel}</span>;
  }

  const thumbnailUrl = buildSurfaceUrl(resolvedApiUrl, summary?.thumbnail_ref);
  const ownerSurfaceUrl = buildOwnerSurfaceUrl(resolvedApiUrl, summary?.owner_surface_url);
  const openPreview = () => {
    if (closeTimerRef.current !== null) {
      window.clearTimeout(closeTimerRef.current);
      closeTimerRef.current = null;
    }
    setOpen(true);
  };
  const scheduleClosePreview = () => {
    if (closeTimerRef.current !== null) {
      window.clearTimeout(closeTimerRef.current);
    }
    closeTimerRef.current = window.setTimeout(() => {
      closeTimerRef.current = null;
      setOpen(false);
    }, PREVIEW_CLOSE_GRACE_MS);
  };

  return (
    <span
      className={`relative inline-flex align-baseline ${className}`}
      onPointerEnter={openPreview}
      onPointerLeave={scheduleClosePreview}
      onFocusCapture={openPreview}
      onBlurCapture={scheduleClosePreview}
    >
      <button
        type="button"
        className="inline-flex items-center rounded bg-blue-50 px-1.5 py-0.5 font-mono text-xs font-semibold text-blue-700 underline-offset-2 hover:bg-blue-100 hover:underline focus:outline-none focus:ring-2 focus:ring-blue-400 dark:bg-blue-900/30 dark:text-blue-200 dark:hover:bg-blue-900/50"
        onClick={() => setOpen((value) => !value)}
        aria-label={`Preview AOL object ${displayLabel}`}
        aria-expanded={open}
      >
        {displayLabel}
      </button>

      {open ? (
        <span
          className="absolute left-0 top-full z-50 mt-2 w-[min(380px,calc(100vw-32px))] rounded-lg border border-gray-200 bg-white p-3 text-left text-xs shadow-xl dark:border-gray-700 dark:bg-gray-900"
          role="dialog"
          aria-label={`AOL object preview ${displayLabel}`}
        >
          {loading ? (
            <span className="flex items-center gap-2 text-gray-600 dark:text-gray-300">
              <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
              Loading object preview...
            </span>
          ) : null}

          {!loading && error ? (
            <span className="block text-red-600 dark:text-red-300">{error}</span>
          ) : null}

          {!loading && result?.status === 'not_indexed' ? (
            <span className="block text-amber-700 dark:text-amber-300">
              Object ref is valid, but this workspace has not indexed it yet.
            </span>
          ) : null}

          {!loading && summary ? (
            <span className="flex gap-3">
              {thumbnailUrl && !imageFailed ? (
                <img
                  src={thumbnailUrl}
                  alt=""
                  className="h-20 w-20 flex-none rounded border border-gray-200 object-cover dark:border-gray-700"
                  onError={() => setImageFailed(true)}
                />
              ) : null}
              <span className="min-w-0 flex-1">
                <span className="block truncate font-semibold text-gray-900 dark:text-gray-100">
                  {summary.title || displayLabel}
                </span>
                {summary.subtitle ? (
                  <span className="mt-0.5 block truncate text-gray-500 dark:text-gray-400">
                    {summary.subtitle}
                  </span>
                ) : null}
                {summary.summary_text ? (
                  <span className="mt-2 line-clamp-3 block text-gray-700 dark:text-gray-300">
                    {summary.summary_text}
                  </span>
                ) : null}
                {summary.labels?.length ? (
                  <span className="mt-2 flex flex-wrap gap-1">
                    {summary.labels.slice(0, 4).map((item) => (
                      <span
                        key={item}
                        className="rounded bg-gray-100 px-1.5 py-0.5 text-[11px] text-gray-600 dark:bg-gray-800 dark:text-gray-300"
                      >
                        {item}
                      </span>
                    ))}
                  </span>
                ) : null}
                {ownerSurfaceUrl ? (
                  <a
                    href={ownerSurfaceUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="mt-2 inline-flex items-center gap-1 font-medium text-blue-700 hover:underline dark:text-blue-300"
                  >
                    Open object
                    <ExternalLink className="h-3 w-3" aria-hidden="true" />
                  </a>
                ) : null}
              </span>
            </span>
          ) : null}
        </span>
      ) : null}
    </span>
  );
}
