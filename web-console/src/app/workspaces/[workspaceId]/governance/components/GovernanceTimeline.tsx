'use client';

import React, { useState, useEffect } from 'react';
import { t } from '@/lib/i18n';
import { GovernanceDecisionDetail } from './GovernanceDecisionDetail';
import { getApiBaseUrl } from '../../../../../lib/api-url';

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

interface GovernanceTimelineProps {
  workspaceId: string;
}

export function GovernanceTimeline({ workspaceId }: GovernanceTimelineProps) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [decisions, setDecisions] = useState<GovernanceDecision[]>([]);
  const [selectedDecision, setSelectedDecision] = useState<GovernanceDecision | null>(null);
  const [filters, setFilters] = useState<{
    layer?: string;
    approved?: boolean;
    startDate?: string;
    endDate?: string;
  }>({});
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);

  useEffect(() => {
    loadDecisions();
  }, [workspaceId, filters, page]);

  const loadDecisions = async () => {
    try {
      setLoading(true);
      setError(null);

      const apiUrl = getApiBaseUrl();
      const params = new URLSearchParams({
        page: page.toString(),
        limit: '50',
      });

      if (filters.layer) params?.append('layer', filters.layer);
      if (filters.approved !== undefined) params?.append('approved', filters.approved.toString());
      if (filters.startDate) params?.append('start_date', filters.startDate);
      if (filters.endDate) params?.append('end_date', filters.endDate);

      const response = await fetch(
        `${apiUrl}/api/v1/workspaces/${workspaceId}/governance/decisions?${params?.toString()}`
      );

      if (!response.ok) {
        if (response.status === 404) {
          // Fallback to events API for Local-Core
          await loadFromEvents();
          return;
        }
        throw new Error('Failed to load governance decisions');
      }

      const data = await response.json();
      setDecisions(data.decisions || []);
      setTotalPages(data.total_pages || 1);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load decisions');
    } finally {
      setLoading(false);
    }
  };

  const loadFromEvents = async () => {
    try {
      const apiUrl = getApiBaseUrl();
      const response = await fetch(
        `${apiUrl}/api/v1/workspaces/${workspaceId}/events?event_types=decision_required&limit=100`
      );

      if (response.ok) {
        const data = await response.json();
        const governanceDecisions: GovernanceDecision[] = (data.events || [])
          .filter((event: any) => event.payload?.governance_decision)
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
      }
    } catch (err) {
      console.error('Failed to load from events:', err);
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
      <div className="text-center py-8 text-gray-500 dark:text-gray-400">
        {t('loading' as any) || 'Loading...'}
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4">
        <p className="text-sm text-red-800 dark:text-red-300">{error}</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div>
            <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
              {t('layer' as any) || 'Layer'}
            </label>
            <select
              value={filters.layer || ''}
              onChange={(e) => setFilters({ ...filters, layer: e.target.value || undefined })}
              className="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
            >
              <option value="">{t('all' as any) || 'All'}</option>
              <option value="cost">{t('cost' as any) || 'Cost'}</option>
              <option value="node">{t('node' as any) || 'Node'}</option>
              <option value="policy">{t('policy' as any) || 'Policy'}</option>
              <option value="preflight">{t('preflight' as any) || 'Preflight'}</option>
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
              {t('status' as any) || 'Status'}
            </label>
            <select
              value={filters.approved === undefined ? '' : filters.approved.toString()}
              onChange={(e) =>
                setFilters({
                  ...filters,
                  approved: e.target.value === '' ? undefined : e.target.value === 'true',
                })
              }
              className="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
            >
              <option value="">{t('all' as any) || 'All'}</option>
              <option value="true">{t('approved' as any) || 'Approved'}</option>
              <option value="false">{t('rejected' as any) || 'Rejected'}</option>
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
              {t('startDate' as any) || 'Start Date'}
            </label>
            <input
              type="date"
              value={filters.startDate || ''}
              onChange={(e) => setFilters({ ...filters, startDate: e.target.value || undefined })}
              className="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
              {t('endDate' as any) || 'End Date'}
            </label>
            <input
              type="date"
              value={filters.endDate || ''}
              onChange={(e) => setFilters({ ...filters, endDate: e.target.value || undefined })}
              className="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
            />
          </div>
        </div>
      </div>

      <div className="space-y-2">
        {decisions.length === 0 ? (
          <div className="text-center py-8 text-gray-500 dark:text-gray-400">
            {t('noDecisionsFound' as any) || 'No governance decisions found'}
          </div>
        ) : (
          decisions.map((decision) => (
            <div
              key={decision.decision_id}
              className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4 cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors"
              onClick={() => setSelectedDecision(decision)}
            >
              <div className="flex items-start justify-between">
                <div className="flex-1">
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
                      {decision.approved ? t('approved' as any) || 'Approved' : t('rejected' as any) || 'Rejected'}
                    </span>
                    {decision.playbook_code && (
                      <span className="text-xs text-gray-600 dark:text-gray-400">
                        {decision.playbook_code}
                      </span>
                    )}
                  </div>
                  {decision.reason && (
                    <p className="text-sm text-gray-700 dark:text-gray-300">{decision.reason}</p>
                  )}
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                    {new Date(decision.timestamp).toLocaleString()}
                  </p>
                </div>
              </div>
            </div>
          ))
        )}
      </div>

      {totalPages > 1 && (
        <div className="flex justify-center gap-2">
          <button
            onClick={() => setPage(Math.max(1, page - 1))}
            disabled={page === 1}
            className="px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {t('previous' as any) || 'Previous'}
          </button>
          <span className="px-3 py-2 text-sm text-gray-700 dark:text-gray-300">
            {t('page' as any) || 'Page'} {page} / {totalPages}
          </span>
          <button
            onClick={() => setPage(Math.min(totalPages, page + 1))}
            disabled={page === totalPages}
            className="px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {t('next' as any) || 'Next'}
          </button>
        </div>
      )}

      {selectedDecision && (
        <GovernanceDecisionDetail
          decision={selectedDecision}
          onClose={() => setSelectedDecision(null)}
        />
      )}
    </div>
  );
}

