'use client';

import { useEffect, useRef, useState } from 'react';
import { fetchAsOfSnapshot } from './api';
import type { AsOfSnapshot } from './types';

interface TimeTravelControlsProps {
  apiUrl: string;
  workspaceId: string;
  workflowId: string;
  currentSequence: number;
}

export function TimeTravelControls(props: TimeTravelControlsProps) {
  const request = useRef<AbortController | null>(null);
  const [sequence, setSequence] = useState(props.currentSequence);
  const [snapshot, setSnapshot] = useState<AsOfSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    request.current?.abort();
    request.current = null;
    setSequence(props.currentSequence);
    setSnapshot(null);
    setError(null);
    return () => request.current?.abort();
  }, [props.workflowId, props.currentSequence]);

  const inspect = () => {
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    setError(null);
    fetchAsOfSnapshot(
      props.apiUrl,
      props.workspaceId,
      props.workflowId,
      sequence,
      controller.signal,
    )
      .then(setSnapshot)
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) {
          setError(reason instanceof Error ? reason.message : String(reason));
        }
      });
  };

  return (
    <section aria-label="Time travel review" className="space-y-2">
      <label className="block text-xs">
        Sequence
        <input
          type="number"
          min={0}
          max={Math.min(50, props.currentSequence)}
          value={sequence}
          onChange={(event) => setSequence(Number(event.target.value))}
          className="ml-2 w-20 border px-1"
        />
      </label>
      <button type="button" onClick={inspect} className="text-sm underline">
        Inspect as-of state
      </button>
      {error && <p role="alert">{error}</p>}
      {snapshot && (
        <pre className="max-h-48 overflow-auto text-xs">
          {JSON.stringify(snapshot.state, null, 2)}
        </pre>
      )}
    </section>
  );
}
