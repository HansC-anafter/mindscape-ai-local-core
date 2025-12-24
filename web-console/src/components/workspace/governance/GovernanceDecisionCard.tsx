'use client';

import React from 'react';
import { DecisionCardData } from '../DecisionCard';
import { CostExceededCard } from './CostExceededCard';
import { NodeGovernanceRejectedCard } from './NodeGovernanceRejectedCard';
import { PolicyViolationCard } from './PolicyViolationCard';
import { PreflightFailedCard } from './PreflightFailedCard';

interface GovernanceDecisionCardProps {
  card: DecisionCardData;
  currentUserId?: string;
  onAction?: (cardId: string, actionType: string) => void;
}

/**
 * Unified governance decision card component
 * Routes to specific governance card components based on governance_type
 */
export function GovernanceDecisionCard({
  card,
  currentUserId,
  onAction,
}: GovernanceDecisionCardProps) {
  if (card.type !== 'governance' || !card.governance_type) {
    return null;
  }

  const commonProps = {
    card,
    currentUserId,
    onAction,
  };

  switch (card.governance_type) {
    case 'cost_exceeded':
      return <CostExceededCard {...commonProps} />;
    case 'node_rejected':
      return <NodeGovernanceRejectedCard {...commonProps} />;
    case 'policy_violation':
      return <PolicyViolationCard {...commonProps} />;
    case 'preflight_failed':
      return <PreflightFailedCard {...commonProps} />;
    default:
      return null;
  }
}

