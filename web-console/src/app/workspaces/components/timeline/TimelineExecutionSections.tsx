'use client';

import React, { useMemo, useState } from 'react';

import { useT } from '@/lib/i18n';

import OutcomesPanel from '../../[workspaceId]/components/OutcomesPanel';
import ArchivedTimelineItem from '../ArchivedTimelineItem';
import PendingTimelineItem from '../PendingTimelineItem';
import RunningTimelineItem from '../RunningTimelineItem';
import {
  getCurrentExecutionStep,
  getFocusedExecutionGroups,
  getTimelineExecutionBuckets,
  isPendingConfirmationExecution,
} from './helpers';
import type {
  ExecutionSession,
  ExecutionStep,
  PendingRestartInfo,
} from './types';

interface TimelineExecutionSectionsProps {
  executions: ExecutionSession[];
  executionSteps: Map<string, ExecutionStep[]>;
  focusExecutionId?: string | null;
  onClearFocus?: () => void;
  showArchivedOnly?: boolean;
  onArtifactClick?: (artifact: any) => void;
  onExecutionClick: (executionId: string) => void;
  onExecutionUpdate: (
    previousExecution: ExecutionSession,
    updatedExecution: ExecutionSession,
    updatedStep?: ExecutionStep
  ) => void;
  onRefreshExecutions: () => Promise<void>;
  pendingRestart: PendingRestartInfo | null;
  apiUrl: string;
  workspaceId: string;
}

interface CollapsibleSectionProps {
  title: string;
  sectionKey: string;
  count: number;
  collapsedSections: Set<string>;
  onToggle: (sectionKey: string) => void;
  headerClassName: string;
  emptyState?: React.ReactNode;
  children: React.ReactNode;
}

function CollapsibleSection({
  title,
  sectionKey,
  count,
  collapsedSections,
  onToggle,
  headerClassName,
  emptyState,
  children,
}: CollapsibleSectionProps) {
  const isCollapsed = collapsedSections.has(sectionKey);

  return (
    <div className="space-y-2">
      <div
        className={`sticky top-0 z-10 flex cursor-pointer items-center gap-1 px-1 py-1 text-xs font-semibold ${headerClassName}`}
        onClick={() => onToggle(sectionKey)}
      >
        <span className="select-none">{isCollapsed ? '▶' : '▼'}</span>
        <span>
          {title} {count > 0 ? `(${count})` : ''}
        </span>
      </div>
      {!isCollapsed ? count > 0 ? children : emptyState : null}
    </div>
  );
}

