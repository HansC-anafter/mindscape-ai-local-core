'use client';

import { List, AlertCircle, UserCheck, AtSign, Clock, type LucideIcon } from 'lucide-react';
import PendingTasksPanel from '@/app/workspaces/components/PendingTasksPanel';
import { DecisionCard } from '../DecisionCard';
import { GovernedMemoryPreview } from '../governance/GovernedMemoryPreview';
import { WorkflowEvidenceSummary } from '../meeting/WorkflowEvidenceSummary';
import { InputDialog } from '../InputDialog';
import { BranchSelectionDialog } from '../BranchSelectionDialog';
import { IntentCardItem } from './IntentCardItem';
import type { DecisionFilter, DecisionPanelViewProps } from './types';

interface FilterOption {
  id: DecisionFilter;
  label: string;
  icon: LucideIcon;
  count: number;
}

export function DecisionPanelView({
  workspaceId,
  apiUrl,
  workspace,
  onViewArtifact,
  onSwitchToOutcomes,
  loading,
  pendingTaskCount,
  onPendingTaskCountChange,
  currentUserId,
  filteredDecisionCards,
  pendingCards,
  historyCards,
  blockerCount,
  assignedToMeCount,
  openDecisionCount,
  mentionedMeCount,
  waitingOnOthersCount,
  filter,
  onFilterChange,
  showLegacyTasks,
  onToggleLegacyTasks,
  showHistory,
  onToggleHistory,
  relatedContext,
  relatedMemoryLoading,
  inputDialog,
  branchDialog,
  onCloseInputDialog,
  onCloseBranchDialog,
  onIntentStatusChange,
  onExpandCard,
}: DecisionPanelViewProps) {
  const filterOptions: FilterOption[] = [
    {
      id: 'all',
      label: 'All',
      icon: List,
      count: openDecisionCount,
    },
    {
      id: 'blockers',
      label: 'Blockers',
      icon: AlertCircle,
      count: blockerCount,
    },
    {
      id: 'assigned-to-me',
      label: 'Assigned to Me',
      icon: UserCheck,
      count: assignedToMeCount,
    },
    {
      id: 'mentioned-me',
      label: 'Mentioned Me',
      icon: AtSign,
      count: mentionedMeCount,
    },
    {
      id: 'waiting-on-others',
      label: 'Waiting on Others',
      icon: Clock,
      count: waitingOnOthersCount,
    },
  ];

  return (
    <div className="decision-panel flex-1 flex flex-col overflow-hidden">
      <div className={`section-header decision-section-header ${blockerCount > 0 ? 'has-high-priority' : ''} px-3 py-2 bg-surface dark:bg-gray-800 border-b dark:border-gray-700`}>
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold">Pending Decisions</span>
            {filteredDecisionCards.length > 0 && (
              <span className="badge pending text-xs px-1.5 py-0.5 rounded bg-accent-10 dark:bg-blue-900/30 text-accent dark:text-blue-300">
                {filteredDecisionCards.length}
              </span>
            )}
            {blockerCount > 0 && (
              <span
                className="badge high-priority text-xs px-1.5 py-0.5 rounded bg-red-100 dark:bg-red-900/30 text-red-800 dark:text-red-300"
                title={`${blockerCount} blocker${blockerCount !== 1 ? 's' : ''}`}
              >
                {blockerCount}
              </span>
            )}
          </div>
        </div>

        <div className="flex gap-1 overflow-x-auto">
          {filterOptions.map(option => {
            const Icon = option.icon;
            const isActive = filter === option.id;
            return (
              <button
                key={option.id}
                onClick={() => onFilterChange(option.id)}
                className={`relative flex items-center justify-center gap-1.5 px-2 py-1.5 rounded transition-all ${
                  isActive
                    ? 'bg-accent dark:bg-blue-700 text-white'
                    : 'bg-surface-secondary dark:bg-gray-700 text-primary dark:text-gray-300 hover:bg-surface-secondary dark:hover:bg-gray-600'
                }`}
                title={!isActive ? `${option.label}${option.count > 0 ? ` (${option.count})` : ''}` : undefined}
              >
                <Icon className="w-4 h-4 flex-shrink-0" />
                {isActive && (
                  <span className="text-xs font-medium whitespace-nowrap">
                    {option.label}
                  </span>
                )}
                {option.count > 0 && (
                  <span className={`absolute -top-1 -right-1 min-w-[14px] h-[14px] px-1 text-[10px] leading-none flex items-center justify-center rounded-full ${
                    isActive
                      ? 'bg-surface-accent text-accent dark:text-blue-700'
                      : 'bg-red-500 text-white'
                  }`}>
                    {option.count > 99 ? '99+' : option.count}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto min-h-0 p-3 space-y-3">
        {relatedMemoryLoading && !relatedContext.memoryId ? (
          <div className="rounded border border-default dark:border-gray-700 bg-surface-secondary dark:bg-gray-800 px-3 py-2 text-sm text-secondary dark:text-gray-300">
            Loading governed memory detail...
          </div>
        ) : null}

        {relatedContext.workflowEvidenceProfile && (
          <WorkflowEvidenceSummary
            label="Workflow Evidence"
            profile={relatedContext.workflowEvidenceProfile}
            scope={relatedContext.workflowEvidenceScope}
            selectedLineCount={relatedContext.workflowEvidenceSelectedLines}
            totalLineBudget={relatedContext.workflowEvidenceTotalBudget}
            totalCandidateCount={relatedContext.workflowEvidenceTotalCandidates}
            totalDroppedCount={relatedContext.workflowEvidenceTotalDropped}
            renderedSectionCount={relatedContext.workflowEvidenceRenderedSections}
            budgetUtilizationRatio={relatedContext.workflowEvidenceUtilizationRatio}
            href={`/workspaces/${workspaceId}/meetings?${new URLSearchParams(
              relatedContext.meetingSessionId
                ? { session_id: relatedContext.meetingSessionId }
                : {}
            ).toString()}`}
            compact
          />
        )}

        {relatedContext.memoryId && (
          <GovernedMemoryPreview
            workspaceId={workspaceId}
            memoryItemId={relatedContext.memoryId}
            apiUrl={apiUrl}
            lifecycleStatus={relatedContext.memoryLifecycleStatus}
            verificationStatus={relatedContext.memoryVerificationStatus}
            compact
          />
        )}

        {filteredDecisionCards.length > 0 ? (
          <div className="space-y-3">
            {filteredDecisionCards.map(card => (
              <DecisionCard
                key={card.id}
                card={card}
                currentUserId={currentUserId}
                onExpand={onExpandCard}
              />
            ))}
          </div>
        ) : (
          !loading && (
            <div className="text-xs text-tertiary dark:text-gray-500 italic py-4 text-center">
              No pending decisions
            </div>
          )
        )}

        {(pendingCards.length > 0 || pendingTaskCount > 0) && (
          <div className="mt-4 pt-4 border-t border-default dark:border-gray-700">
            <div className="flex items-center justify-between mb-2">
              <div className="text-xs font-medium text-secondary dark:text-gray-400">
                Legacy Tasks - Will be migrated to unified decisions
              </div>
              <button
                onClick={onToggleLegacyTasks}
                className="text-[10px] text-tertiary dark:text-gray-500 hover:text-secondary dark:hover:text-gray-400"
              >
                {showLegacyTasks ? 'Hide' : 'Show'}
              </button>
            </div>

            {showLegacyTasks && (
              <>
                {pendingTaskCount > 0 && (
                  <div className="mb-4">
                    <div className="text-xs font-medium text-secondary dark:text-gray-400 mb-2">
                      Tasks requiring human confirmation / input
                    </div>
                    <PendingTasksPanel
                      workspaceId={workspaceId}
                      apiUrl={apiUrl}
                      onViewArtifact={onViewArtifact}
                      onSwitchToOutcomes={onSwitchToOutcomes}
                      workspace={workspace}
                      onTaskCountChange={onPendingTaskCountChange}
                    />
                  </div>
                )}

                {pendingCards.length > 0 && (
                  <div>
                    <div className="text-xs font-medium text-secondary dark:text-gray-400 mb-2">
                      Intent Card
                    </div>
                    <div className="space-y-2">
                      {pendingCards.map(card => (
                        <IntentCardItem
                          key={card.id}
                          card={card}
                          workspaceId={workspaceId}
                          apiUrl={apiUrl}
                          onStatusChange={onIntentStatusChange}
                        />
                      ))}
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        )}

        {historyCards.length > 0 && (
          <div className="history-intents border-t border-default dark:border-gray-700 pt-3">
            <button
              className="flex items-center gap-2 text-xs text-secondary dark:text-gray-400 hover:text-primary dark:hover:text-gray-300 transition-colors"
              onClick={onToggleHistory}
            >
              <span className="chevron">{showHistory ? '▼' : '▶'}</span>
              <span>History ({historyCards.length})</span>
            </button>

            {showHistory && (
              <div className="history-list mt-2 space-y-2">
                {historyCards.map(card => (
                  <IntentCardItem
                    key={card.id}
                    card={card}
                    collapsed
                    workspaceId={workspaceId}
                    apiUrl={apiUrl}
                    onStatusChange={onIntentStatusChange}
                  />
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {inputDialog && (
        <InputDialog
          title={inputDialog.title}
          fields={inputDialog.fields}
          onSubmit={inputDialog.onSubmit}
          onCancel={onCloseInputDialog}
        />
      )}

      {branchDialog && (
        <BranchSelectionDialog
          title={branchDialog.title}
          alternatives={branchDialog.alternatives}
          recommendedBranch={branchDialog.recommendedBranch}
          onSubmit={branchDialog.onSubmit}
          onCancel={onCloseBranchDialog}
        />
      )}
    </div>
  );
}
