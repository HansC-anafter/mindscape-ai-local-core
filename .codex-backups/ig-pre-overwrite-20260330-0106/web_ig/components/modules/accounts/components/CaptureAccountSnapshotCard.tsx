import React, { useEffect, useRef } from 'react';

export function CaptureAccountSnapshotCard(props: {
  snapshotHandleInput: string;
  onSnapshotHandleInputChange: (value: string) => void;
  onCaptureSnapshot: () => void;
  captureDisabled: boolean;
  snapshotError: string | null;
  focusToken?: number;
}) {
  const {
    snapshotHandleInput,
    onSnapshotHandleInputChange,
    onCaptureSnapshot,
    captureDisabled,
    snapshotError,
    focusToken = 0,
  } = props;
  const inputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (!focusToken) return;
    const timer = window.setTimeout(() => {
      inputRef.current?.focus();
    }, 0);
    return () => {
      window.clearTimeout(timer);
    };
  }, [focusToken]);

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
      <div className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-1">Capture account snapshot</div>
      <div className="text-xs text-gray-500 dark:text-gray-400">
        Captures bio, followers, following, posts, and avatar for one target.
      </div>
      <div className="mt-3 flex items-center gap-2">
        <input
          ref={inputRef}
          type="text"
          value={snapshotHandleInput}
          onChange={(e) => onSnapshotHandleInputChange(e.target.value)}
          placeholder="@handle"
          className="flex-1 px-3 py-2 text-sm border rounded-lg dark:bg-gray-700 dark:border-gray-600"
        />
        <button
          onClick={onCaptureSnapshot}
          disabled={captureDisabled}
          className="px-3 py-2 text-sm bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
        >
          Capture
        </button>
      </div>
      {snapshotError && (
        <div className="mt-2 text-xs text-red-600 dark:text-red-400">
          {snapshotError}
        </div>
      )}
    </div>
  );
}
