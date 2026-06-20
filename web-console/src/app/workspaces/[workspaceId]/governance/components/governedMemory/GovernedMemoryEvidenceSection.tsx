import { formatLocalDateTime } from '@/lib/time';

import {
  EVIDENCE_ROLE_KEYS,
  evidenceDisplayName,
  evidenceMetadataRows,
  fileLabelFromPath,
  translateMappedValue,
} from './formatters';
import type { MemoryEvidenceSummary, TranslateFn } from './types';

interface GovernedMemoryEvidenceSectionProps {
  t: TranslateFn;
  evidence: MemoryEvidenceSummary[];
  filteredEvidence: MemoryEvidenceSummary[];
  evidenceTypeCounts: Record<string, number>;
  evidenceTypeFilter: string;
  onEvidenceTypeFilterChange: (value: string) => void;
}

export function GovernedMemoryEvidenceSection({
  t,
  evidence,
  filteredEvidence,
  evidenceTypeCounts,
  evidenceTypeFilter,
  onEvidenceTypeFilterChange,
}: GovernedMemoryEvidenceSectionProps) {
  return (
    <div className="rounded-lg border border-default dark:border-gray-700 p-4">
      <div className="text-sm font-semibold text-primary dark:text-gray-100 mb-3">
        {t('evidence' as any) || 'Evidence'}
      </div>
      {evidence.length > 0 && (
        <div className="flex flex-wrap gap-2 mb-3">
          <button
            onClick={() => onEvidenceTypeFilterChange('all')}
            className={`px-2.5 py-1 text-xs rounded transition-colors ${
              evidenceTypeFilter === 'all'
                ? 'bg-blue-600 text-white'
                : 'bg-surface-secondary dark:bg-gray-700 text-secondary dark:text-gray-300'
            }`}
          >
            {t('all' as any) || 'All'} ({evidence.length})
          </button>
          {Object.entries(evidenceTypeCounts).map(([evidenceType, count]) => (
            <button
              key={evidenceType}
              onClick={() => onEvidenceTypeFilterChange(evidenceType)}
              className={`px-2.5 py-1 text-xs rounded transition-colors ${
                evidenceTypeFilter === evidenceType
                  ? 'bg-blue-600 text-white'
                  : 'bg-surface-secondary dark:bg-gray-700 text-secondary dark:text-gray-300'
              }`}
            >
              {evidenceDisplayName(evidenceType, t)} ({count})
            </button>
          ))}
        </div>
      )}
      <div className="space-y-3">
        {evidence.length === 0 ? (
          <div className="text-sm text-secondary dark:text-gray-400">
            {t('noEvidence' as any) || 'No evidence links recorded.'}
          </div>
        ) : filteredEvidence.length === 0 ? (
          <div className="text-sm text-secondary dark:text-gray-400">
            {t('noEvidenceForFilter' as any) || 'No evidence matches this filter.'}
          </div>
        ) : (
          filteredEvidence.map((link) => (
            <GovernedMemoryEvidenceCard key={link.id} t={t} link={link} />
          ))
        )}
      </div>
    </div>
  );
}

interface GovernedMemoryEvidenceCardProps {
  t: TranslateFn;
  link: MemoryEvidenceSummary;
}

