'use client';

import React, { useState, useEffect } from 'react';
import { t } from '@/lib/i18n';
import { GovernanceDecisionDetail } from '@/app/workspaces/[workspaceId]/governance/components/GovernanceDecisionDetail';

interface GovernanceDecision {
  decision_id: string;
  timestamp: string;
  layer: 'cost' | 'node' | 'policy' | 'preflight';
  approved: boolean;
  reason?: string;
  playbook_code?: string;
  metadata?: {
    estimated_cost?: number;
    quota_limit?: number;
    rejection_reason?: string;
    violation_type?: string;
    missing_inputs?: string[];
  };
}

interface GovernanceTabProps {
  executionId: string;
  workspaceId: string;
  apiUrl: string;
}

export default function GovernanceTab({
  executionId,
  workspaceId,
  apiUrl,
}: GovernanceTabProps) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [decisions, setDecisions] = useState<GovernanceDecision[]>([]);
  const [selectedDecision, setSelectedDecision] = useState<GovernanceDecision | null>(null);

  useEffect(() => {
    loadGovernanceDecisions();
  }, [executionId, workspaceId]);

  const loadGovernanceDecisions = async () => {
    try {
      setLoading(true);
      setError(null);

      // Try to load from governance decisions API (Cloud)
      try {
        const response = await fetch(
          `${apiUrl}/api/v1/workspaces/${workspaceId}/governance/decisions?limit=50`
        );
        if (response.ok) {
          const data = await response.json();
          // Filter decisions for this execution
          const executionDecisions = (data.decisions || []).filter(
            (d: GovernanceDecision) => d.metadata?.execution_id === executionId
          );
          setDecisions(executionDecisions);
          setLoading(false);
          return;
        }
      } catch (err) {
        // Fallback to events API for Local-Core
      }

      // Fallback: Load from events API
      const response = await fetch(
        `${apiUrl}/api/v1/workspaces/${workspaceId}/events?event_types=decision_required&limit=100`
      );

      if (response.ok) {
        const data = await response.json();
        const governanceDecisions: GovernanceDecision[] = (data.events || [])
          .filter(
            (event: any) =>
              event.payload?.governance_decision &&
              event.metadata?.execution_id === executionId
          )
          .map((event: any) => ({
            decision_id: event.id,
            timestamp: event.timestamp,
            layer: event.payload.governance_decision.layer,
            approved: event.payload.governance_decision.approved,
            reason: event.payload.governance_decision.reason,
            playbook_code: event.payload.selected_playbook_code,
            metadata: {
              estimated_cost: event.payload.governance_decision.cost_governance?.estimated_cost,
              quota_limit: event.payload.governance_decision.cost_governance?.quota_limit,
              rejection_reason: event.payload.governance_decision.node_governance?.rejection_reason,
              violation_type: event.payload.governance_decision.policy_violation?.violation_type,
              missing_inputs: event.payload.governance_decision.preflight_failure?.missing_inputs,
            },
          }));
        setDecisions(governanceDecisions);
      } else {
        throw new Error('Failed to load governance decisions');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load governance decisions');
    } finally {
      setLoading(false);
    }
  };

  const layerColors = {
    cost: 'bg-red-100 dark:bg-red-900/30 text-red-800 dark:text-red-300',
    node: 'bg-orange-100 dark:bg-orange-900/30 text-orange-800 dark:text-orange-300',
    policy: 'bg-purple-100 dark:bg-purple-900/30 text-purple-800 dark:text-purple-300',
    preflight: 'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-800 dark:text-yellow-300',
  };

  if (loading) {
    return (
      <div className="p-4 text-center text-gray-500 dark:text-gray-400">
        {t('loading') || 'Loading...'}
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded">
        <p className="text-sm text-red-800 dark:text-red-300">{error}</p>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col">
      <div className="p-4 border-b border-gray-200 dark:border-gray-700">
        <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
          {t('governanceDecisions') || 'Governance Decisions'}
        </h3>
        <p className="text-xs text-gray-600 dark:text-gray-400 mt-1">
          {decisions.length} {t('decisions') || 'decisions'} for this execution
        </p>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-2">
        {decisions.length === 0 ? (
          <div className="text-center py-8 text-gray-500 dark:text-gray-400">
            <p className="text-sm">{t('noGovernanceDecisions') || 'No governance decisions found for this execution'}</p>
          </div>
        ) : (
          decisions.map((decision) => (
            <div
              key={decision.decision_id}
              className="p-3 bg-surface-secondary dark:bg-gray-800 rounded-lg border border-default dark:border-gray-700 cursor-pointer hover:bg-tertiary dark:hover:bg-gray-700/50 transition-colors"
              onClick={() => setSelectedDecision(decision)}
            >
              <div className="flex items-center gap-2 mb-2">
                <span
                  className={`px-2 py-1 text-xs font-medium rounded ${layerColors[decision.layer]}`}
                >
                  {decision.layer}
                </span>
                <span
                  className={`px-2 py-1 text-xs font-medium rounded ${
                    decision.approved
                      ? 'bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-300'
                      : 'bg-red-100 dark:bg-red-900/30 text-red-800 dark:text-red-300'
                  }`}
                >
                  {decision.approved ? t('approved') || 'Approved' : t('rejected') || 'Rejected'}
                </span>
              </div>
              {decision.reason && (
                <p className="text-xs text-gray-700 dark:text-gray-300 mb-1 line-clamp-2">
                  {decision.reason}
                </p>
              )}
              <p className="text-xs text-gray-500 dark:text-gray-400">
                {new Date(decision.timestamp).toLocaleString()}
              </p>
            </div>
          ))
        )}
      </div>

      {selectedDecision && (
        <GovernanceDecisionDetail
          decision={selectedDecision}
          onClose={() => setSelectedDecision(null)}
        />
      )}
    </div>
  );
}

