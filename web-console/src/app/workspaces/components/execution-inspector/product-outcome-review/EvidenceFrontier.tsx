import type { ProductIterationReviewSummary } from './types';

export function EvidenceFrontier({
  frontier,
}: {
  frontier: ProductIterationReviewSummary['evidence_frontier'];
}) {
  const missing = Math.max(
    0,
    frontier.minimum_sample_size - frontier.accepted_observation_count,
  );
  return (
    <section aria-labelledby="evidence-frontier-heading">
      <h4 id="evidence-frontier-heading" className="text-sm font-semibold">
        Evidence frontier
      </h4>
      <dl className="mt-2 grid grid-cols-2 gap-1 text-xs">
        <dt>Accepted observations</dt>
        <dd>{frontier.accepted_observation_count}</dd>
        <dt>Minimum sample</dt><dd>{frontier.minimum_sample_size}</dd>
        <dt>Missing</dt><dd>{missing}</dd>
        <dt>Last observation sequence</dt>
        <dd>{frontier.last_observation_sequence}</dd>
        <dt>Frontier hash</dt>
        <dd className="break-all">{frontier.frontier_hash}</dd>
      </dl>
    </section>
  );
}
