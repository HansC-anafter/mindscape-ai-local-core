import {
  evidenceDisplayName,
} from './formatters';
import type {
  EvidenceCoverageSummary,
  MemoryEvidenceSummary,
  MemoryTransitionAction,
  SuccessorDraftSuggestion,
  TransitionCue,
  TranslateFn,
  WorkspaceMemoryItemSummary,
} from './types';

export function buildEvidenceCoverage(evidence: MemoryEvidenceSummary[]): EvidenceCoverageSummary {
  return evidence.reduce<EvidenceCoverageSummary>(
    (acc, link) => {
      if (
        link.evidence_type === 'session_digest' ||
        link.evidence_type === 'meeting_decision' ||
        link.evidence_type === 'reasoning_trace'
      ) {
        acc.deliberation += 1;
      }
      if (
        link.evidence_type === 'task_execution' ||
        link.evidence_type === 'execution_trace' ||
        link.evidence_type === 'stage_result' ||
        link.evidence_type === 'artifact_result' ||
        link.evidence_type === 'lens_receipt'
      ) {
        acc.execution += 1;
      }
      if (
        link.evidence_type === 'writeback_receipt' ||
        link.evidence_type === 'intent_log' ||
        link.evidence_type === 'governance_decision' ||
        link.evidence_type === 'lens_patch'
      ) {
        acc.governance += 1;
      }
      if (link.link_role === 'supports') {
        acc.support += 1;
      }
      if (link.link_role === 'derived_from') {
        acc.derived += 1;
      }
      return acc;
    },
    {
      deliberation: 0,
      execution: 0,
      governance: 0,
      support: 0,
      derived: 0,
    }
  );
}

export function buildTransitionCues(
  item: WorkspaceMemoryItemSummary,
  evidence: MemoryEvidenceSummary[],
  coverage: EvidenceCoverageSummary,
  translate: TranslateFn
): TransitionCue[] {
  const cues: TransitionCue[] = [];
  const hasOperationalEvidence = coverage.execution > 0 || coverage.governance > 0;
  const hasDeliberationEvidence = coverage.deliberation > 0;
  const hasArtifactOrTaskEvidence = evidence.some(
    (link) =>
      link.evidence_type === 'task_execution' ||
      link.evidence_type === 'execution_trace' ||
      link.evidence_type === 'stage_result' ||
      link.evidence_type === 'artifact_result'
  );
  const hasDecisionEvidence = evidence.some(
    (link) =>
      link.evidence_type === 'meeting_decision' ||
      link.evidence_type === 'intent_log' ||
      link.evidence_type === 'governance_decision' ||
      link.evidence_type === 'lens_patch'
  );

  if (item.lifecycle_status === 'candidate') {
    if (hasDeliberationEvidence && hasOperationalEvidence) {
      cues.push({
        id: 'verify-ready',
        tone: 'positive',
        title: translate('memoryCueVerifyReadyTitle'),
        body: translate('memoryCueVerifyReadyBody'),
      });
    } else {
      cues.push({
        id: 'verify-hold',
        tone: 'caution',
        title: translate('memoryCueHoldTitle'),
        body: translate('memoryCueHoldBody'),
      });
    }
  }

  if (item.lifecycle_status === 'active') {
    cues.push({
      id: 'stale-usage',
      tone: 'neutral',
      title: translate('memoryCueStaleTitle'),
      body: translate('memoryCueStaleBody'),
    });
    if (hasArtifactOrTaskEvidence || hasDecisionEvidence) {
      cues.push({
        id: 'supersede-usage',
        tone: 'positive',
        title: translate('memoryCueSupersedeTitle'),
        body: translate('memoryCueSupersedeBody'),
      });
    }
  }

  if (coverage.support === 0 && coverage.derived > 0) {
    cues.push({
      id: 'support-gap',
      tone: 'caution',
      title: translate('memoryCueSupportGapTitle'),
      body: translate('memoryCueSupportGapBody'),
    });
  }

  if (cues.length === 0) {
    cues.push({
      id: 'baseline',
      tone: 'neutral',
      title: translate('memoryCueBaselineTitle'),
      body: translate('memoryCueBaselineBody'),
    });
  }

  return cues;
}