function GovernedMemoryEvidenceCard({ t, link }: GovernedMemoryEvidenceCardProps) {
  const metadataRows = evidenceMetadataRows(link, t);

  return (
    <div className="rounded bg-surface-accent dark:bg-gray-900/40 p-3">
      <div className="flex items-center gap-2 mb-1 flex-wrap">
        <span className="px-2 py-1 text-xs rounded bg-surface-secondary dark:bg-gray-700 text-secondary dark:text-gray-300">
          {evidenceDisplayName(link.evidence_type, t)}
        </span>
        <span className="px-2 py-1 text-xs rounded bg-surface-secondary dark:bg-gray-700 text-secondary dark:text-gray-300">
          {translateMappedValue(link.link_role, t, EVIDENCE_ROLE_KEYS)}
        </span>
        {typeof link.confidence === 'number' && (
          <span className="px-2 py-1 text-xs rounded bg-surface-secondary dark:bg-gray-700 text-secondary dark:text-gray-300">
            {(t('confidence' as any) || 'Confidence')} {Math.round(link.confidence * 100)}%
          </span>
        )}
      </div>
      <div className="text-xs text-secondary dark:text-gray-400 mb-2 font-mono break-all">
        {link.evidence_id}
      </div>
      {link.excerpt && (
        <div className="text-sm text-gray-800 dark:text-gray-200 whitespace-pre-wrap mb-3">
          {link.excerpt}
        </div>
      )}
      {metadataRows.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          {metadataRows.map((row) => (
            <div
              key={`${link.id}-${row.label}`}
              className="rounded border border-default dark:border-gray-700 px-2.5 py-2"
            >
              <div className="text-[11px] uppercase tracking-wide text-secondary dark:text-gray-400">
                {row.label}
              </div>
              <div className="text-xs text-primary dark:text-gray-200 break-all">
                {row.value}
              </div>
            </div>
          ))}
        </div>
      )}
      {link.artifact_landing && (
        <div className="mt-3 rounded border border-default dark:border-gray-700 p-3">
          <div className="text-xs font-semibold uppercase tracking-wide text-secondary dark:text-gray-400 mb-2">
            {t('landing' as any) || 'Landing'}
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 mb-3">
            <div className="rounded border border-default dark:border-gray-700 px-2.5 py-2">
              <div className="text-[11px] uppercase tracking-wide text-secondary dark:text-gray-400">
                {t('artifactDir' as any) || 'Artifact Dir'}
              </div>
              <div className="text-xs text-primary dark:text-gray-200">
                {link.artifact_landing.artifact_dir_exists
                  ? t('available' as any) || 'Available'
                  : t('missing' as any) || 'Missing'}
              </div>
            </div>
            <div className="rounded border border-default dark:border-gray-700 px-2.5 py-2">
              <div className="text-[11px] uppercase tracking-wide text-secondary dark:text-gray-400">
                {t('resultJson' as any) || 'Result JSON'}
              </div>
              <div className="text-xs text-primary dark:text-gray-200">
                {link.artifact_landing.result_json_exists
                  ? t('available' as any) || 'Available'
                  : t('missing' as any) || 'Missing'}
              </div>
            </div>
            <div className="rounded border border-default dark:border-gray-700 px-2.5 py-2">
              <div className="text-[11px] uppercase tracking-wide text-secondary dark:text-gray-400">
                {t('summaryFile' as any) || 'Summary File'}
              </div>
              <div className="text-xs text-primary dark:text-gray-200">
                {link.artifact_landing.summary_md_exists
                  ? t('available' as any) || 'Available'
                  : t('missing' as any) || 'Missing'}
              </div>
            </div>
          </div>
          <div className="space-y-2">
            {link.artifact_landing.landed_at && (
              <div className="text-xs text-secondary dark:text-gray-400">
                {(t('landedAt' as any) || 'Landed at')} {formatLocalDateTime(link.artifact_landing.landed_at)}
              </div>
            )}
            {link.artifact_landing.attachments.length > 0 && (
              <div>
                <div className="text-[11px] uppercase tracking-wide text-secondary dark:text-gray-400 mb-1">
                  {(t('attachments' as any) || 'Attachments')} ({link.artifact_landing.attachments_count})
                </div>
                <div className="flex flex-wrap gap-2">
                  {link.artifact_landing.attachments.map((attachmentPath) => (
                    <span
                      key={`${link.id}-${attachmentPath}`}
                      className="px-2 py-1 text-xs rounded bg-surface-secondary dark:bg-gray-700 text-secondary dark:text-gray-300"
                      title={attachmentPath}
                    >
                      {fileLabelFromPath(attachmentPath)}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
      {link.execution_trace_drilldown && (
        <div className="mt-3 rounded border border-default dark:border-gray-700 p-3">
          <div className="text-xs font-semibold uppercase tracking-wide text-secondary dark:text-gray-400 mb-2">
            {t('trace' as any) || 'Trace'}
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            <div className="rounded border border-default dark:border-gray-700 px-2.5 py-2">
              <div className="text-[11px] uppercase tracking-wide text-secondary dark:text-gray-400">
                {t('traceFile' as any) || 'Trace File'}
              </div>
              <div className="text-xs text-primary dark:text-gray-200 break-all">
                {link.execution_trace_drilldown.trace_file_path || (t('unavailable' as any) || 'Unavailable')}
              </div>
            </div>
            <div className="rounded border border-default dark:border-gray-700 px-2.5 py-2">
              <div className="text-[11px] uppercase tracking-wide text-secondary dark:text-gray-400">
                {t('traceFileStatus' as any) || 'Trace File Status'}
              </div>
              <div className="text-xs text-primary dark:text-gray-200">
                {link.execution_trace_drilldown.trace_file_exists
                  ? t('available' as any) || 'Available'
                  : t('missing' as any) || 'Missing'}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
