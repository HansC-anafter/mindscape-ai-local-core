'use client';

import { useEffect, useRef, useState } from 'react';
import { fetchCheckpoints } from './api';
import type { DurableCheckpoint } from './types';

interface CheckpointLineageProps {
  apiUrl: string;
  workspaceId: string;
  workflowId: string;
}

export function CheckpointLineage(props: CheckpointLineageProps) {
  const request = useRef<AbortController | null>(null);
  const [checkpoints, setCheckpoints] = useState<DurableCheckpoint[] | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    request.current?.abort();
    request.current = null;
    setCheckpoints(null);
    setError(null);
    return () => request.current?.abort();
  }, [props.workflowId]);

  const load = () => {
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    setError(null);
    fetchCheckpoints(
      props.apiUrl,
      props.workspaceId,
      props.workflowId,
      -1,
      controller.signal,
    )
      .then(setCheckpoints)
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) {
          setError(reason instanceof Error ? reason.message : String(reason));
        }
      });
  };

  if (checkpoints === null) {
    return (
      <button type="button" onClick={load} className="text-sm underline">
        Load checkpoint lineage
      </button>
    );
  }
  return (
    <section aria-label="Checkpoint lineage">
      {error && <p role="alert">{error}</p>}
      <ol className="space-y-1 text-xs">
        {checkpoints.map((checkpoint) => (
          <li key={checkpoint.checkpoint_id}>
            #{checkpoint.sequence} · {checkpoint.reducer_version}
          </li>
        ))}
      </ol>
    </section>
  );
}
