'use client';

import { useState } from 'react';

interface Props {
  currentSequence: number;
  onAsOf: (sequence: number) => void;
  onReEvaluate: () => void;
  onFork: () => void;
  onCompare: () => void;
}

export function OutcomeTimeTravelControls({
  currentSequence,
  onAsOf,
  onReEvaluate,
  onFork,
  onCompare,
}: Props) {
  const [sequence, setSequence] = useState(currentSequence);
  return (
    <section aria-labelledby="outcome-time-travel-heading">
      <h4 id="outcome-time-travel-heading" className="text-sm font-semibold">
        Product outcome time travel
      </h4>
      <p className="mt-1 text-xs text-gray-500">
        As-of is read-only. Re-evaluation reuses the evidence frontier and
        never reruns lower tasks or effects. A fork creates a successor
        iteration and does not reopen this source.
      </p>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <label className="text-xs">
          Sequence
          <input
            className="ml-1 w-20 rounded border px-1 py-0.5"
            type="number"
            min={0}
            max={currentSequence}
            value={sequence}
            onChange={(event) => setSequence(Number(event.target.value))}
          />
        </label>
        <button type="button" onClick={() => onAsOf(sequence)}>
          View outcome as-of
        </button>
        <button type="button" onClick={onReEvaluate}>
          Re-evaluate evidence
        </button>
        <button type="button" onClick={onFork}>
          Fork iteration
        </button>
        <button type="button" onClick={onCompare}>
          Compare explicit refs
        </button>
      </div>
    </section>
  );
}
