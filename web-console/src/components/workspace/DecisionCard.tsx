'use client';

import React, { useState } from 'react';
import { useT } from '@/lib/i18n';
import { GovernanceDecisionCard } from './governance/GovernanceDecisionCard';

/**
 * DecisionCard - Unified decision card component
 *
 * Unifies all blocking items into a single card type with variants: decision / input / review / assignment
 * Fixed fields: why needed, what is blocked, action required, what happens after action
 */
export interface DecisionCardData {
  id: string;
  type: 'decision' | 'input' | 'review' | 'assignment' | 'governance';
  governance_type?: 'cost_exceeded' | 'node_rejected' | 'policy_violation' | 'preflight_failed';
  title: string;
  description: string;
  blocks: {
    steps: string[];
    count: number;
    stepNames?: string[];
  };
  action: {
    type: 'confirm' | 'reject' | 'upload' | 'select' | 'assign';
    label: string;
    onClick: () => void | Promise<void>;
  };
  result: {
    autoRun: boolean;
    outputLocation?: string;
    message?: string;
  };
  expandable?: {
    evidence?: any;
    preview?: any;
    diff?: any;
    risk?: string;
    affectedSteps?: string[];
    governance_data?: {
      cost_governance?: {
        estimated_cost: number;
        quota_limit: number;
        current_usage: number;
        downgrade_suggestion?: {
          profile: string;
          estimated_cost: number;
        };
      };
      node_governance?: {
        rejection_reason: 'blacklist' | 'risk_label' | 'throttle';
        affected_playbooks?: string[];
        alternatives?: string[];
      };
      policy_violation?: {
        violation_type: 'role' | 'data_domain' | 'pii';
        policy_id?: string;
        violation_items: string[];
        request_permission_url?: string;
      };
      preflight_failure?: {
        missing_inputs: string[];
        missing_credentials: string[];
        environment_issues: string[];
        recommended_alternatives?: string[];
      };
    };
  };
  assignee?: string;
  watchers?: string[];
  status: 'OPEN' | 'NEED_INFO' | 'IN_REVIEW' | 'DONE' | 'REJECTED';
  priority: 'blocker' | 'high' | 'normal';
  dueAt?: Date;
  createdAt?: Date;
}

interface DecisionCardProps {
  card: DecisionCardData;
  currentUserId?: string;
  onExpand?: (cardId: string) => void;
  onAssign?: (cardId: string, assignee: string) => void;
  onMention?: (cardId: string, userIds: string[]) => void;
}