export default function TimelineExecutionSections({
  executions,
  executionSteps,
  focusExecutionId = null,
  onClearFocus,
  showArchivedOnly = false,
  onArtifactClick,
  onExecutionClick,
  onExecutionUpdate,
  onRefreshExecutions,
  pendingRestart,
  apiUrl,
  workspaceId,
}: TimelineExecutionSectionsProps) {
  const t = useT();
  const [collapsedSections, setCollapsedSections] = useState<Set<string>>(new Set());

  const focusedGroups = useMemo(
    () =>
      focusExecutionId
        ? getFocusedExecutionGroups(executions, focusExecutionId)
        : null,
    [executions, focusExecutionId]
  );

  const {
    pendingConfirmationExecutions,
    runningExecutions,
    archivedExecutions,
  } = useMemo(
    () => getTimelineExecutionBuckets(executions, executionSteps),
    [executions, executionSteps]
  );

  const toggleSection = (sectionKey: string) => {
    setCollapsedSections((previous) => {
      const next = new Set(previous);
      if (next.has(sectionKey)) {
        next.delete(sectionKey);
      } else {
        next.add(sectionKey);
      }
      return next;
    });
  };

  const renderExecutionItem = (
    execution: ExecutionSession,
    archivedOpenMode: 'click' | 'console' = 'click'
  ) => {
    const currentStep = getCurrentExecutionStep(execution, executionSteps);

    if (isPendingConfirmationExecution(execution, executionSteps) && currentStep) {
      return (
        <PendingTimelineItem
          key={execution.execution_id}
          execution={execution}
          currentStep={currentStep}
          apiUrl={apiUrl}
          workspaceId={workspaceId}
          onClick={() => onExecutionClick(execution.execution_id)}
          onAction={() => {
            void onRefreshExecutions();
          }}
        />
      );
    }

    if (execution.status === 'running') {
      return (
        <RunningTimelineItem
          key={execution.execution_id}
          execution={execution}
          currentStep={currentStep || undefined}
          apiUrl={apiUrl}
          workspaceId={workspaceId}
          onClick={() => onExecutionClick(execution.execution_id)}
          onUpdate={(updatedExecution, updatedStep) =>
            onExecutionUpdate(execution, updatedExecution, updatedStep)
          }
        />
      );
    }

    if (archivedOpenMode === 'console') {
      return (
        <ArchivedTimelineItem
          key={execution.execution_id}
          execution={execution}
          onOpenConsole={() => onExecutionClick(execution.execution_id)}
        />
      );
    }

    return (
      <ArchivedTimelineItem
        key={execution.execution_id}
        execution={execution}
        onClick={() => onExecutionClick(execution.execution_id)}
      />
    );
  };

  if (focusExecutionId && focusedGroups?.currentExecution) {
    return (
      <div className="space-y-4">
        {onClearFocus ? (
          <div className="border-b px-2 pb-2 dark:border-gray-700">
            <button
              onClick={() => {
                onClearFocus();
                window.dispatchEvent(new CustomEvent('clear-execution-focus'));
              }}
              className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm text-blue-600 transition-colors hover:bg-blue-50 dark:text-blue-400 dark:hover:bg-blue-900/20"
            >
              <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M10 19l-7-7m0 0l7-7m-7 7h18"
                />
              </svg>
              {t('returnToWorkspaceOverview' as any)}
            </button>
          </div>
        ) : null}

        <div>
          <h3 className="mb-2 px-2 text-xs font-semibold text-primary dark:text-gray-300">
            {t('currentExecution' as any)}
          </h3>
          {renderExecutionItem(focusedGroups.currentExecution)}
        </div>

        {focusedGroups.samePlaybookExecutions.length > 0 ? (
          <div>
            <h3 className="mb-2 px-2 text-xs font-semibold text-primary dark:text-gray-300">
              {t('otherExecutionsOfSamePlaybook' as any)}
            </h3>
            <div className="space-y-2">
              {focusedGroups.samePlaybookExecutions.map((execution) =>
                renderExecutionItem(execution)
              )}
            </div>
          </div>
        ) : null}

        {focusedGroups.otherPlaybookExecutions.length > 0 ? (
          <CollapsibleSection
            title={t('otherPlaybooksExecutions' as any)}
            sectionKey="other_playbooks"
            count={focusedGroups.otherPlaybookExecutions.length}
            collapsedSections={collapsedSections}
            onToggle={toggleSection}
            headerClassName="justify-between rounded-lg text-primary hover:bg-surface-secondary dark:text-gray-300 dark:hover:bg-gray-700"
          >
            <div className="mt-2 space-y-2">
              {focusedGroups.otherPlaybookExecutions.map((execution) =>
                renderExecutionItem(execution)
              )}
            </div>
          </CollapsibleSection>
        ) : null}
      </div>
    );
  }

  if (showArchivedOnly) {
    return (
      <div className="space-y-4">
        <div className="space-y-1">
          <div className="sticky top-0 z-10 bg-surface-secondary px-1 py-1 text-xs font-semibold text-secondary dark:bg-gray-900 dark:text-gray-300">
            <span>{t('tabOutcomes' as any) || 'Outcomes'}</span>
          </div>
          <div className="px-1">
            <OutcomesPanel
              workspaceId={workspaceId}
              apiUrl={apiUrl}
              onArtifactClick={onArtifactClick}
            />
          </div>
        </div>

        <CollapsibleSection
          title={t('timelineArchived' as any)}
          sectionKey="archived"
          count={archivedExecutions.length}
          collapsedSections={collapsedSections}
          onToggle={toggleSection}
          headerClassName="bg-surface-secondary text-secondary hover:bg-surface-accent dark:bg-gray-900 dark:text-gray-300 dark:hover:bg-gray-800"
          emptyState={
            <div className="px-1 py-2 text-xs text-tertiary opacity-60 dark:text-gray-300">
              {t('noArchivedExecutions' as any)}
            </div>
          }
        >
          <>
            {archivedExecutions.map((execution) =>
              renderExecutionItem(execution, 'console')
            )}
          </>
        </CollapsibleSection>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <CollapsibleSection
        title={t('timelineRunning' as any)}
        sectionKey="running"
        count={runningExecutions.length}
        collapsedSections={collapsedSections}
        onToggle={toggleSection}
        headerClassName="bg-surface-accent text-primary hover:bg-surface-secondary dark:bg-gray-900 dark:text-gray-300 dark:hover:bg-gray-800"
        emptyState={
          <div className="px-1 py-2 text-xs text-tertiary dark:text-gray-300">
            {t('noRunningExecutions' as any)}
          </div>
        }
      >
        <>
          {pendingRestart ? (
            <div className="rounded border border-blue-200 bg-blue-50 p-2 shadow-sm dark:border-blue-800 dark:bg-blue-900/20">
              <div className="mb-1 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-medium text-blue-900 dark:text-blue-200">
                    {pendingRestart.playbook_code || 'Playbook Execution'}
                  </span>
                  <span className="inline-block rounded border border-blue-300 bg-blue-100 px-1.5 py-0.5 text-xs text-blue-700 dark:border-blue-700 dark:bg-blue-900/30 dark:text-blue-300">
                    {t('restarting' as any) || 'Restarting'}
                  </span>
                </div>
              </div>
              <div className="mb-2">
                <div className="h-1.5 w-full overflow-hidden rounded-full bg-blue-200 dark:bg-blue-800">
                  <div
                    className="h-1.5 rounded-full bg-blue-500 dark:bg-blue-600"
                    style={{
                      width: '100%',
                      background:
                        'linear-gradient(90deg, #3b82f6 0%, #60a5fa 50%, #3b82f6 100%)',
                    }}
                  />
                </div>
              </div>
              <div className="flex items-start gap-2">
                <div className="mt-0.5 flex-shrink-0">
                  <div className="relative h-4 w-4">
                    <div className="absolute inset-0 animate-spin rounded-full border-2 border-blue-300 border-t-blue-600 dark:border-blue-500 dark:border-t-blue-400" />
                  </div>
                </div>
                <div className="flex-1">
                  <p className="text-xs leading-relaxed text-blue-800 dark:text-blue-200">
                    {t('restartingExecution' as any) ||
                      'Restarting execution, please wait...'}
                  </p>
                </div>
              </div>
            </div>
          ) : null}
          <>
            {runningExecutions.map((execution) => renderExecutionItem(execution))}
          </>
        </>
      </CollapsibleSection>

      <CollapsibleSection
        title={t('timelinePendingConfirmation' as any)}
        sectionKey="pending"
        count={pendingConfirmationExecutions.length}
        collapsedSections={collapsedSections}
        onToggle={toggleSection}
        headerClassName="bg-surface-accent text-amber-700 hover:bg-surface-secondary dark:bg-gray-900 dark:text-amber-400 dark:hover:bg-gray-800"
        emptyState={
          <div className="px-1 py-2 text-xs text-tertiary dark:text-gray-300">
            {t('noPendingConfirmations' as any)}
          </div>
        }
      >
        <>{pendingConfirmationExecutions.map((execution) => renderExecutionItem(execution))}</>
      </CollapsibleSection>

      <div className="space-y-1">
        <div className="sticky top-0 z-10 bg-surface-accent px-1 py-1 text-xs font-semibold text-secondary dark:bg-gray-900 dark:text-gray-300">
          <span>{t('tabOutcomes' as any) || 'Outcomes'}</span>
        </div>
        <div className="px-1">
          <OutcomesPanel
            workspaceId={workspaceId}
            apiUrl={apiUrl}
            onArtifactClick={onArtifactClick}
          />
        </div>
      </div>
    </div>
  );
}
