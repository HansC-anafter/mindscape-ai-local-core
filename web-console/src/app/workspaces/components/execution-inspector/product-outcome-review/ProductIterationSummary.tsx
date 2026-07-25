import type { ProductIterationReviewSummary } from './types';

export function ProductIterationSummary({
  summary,
}: {
  summary: ProductIterationReviewSummary;
}) {
  return (
    <section aria-labelledby="product-iteration-summary-heading">
      <div className="flex items-center justify-between gap-2">
        <h3 id="product-iteration-summary-heading" className="text-sm font-semibold">
          Product iteration outcome
        </h3>
        <span className="rounded bg-gray-100 px-2 py-1 text-xs dark:bg-gray-800">
          {summary.state}
        </span>
      </div>
      <p className="mt-2 text-sm">{summary.objective}</p>
      <dl className="mt-2 grid grid-cols-2 gap-1 text-xs">
        <dt>Iteration</dt><dd className="break-all">{summary.iteration_id}</dd>
        <dt>Revision</dt><dd>{summary.revision}</dd>
        <dt>Parent</dt><dd>{summary.parent_iteration_id ?? 'none'}</dd>
        <dt>Sequence</dt><dd>{summary.current_sequence}</dd>
        <dt>Definition hash</dt>
        <dd className="break-all">{summary.definition_sha256}</dd>
      </dl>
    </section>
  );
}