export function DecisionCard({
  card,
  currentUserId,
  onExpand,
  onAssign,
  onMention,
}: DecisionCardProps) {
  const t = useT();
  const [isExpanded, setIsExpanded] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);

  const isAssignedToMe = card.assignee === currentUserId;
  const isMentioned = card.watchers?.includes(currentUserId || '');
  const isBlocker = card.priority === 'blocker';

  const priorityColors = {
    blocker: 'bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800',
    high: 'bg-yellow-50 dark:bg-yellow-900/20 border-yellow-200 dark:border-yellow-800',
    normal: 'bg-gray-50 dark:bg-gray-800 border-gray-200 dark:border-gray-700',
  };

  const statusColors = {
    OPEN: 'bg-blue-50 dark:bg-blue-900/20',
    NEED_INFO: 'bg-orange-50 dark:bg-orange-900/20',
    IN_REVIEW: 'bg-purple-50 dark:bg-purple-900/20',
    DONE: 'bg-green-50 dark:bg-green-900/20',
    REJECTED: 'bg-gray-50 dark:bg-gray-800',
  };

  const handleAction = async () => {
    if (isProcessing) return;
    setIsProcessing(true);
    try {
      await card.action.onClick();
    } catch (error) {
      console.error('Decision card action failed:', error);
    } finally {
      setIsProcessing(false);
    }
  };

  const handleExpand = () => {
    setIsExpanded(!isExpanded);
    if (!isExpanded && onExpand) {
      onExpand(card.id);
    }
  };

  // Render governance decision card if type is governance
  if (card.type === 'governance') {
    return (
      <GovernanceDecisionCard
        card={card}
        currentUserId={currentUserId}
        onAction={(cardId, actionType) => {
          if (card.action.onClick) {
            card.action.onClick();
          }
        }}
      />
    );
  }

  return (
    <div
      className={`border rounded-lg p-3 transition-all ${
        priorityColors[card.priority]
      } ${statusColors[card.status]} ${
        isBlocker ? 'ring-2 ring-red-300 dark:ring-red-700' : ''
      } ${isAssignedToMe ? 'ring-2 ring-blue-300 dark:ring-blue-700' : ''}`}
    >
      {/* Header */}
      <div className="flex items-start justify-between mb-2">
        <div className="flex-1 min-w-0">
          {/* Title and Type */}
          <div className="flex items-center gap-2 mb-1">
            <span className="text-sm font-semibold text-gray-900 dark:text-gray-100 truncate">
              {card.title}
            </span>
            <span className="text-xs px-1.5 py-0.5 rounded bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 flex-shrink-0">
              {card.type}
            </span>
            {isBlocker && (
              <span className="text-xs px-1.5 py-0.5 rounded bg-red-100 dark:bg-red-900/30 text-red-800 dark:text-red-300 flex-shrink-0">
                Blocking
              </span>
            )}
            {isAssignedToMe && (
              <span className="text-xs px-1.5 py-0.5 rounded bg-blue-100 dark:bg-blue-900/30 text-blue-800 dark:text-blue-300 flex-shrink-0">
                Assigned to me
              </span>
            )}
            {isMentioned && !isAssignedToMe && (
              <span className="text-xs px-1.5 py-0.5 rounded bg-purple-100 dark:bg-purple-900/30 text-purple-800 dark:text-purple-300 flex-shrink-0">
                Mentioned me
              </span>
            )}
          </div>

          <div className="text-xs text-gray-600 dark:text-gray-400 mb-2">
            {card.description}
          </div>
        </div>

        <span className={`text-[10px] px-1.5 py-0.5 rounded flex-shrink-0 ${
          card.status === 'OPEN' ? 'bg-blue-100 dark:bg-blue-900/30 text-blue-800 dark:text-blue-300' :
          card.status === 'NEED_INFO' ? 'bg-orange-100 dark:bg-orange-900/30 text-orange-800 dark:text-orange-300' :
          card.status === 'IN_REVIEW' ? 'bg-purple-100 dark:bg-purple-900/30 text-purple-800 dark:text-purple-300' :
          card.status === 'DONE' ? 'bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-300' :
          'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300'
        }`}>
          {card.status === 'OPEN' ? 'Open' :
           card.status === 'NEED_INFO' ? 'Need Info' :
           card.status === 'IN_REVIEW' ? 'In Review' :
           card.status === 'DONE' ? 'Done' :
           'Rejected'}
        </span>
      </div>

      {card.blocks.count > 0 && (
        <div className="mb-2 p-2 bg-gray-100 dark:bg-gray-800 rounded text-xs">
          <div className="font-medium text-gray-700 dark:text-gray-300 mb-1">
            Blocking {card.blocks.count} step{card.blocks.count !== 1 ? 's' : ''}
          </div>
          {card.blocks.stepNames && card.blocks.stepNames.length > 0 && (
            <div className="text-gray-600 dark:text-gray-400">
              {card.blocks.stepNames.slice(0, 3).join(', ')}
              {card.blocks.stepNames.length > 3 && ` and ${card.blocks.stepNames.length - 3} more`}
            </div>
          )}
        </div>
      )}

      {card.status === 'OPEN' || card.status === 'NEED_INFO' ? (
        <div className="mb-2">
          <button
            onClick={handleAction}
            disabled={isProcessing}
            className={`w-full px-3 py-2 text-xs font-medium rounded transition-all ${
              isProcessing
                ? 'bg-gray-400 dark:bg-gray-600 text-white cursor-not-allowed opacity-75'
                : card.action.type === 'confirm'
                ? 'bg-blue-600 dark:bg-blue-700 text-white hover:bg-blue-700 dark:hover:bg-blue-600'
                : card.action.type === 'reject'
                ? 'bg-red-600 dark:bg-red-700 text-white hover:bg-red-700 dark:hover:bg-red-600'
                : 'bg-gray-600 dark:bg-gray-700 text-white hover:bg-gray-700 dark:hover:bg-gray-600'
            }`}
          >
            {isProcessing ? (
              <div className="flex items-center justify-center gap-2">
                <div className="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                <span>Processing...</span>
              </div>
            ) : (
              card.action.label
            )}
          </button>
        </div>
      ) : null}

      {card.result.message && (
        <div className="mb-2 p-2 bg-blue-50 dark:bg-blue-900/20 rounded text-xs text-blue-700 dark:text-blue-300">
          {card.result.message}
          {card.result.autoRun && ' System will start execution automatically'}
          {card.result.outputLocation && ` Output location: ${card.result.outputLocation}`}
        </div>
      )}

      {card.expandable && (
        <div className="mt-2">
          <button
            onClick={handleExpand}
            className="text-xs text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 flex items-center gap-1"
          >
            <span>{isExpanded ? '▼' : '▶'}</span>
            <span>{isExpanded ? 'Collapse' : 'View Details'}</span>
          </button>

          {isExpanded && (
            <div className="mt-2 space-y-2 text-xs">
              {card.expandable.evidence && (
                <div className="p-2 bg-gray-50 dark:bg-gray-800 rounded">
                  <div className="font-medium mb-1">Evidence/Source</div>
                  <div className="text-gray-600 dark:text-gray-400">
                    {JSON.stringify(card.expandable.evidence, null, 2)}
                  </div>
                </div>
              )}

              {card.expandable.risk && (
                <div className="p-2 bg-yellow-50 dark:bg-yellow-900/20 rounded">
                  <div className="font-medium mb-1">Risk Warning</div>
                  <div className="text-yellow-700 dark:text-yellow-300">
                    {card.expandable.risk}
                  </div>
                </div>
              )}

              {card.expandable.affectedSteps && card.expandable.affectedSteps.length > 0 && (
                <div className="p-2 bg-gray-50 dark:bg-gray-800 rounded">
                  <div className="font-medium mb-1">Affected Steps</div>
                  <div className="text-gray-600 dark:text-gray-400">
                    {card.expandable.affectedSteps.join(', ')}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Assignment Info */}
      {(card.assignee || card.watchers?.length) && (
        <div className="mt-2 pt-2 border-t border-gray-200 dark:border-gray-700 text-[10px] text-gray-500 dark:text-gray-400">
          {card.assignee && (
            <div>Assignee: {card.assignee}</div>
          )}
          {card.watchers && card.watchers.length > 0 && (
            <div>Watchers: {card.watchers.join(', ')}</div>
          )}
        </div>
      )}
    </div>
  );
}

