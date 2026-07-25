import type { DurableWorkflowSummary as Summary } from './types';

interface DurableWorkflowSummaryProps {
  summary: Summary;
}

export function DurableWorkflowSummary({
  summary,
}: DurableWorkflowSummaryProps) {
  return (
    <section aria-labelledby="durable-workflow-heading" className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 id="durable-workflow-heading" className="text-sm font-semibold">
          Durable workflow
        </h3>
        <span className="rounded bg-gray-100 px-2 py-1 text-xs dark:bg-gray-800">
          {summary.current_state}
        </span>
      </div>
      <dl className="grid grid-cols-2 gap-2 text-xs">
        <dt>Sequence</dt>
        <dd>{summary.current_sequence}</dd>
        <dt>Segment</dt>
        <dd>{summary.segment_number}</dd>
        <dt>Reducer</dt>
        <dd>{summary.reducer_version}</dd>
        <dt>Workflow definition</dt>
        <dd>{summary.workflow_definition_version}</dd>
        <dt>Effect adapter registry</dt>
        <dd>{summary.effect_adapter_registry_version}</dd>
        <dt>Runtime build</dt>
        <dd>{summary.runtime_build_id}</dd>
        <dt>Checkpoints</dt>
        <dd>{summary.checkpoint_count}</dd>
        <dt>Open approvals</dt>
        <dd>{summary.open_approval_count}</dd>
        <dt>Side-effect receipts</dt>
        <dd>{summary.side_effect_count}</dd>
      </dl>
      <p className="break-all text-xs text-gray-500">
        Attestation: {summary.development_attestation_id} ·{' '}
        {summary.development_attestation_sha256}
      </p>
      <p className="text-xs text-gray-500">
        Consumer compatibility: {summary.consumer_compatibility_class}
      </p>
      <p className="break-all text-xs text-gray-500">
        Environment: {summary.environment_fingerprint} · Data:{' '}
        {summary.data_fingerprint}
      </p>
      {summary.evidence_lifecycle && (
        <p className="text-xs text-gray-500">
          Evidence: {summary.evidence_lifecycle.evidence_class} ·{' '}
          {summary.evidence_lifecycle.lifecycle_action ?? 'registered'} ·{' '}
          {summary.evidence_lifecycle.reconciliation_state}
        </p>
      )}
    </section>
  );
}
