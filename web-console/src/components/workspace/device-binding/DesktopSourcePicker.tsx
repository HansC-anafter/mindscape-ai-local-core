'use client';

import React, { useEffect, useRef, useState } from 'react';
import { Camera, RefreshCw } from 'lucide-react';

import {
  attachDeviceChangeRefresh,
  loadVideoInputCatalog,
  sourceKindLabel,
  type BrowserVideoInputSource,
} from '@/lib/media-transport/mediaDeviceCatalog';

interface DesktopSourcePickerProps {
  selectedDeviceId?: string;
  onSelectionChange: (source: BrowserVideoInputSource | null) => void;
  disabled?: boolean;
}

export function DesktopSourcePicker({
  selectedDeviceId,
  onSelectionChange,
  disabled = false,
}: DesktopSourcePickerProps) {
  const [sources, setSources] = useState<BrowserVideoInputSource[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const loadedRef = useRef(false);

  const loadSources = async () => {
    if (disabled || loading) {
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const nextSources = await loadVideoInputCatalog();
      loadedRef.current = true;
      setSources(nextSources);
      if (!selectedDeviceId && nextSources[0]) {
        onSelectionChange(nextSources[0]);
      }
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : 'camera_source_load_failed');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => attachDeviceChangeRefresh(
    globalThis.navigator?.mediaDevices,
    () => {
      if (loadedRef.current) {
        void loadSources();
      }
    },
  ));

  return (
    <div className="mb-5 rounded-md border border-gray-800 bg-gray-950 p-3">
      <div className="mb-3 flex items-center justify-between gap-2">
        <div className="inline-flex min-w-0 items-center gap-2 text-sm font-semibold text-gray-100">
          <Camera className="h-4 w-4 text-sky-400" aria-hidden="true" />
          <span className="truncate">Camera source</span>
        </div>
        <button
          type="button"
          onClick={() => void loadSources()}
          disabled={disabled || loading}
          className="inline-flex h-8 w-8 items-center justify-center rounded-md text-gray-300 hover:bg-gray-800 disabled:cursor-wait disabled:text-gray-600"
          aria-label="Refresh camera sources"
          title="Refresh"
        >
          <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} aria-hidden="true" />
        </button>
      </div>

      {error ? (
        <div className="mb-3 rounded border border-red-900 bg-red-950/40 px-2 py-1.5 text-xs text-red-200">
          {error}
        </div>
      ) : null}

      <div className="space-y-2">
        {sources.map((source) => (
          <button
            key={source.deviceId}
            type="button"
            onClick={() => onSelectionChange(source)}
            disabled={disabled}
            className={`flex w-full items-center justify-between gap-2 rounded-md border px-2 py-2 text-left transition-colors ${
              selectedDeviceId === source.deviceId
                ? 'border-sky-500 bg-sky-950/50 text-white'
                : 'border-gray-800 bg-gray-900 text-gray-200 hover:border-gray-700'
            } disabled:cursor-not-allowed disabled:opacity-60`}
          >
            <span className="min-w-0">
              <span className="block truncate text-sm font-medium">{source.label}</span>
              <span className="block truncate text-xs text-gray-400">
                {sourceKindLabel(source.sourceKind)}
              </span>
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}

export default DesktopSourcePicker;
