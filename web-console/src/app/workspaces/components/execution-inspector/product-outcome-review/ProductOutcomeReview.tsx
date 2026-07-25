'use client';

import { buildIterationSummaryEndpoint } from './api';
import { DevelopmentCandidateProvenance } from './DevelopmentCandidateProvenance';
import { EvidenceFrontier } from './EvidenceFrontier';
import { EvidenceLifecycleState } from './EvidenceLifecycleState';
import { EvaluationHistory } from './EvaluationHistory';
import { ExperienceSummary } from './ExperienceSummary';
import { OutcomeGateMatrix } from './OutcomeGateMatrix';
import { OutcomeTimeTravelControls } from './OutcomeTimeTravelControls';
import { ProductIterationSummary } from './ProductIterationSummary';
import { ProductOutcomeReviewLensSlot } from './ProductOutcomeReviewLensSlot';
import { ProductReleaseHealth } from './ProductReleaseHealth';
import { useProductOutcomeReview } from './useProductOutcomeReview';
import { ValidationDesignValidity } from './ValidationDesignValidity';

interface Props {
  active: boolean;
  apiUrl: string;
  workspaceId: string;
  iterationId: string;
  genericReviewHref: string;
  onAsOf: (sequence: number) => void;
  onReEvaluate: () => void;
  onFork: () => void;
  onCompare: () => void;
}

export function ProductOutcomeReview({
  active,
  apiUrl,
  workspaceId,
  iterationId,
  genericReviewHref,
  onAsOf,
  onReEvaluate,
  onFork,
  onCompare,
}: Props) {
  const { summary, loading, error } = useProductOutcomeReview({
    active,
    apiUrl,
    workspaceId,
    iterationId,
  });
  if (!active) return null;
  if (loading && !summary) return <p>Loading product outcome…</p>;
  if (error && !summary) return <p role="alert">{error}</p>;
  if (!summary) return null;
  const endpoint = buildIterationSummaryEndpoint(
    apiUrl,
    workspaceId,
    iterationId,
  );
  return (
    <div className="space-y-4" data-testid="product-outcome-review">
      <ProductIterationSummary summary={summary} />
      <DevelopmentCandidateProvenance arms={summary.arms} />
      <ValidationDesignValidity
        validationDesign={summary.validation_design}
        evaluator={summary.evaluator}
      />
      <OutcomeGateMatrix gates={summary.gate_results} />
      <EvidenceFrontier frontier={summary.evidence_frontier} />
      <EvaluationHistory summary={summary} />
      <ProductReleaseHealth release={summary.product_release} />
      <EvidenceLifecycleState lifecycle={summary.evidence_lifecycle} />
      <ExperienceSummary summary={summary.experience_summary} />
      <OutcomeTimeTravelControls
        currentSequence={summary.current_sequence}
        onAsOf={onAsOf}
        onReEvaluate={onReEvaluate}
        onFork={onFork}
        onCompare={onCompare}
      />
      <ProductOutcomeReviewLensSlot
        active={active}
        apiUrl={apiUrl}
        workspaceId={workspaceId}
        iterationId={iterationId}
        summaryEndpoint={endpoint}
        genericReviewHref={genericReviewHref}
        pin={summary.review_lens}
      />
    </div>
  );
}
