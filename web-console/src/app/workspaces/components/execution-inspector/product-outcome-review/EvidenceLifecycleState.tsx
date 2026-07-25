import type { EvidenceLifecycle } from './types';

export function EvidenceLifecycleState({
  lifecycle,
}: {
  lifecycle: EvidenceLifecycle | null;
}) {
  return (
    <section aria-labelledby="evidence-lifecycle-heading">
      <h4 id="evidence-lifecycle-heading" className="text-sm font-semibold">
        Evidence lifecycle
      </h4>
      {lifecycle ? (
        <dl className="mt-2 grid grid-cols-2 gap-1 text-xs">
          <dt>Class</dt><dd>{lifecycle.evidence_class}</dd>
          <dt>Action</dt><dd>{lifecycle.lifecycle_action ?? 'registered'}</dd>
          <dt>Reconciliation</dt><dd>{lifecycle.reconciliation_state}</dd>
          <dt>Privacy</dt><dd>{lifecycle.privacy_classification}</dd>
          <dt>Legal hold</dt><dd>{lifecycle.legal_hold ? 'yes' : 'no'}</dd>
          <dt>Content hash</dt>
          <dd className="break-all">{lifecycle.content_hash}</dd>
        </dl>
      ) : (
        <p className="mt-2 text-xs text-gray-500">
          No lifecycle receipt is available.
        </p>
      )}
    </section>
  );
}