function evidencePriority(link: MemoryEvidenceSummary): number {
  if (link.link_role === 'supports' && link.evidence_type === 'artifact_result') {
    return 0;
  }
  if (link.link_role === 'supports' && link.evidence_type === 'stage_result') {
    return 1;
  }
  if (link.link_role === 'supports' && link.evidence_type === 'task_execution') {
    return 2;
  }
  if (link.link_role === 'supports' && link.evidence_type === 'execution_trace') {
    return 3;
  }
  if (link.link_role === 'supports' && link.evidence_type === 'meeting_decision') {
    return 4;
  }
  if (link.link_role === 'supports' && link.evidence_type === 'governance_decision') {
    return 5;
  }
  if (link.link_role === 'supports' && link.evidence_type === 'lens_patch') {
    return 6;
  }
  if (link.link_role === 'supports' && link.evidence_type === 'intent_log') {
    return 7;
  }
  if (link.link_role === 'supports' && link.evidence_type === 'reasoning_trace') {
    return 8;
  }
  if (link.evidence_type === 'session_digest') {
    return 9;
  }
  if (link.evidence_type === 'lens_receipt') {
    return 10;
  }
  if (link.evidence_type === 'writeback_receipt') {
    return 11;
  }
  return 12;
}

export function selectPrimaryEvidence(evidence: MemoryEvidenceSummary[]): MemoryEvidenceSummary | null {
  if (evidence.length === 0) {
    return null;
  }
  const ranked = [...evidence].sort((a, b) => {
    const priorityDiff = evidencePriority(a) - evidencePriority(b);
    if (priorityDiff !== 0) {
      return priorityDiff;
    }
    return b.created_at.localeCompare(a.created_at);
  });
  return ranked[0] || null;
}

export function buildSuccessorDraftSuggestion(
  item: WorkspaceMemoryItemSummary,
  evidence: MemoryEvidenceSummary[],
  coverage: EvidenceCoverageSummary,
  translate: TranslateFn
): SuccessorDraftSuggestion {
  const primaryEvidence = selectPrimaryEvidence(evidence);
  const primaryExcerpt = primaryEvidence?.excerpt?.trim();
  const revisionSuffix = translate('revisionSuffix');
  const primaryLabel = primaryEvidence
    ? evidenceDisplayName(primaryEvidence.evidence_type, translate)
    : translate('evidence');
  const claim =
    primaryExcerpt ||
    item.claim ||
    item.summary ||
    translate('refineClaimFromEvidence');
  const title = item.title.toLowerCase().includes('revision') || item.title.endsWith(revisionSuffix)
    ? item.title
    : `${item.title} ${revisionSuffix}`;
  const summaryParts = [
    translate('successorDraftFromEvidence', { source: primaryLabel }),
    translate('successorDraftCoverage', {
      deliberation: String(coverage.deliberation),
      execution: String(coverage.execution),
      governance: String(coverage.governance),
    }),
  ];
  if (primaryEvidence?.evidence_id) {
    summaryParts.push(
      translate('successorDraftAnchorEvidence', {
        evidenceId: primaryEvidence.evidence_id,
      })
    );
  }
  return {
    title,
    claim,
    summary: summaryParts.join(' '),
  };
}

export function buildTransitionReasonSuggestion(
  action: MemoryTransitionAction,
  item: WorkspaceMemoryItemSummary,
  primaryEvidence: MemoryEvidenceSummary | null,
  coverage: EvidenceCoverageSummary,
  translate: TranslateFn
): string {
  const anchor = primaryEvidence
    ? `${evidenceDisplayName(primaryEvidence.evidence_type, translate)} ${primaryEvidence.evidence_id}`
    : translate('evidence');

  if (action === 'verify') {
    return translate('verifyReasonSuggestion', {
      anchor,
      deliberation: String(coverage.deliberation),
      downstream: String(coverage.execution + coverage.governance),
    });
  }
  if (action === 'stale') {
    return translate('staleReasonSuggestion', { anchor });
  }
  return translate('supersedeReasonSuggestion', {
    anchor,
    title: item.title,
  });
}
