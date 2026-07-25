import type { ProductIterationReviewSummary } from './types';

export function EvaluationHistory({
  summary,
}: {
  summary: ProductIterationReviewSummary;
}) {
  return (
    <section aria-labelledby="evaluation-history-heading">
      <h4 id="evaluation-history-heading" className="text-sm font-semibold">
        Evaluation and decision receipts
      </h4>
      <dl className="mt-2 grid grid-cols-2 gap-1 text-xs">
        <dt>Attempts</dt><dd>{summary.evaluation_attempt_count}</dd>
        <dt>Latest decision</dt>
        <dd>{summary.evaluation?.decision ?? 'not_started'}</dd>
        <dt>Recommendation</dt>
        <dd>{summary.evaluation?.recommendation ?? 'not_started'}</dd>
        <dt>Approval request</dt>
        <dd>{summary.governance_receipts.approval_request ? 'recorded' : 'none'}</dd>
        <dt>Approval decision</dt>
        <dd>{summary.governance_receipts.approval_decision ? 'recorded' : 'none'}</dd>
        <dt>Approval consumption</dt>
        <dd>{summary.governance_receipts.approval_consumption ? 'recorded' : 'none'}</dd>
        <dt>Owner effect</dt>
        <dd>{summary.governance_receipts.release_effect ? 'recorded' : 'none'}</dd>
      </dl>
    </section>
  );
}
