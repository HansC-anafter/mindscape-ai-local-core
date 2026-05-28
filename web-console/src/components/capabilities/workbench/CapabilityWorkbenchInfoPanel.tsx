'use client';

import React from 'react';

import {
  assertCapabilityWorkbenchInfoMetadata,
  type CapabilityWorkbenchInfoMetadata,
  type CapabilityWorkbenchInfoReference,
  type CapabilityWorkbenchInfoStatus,
} from '@/types/capability-workbench';

const TONE_CLASS_NAMES: Record<CapabilityWorkbenchInfoStatus['tone'], string> = {
  neutral: 'border-gray-200 bg-gray-50 text-gray-700 dark:border-gray-800 dark:bg-gray-900 dark:text-gray-300',
  active: 'border-blue-200 bg-blue-50 text-blue-700 dark:border-blue-900 dark:bg-blue-950/40 dark:text-blue-200',
  warning: 'border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-200',
  danger: 'border-red-200 bg-red-50 text-red-700 dark:border-red-900 dark:bg-red-950/40 dark:text-red-200',
  success: 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-200',
};

function MetadataRow({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  return (
    <div className="grid grid-cols-[96px_minmax(0,1fr)] gap-2 border-b border-gray-100 py-2 text-xs last:border-b-0 dark:border-gray-800">
      <dt className="font-semibold uppercase tracking-normal text-gray-500 dark:text-gray-400">
        {label}
      </dt>
      <dd className="min-w-0 break-words text-gray-900 dark:text-gray-100">
        {value || 'n/a'}
      </dd>
    </div>
  );
}

function ReferenceRow({
  reference,
}: {
  reference: CapabilityWorkbenchInfoReference;
}) {
  const handleCopy = () => {
    if (typeof navigator === 'undefined' || !navigator.clipboard) {
      return;
    }
    void navigator.clipboard.writeText(reference.copyValue);
  };

  return (
    <div className="rounded-md border border-gray-200 bg-white p-2 text-xs dark:border-gray-800 dark:bg-gray-950">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="font-semibold text-gray-700 dark:text-gray-200">{reference.label}</div>
          <div className="mt-1 break-words font-mono text-[11px] text-gray-500 dark:text-gray-400">
            {reference.value || 'n/a'}
          </div>
        </div>
        <button
          type="button"
          className="shrink-0 rounded border border-gray-200 px-2 py-1 text-[11px] font-medium text-gray-600 hover:bg-gray-50 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-900"
          onClick={handleCopy}
        >
          Copy
        </button>
      </div>
    </div>
  );
}

function StatusRow({
  status,
}: {
  status: CapabilityWorkbenchInfoStatus;
}) {
  return (
    <div className={`rounded-md border px-2 py-2 text-xs ${TONE_CLASS_NAMES[status.tone]}`}>
      <div className="font-semibold">{status.label}</div>
      <div className="mt-1 break-words font-mono text-[11px]">{status.value || 'n/a'}</div>
    </div>
  );
}

export function CapabilityWorkbenchInfoPanel({
  metadata,
}: {
  metadata: CapabilityWorkbenchInfoMetadata;
}) {
  let validMetadata: CapabilityWorkbenchInfoMetadata;
  try {
    validMetadata = assertCapabilityWorkbenchInfoMetadata(metadata);
  } catch {
    return (
      <div
        className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/30 dark:text-red-200"
        data-testid="capability-workbench-info-invalid"
      >
        Invalid workbench info metadata contract.
      </div>
    );
  }

  return (
    <section className="space-y-4" data-testid="capability-workbench-info-panel">
      <div>
        <div className="text-sm font-semibold text-gray-900 dark:text-gray-100">
          {validMetadata.capability.label}
        </div>
        <div className="mt-1 font-mono text-[11px] text-gray-500 dark:text-gray-400">
          {validMetadata.capability.code}
        </div>
      </div>

      <dl className="rounded-md border border-gray-200 bg-white px-3 dark:border-gray-800 dark:bg-gray-950">
        <MetadataRow label="Workspace" value={validMetadata.workspace.label || validMetadata.workspace.id} />
        <MetadataRow label="Workspace ID" value={validMetadata.workspace.id} />
        <MetadataRow label="Object" value={`${validMetadata.primaryObject.kind}:${validMetadata.primaryObject.id}`} />
        <MetadataRow label="Object label" value={validMetadata.primaryObject.label || ''} />
        <MetadataRow label="Session" value={validMetadata.session?.id || ''} />
        <MetadataRow label="Session state" value={validMetadata.session?.status || ''} />
        <MetadataRow label="Artifact" value={validMetadata.artifact?.id || ''} />
        <MetadataRow label="Selection" value={[
          validMetadata.selection?.mode,
          validMetadata.selection?.department,
          validMetadata.selection?.sceneId,
          validMetadata.selection?.shotId,
        ].filter(Boolean).join(' / ')} />
      </dl>

      <div className="space-y-2">
        <div className="text-xs font-semibold uppercase tracking-normal text-gray-500 dark:text-gray-400">
          References
        </div>
        {validMetadata.references.length > 0 ? (
          validMetadata.references.map((reference) => (
            <ReferenceRow key={reference.key} reference={reference} />
          ))
        ) : (
          <div className="rounded-md border border-dashed border-gray-200 p-3 text-xs text-gray-500 dark:border-gray-800 dark:text-gray-400">
            No references.
          </div>
        )}
      </div>

      <div className="space-y-2">
        <div className="text-xs font-semibold uppercase tracking-normal text-gray-500 dark:text-gray-400">
          Status
        </div>
        {validMetadata.status.length > 0 ? (
          validMetadata.status.map((status) => (
            <StatusRow key={status.key} status={status} />
          ))
        ) : (
          <div className="rounded-md border border-dashed border-gray-200 p-3 text-xs text-gray-500 dark:border-gray-800 dark:text-gray-400">
            No status rows.
          </div>
        )}
      </div>
    </section>
  );
}

export default CapabilityWorkbenchInfoPanel;
