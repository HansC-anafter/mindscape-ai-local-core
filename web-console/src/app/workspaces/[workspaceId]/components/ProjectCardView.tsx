import type { MouseEvent } from 'react';
import type { Project } from '@/types/project';
import { WorkflowEvidenceSummary } from '@/components/workspace/meeting/WorkflowEvidenceSummary';
import type {
  ProjectCardData,
  ProjectCardProgressValues,
  WorkflowEvidenceValues,
} from './projectCardTypes';
import { formatProjectCreatedDate, formatRelativeTime } from './projectCardState';

interface ProjectCardViewProps {
  project: Project;
  effectiveWorkspaceId: string;
  cardData: ProjectCardData | null;
  loading: boolean;
  isExpanded: boolean;
  isFocused: boolean;
  isHighlighted: boolean;
  meetingEnabled: boolean;
  meetingActive: boolean;
  meetingUpdating: boolean;
  workflowEvidence: WorkflowEvidenceValues;
  progress: ProjectCardProgressValues;
  filteredEvents: ProjectCardData['recentEvents'];
  meetingHref: string;
  onCardClick: (event: MouseEvent<HTMLDivElement>) => void;
  onToggleExpand: () => void;
  onToggleMeeting: (enabled: boolean) => Promise<void>;
  onOpenMeeting: () => void;
  onOpenMeetingScenePatch: () => void;
  onOpenExecution: (executionId: string) => void;
  onViewProject: () => void;
}

function EventItem({
  event,
  onClick
}: {
  event: ProjectCardData['recentEvents'][0];
  onClick: () => void;
}) {
  const icons: Record<string, string> = {
    playbook_started: 'START',
    step_completed: 'DONE',
    artifact_created: 'ART',
    confirmation_needed: 'WAIT'
  };

  return (
    <div
      className="event-item flex items-center gap-2 p-2 hover:bg-surface-secondary dark:hover:bg-gray-800 rounded cursor-pointer transition-colors"
      onClick={onClick}
    >
      <span className="event-icon text-xs flex-shrink-0">{icons[event.type] || '-'}</span>
      <div className="event-content flex-1 min-w-0">
        <div className="playbook-name text-[10px] font-medium text-primary dark:text-gray-100 truncate">
          {event.playbookName}
        </div>
        {event.stepName && (
          <div className="step-info text-[9px] text-secondary dark:text-gray-400">
            Step {event.stepIndex}: {event.stepName}
          </div>
        )}
      </div>
      <span className="event-time text-[9px] text-tertiary dark:text-gray-500 flex-shrink-0">
        {formatRelativeTime(event.timestamp)}
      </span>
    </div>
  );
}

export default function ProjectCardView({
  project,
  effectiveWorkspaceId,
  cardData,
  loading,
  isExpanded,
  isFocused,
  isHighlighted,
  meetingEnabled,
  meetingActive,
  meetingUpdating,
  workflowEvidence,
  progress,
  filteredEvents,
  meetingHref,
  onCardClick,
  onToggleExpand,
  onToggleMeeting,
  onOpenMeeting,
  onOpenMeetingScenePatch,
  onOpenExecution,
  onViewProject,
}: ProjectCardViewProps) {
  return (
    <div
      data-project-card-id={project.id}
      className={`project-card bg-surface-secondary dark:bg-gray-800 border rounded-lg overflow-hidden transition-all cursor-pointer ${isHighlighted
        ? 'ring-2 ring-accent dark:ring-blue-400 border-accent dark:border-blue-500 shadow-lg'
        : 'border-default dark:border-gray-700'
        } ${isFocused ? 'ring-2 ring-accent dark:ring-blue-400' : ''
        }`}
      onClick={onCardClick}
    >
      <div
        className={`cursor-pointer hover:bg-surface-secondary dark:hover:bg-gray-700 transition-colors ${meetingActive ? 'meeting-laser-border' : ''}`}
        onClick={(event) => {
          event.stopPropagation();
          onToggleExpand();
        }}
      >
        <div className="flex items-center justify-between p-3 pb-1.5">
          <div className="left flex items-center gap-2 flex-1 min-w-0">
            <span className="chevron text-xs text-tertiary dark:text-gray-500 flex-shrink-0">
              {isExpanded ? '[-]' : '[+]'}
            </span>
            <span className="project-name text-sm font-medium text-primary dark:text-gray-100 truncate">
              {project.title}
            </span>
            {cardData?.mindLensName && (
              <span className="mind-lens-tag text-[10px] px-1.5 py-0.5 bg-accent-10 dark:bg-blue-900/30 text-accent dark:text-blue-300 rounded">
                @{cardData.mindLensName}
              </span>
            )}
          </div>
          <div className="right flex items-center gap-2 flex-shrink-0">
            {cardData && (
              <span
                className={`badge running text-[10px] px-1.5 py-0.5 rounded ${cardData.stats.runningExecutions > 0
                  ? 'bg-accent-10 dark:bg-blue-900/30 text-accent dark:text-blue-300'
                  : 'bg-surface-secondary dark:bg-gray-700 text-tertiary dark:text-gray-500'
                  }`}
                title={`${cardData.stats.runningExecutions} running executions`}
              >
                RUN {cardData.stats.runningExecutions}
              </span>
            )}
            {cardData && (
              <span
                className={`badge artifact text-[10px] px-1.5 py-0.5 rounded ${cardData.stats.artifactCount > 0
                  ? 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300'
                  : 'bg-surface-secondary dark:bg-gray-700 text-tertiary dark:text-gray-500'
                  }`}
                title={`${cardData.stats.artifactCount} artifacts`}
              >
                ART {cardData.stats.artifactCount}
              </span>
            )}
            {cardData && (
              <span
                className={`badge completed text-[10px] px-1.5 py-0.5 rounded ${cardData.stats.completedExecutions > 0
                  ? 'bg-surface-secondary dark:bg-gray-700 text-primary dark:text-gray-300'
                  : 'bg-surface-secondary dark:bg-gray-700 text-tertiary dark:text-gray-500'
                  }`}
                title={`${cardData.stats.completedExecutions} completed executions`}
              >
                DONE {cardData.stats.completedExecutions}
              </span>
            )}
            {cardData && cardData.stats.pendingConfirmations > 0 && (
              <span
                className="badge pending text-[10px] px-1.5 py-0.5 bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-300 rounded"
                title={`${cardData.stats.pendingConfirmations} pending confirmations`}
              >
                WAIT {cardData.stats.pendingConfirmations}
              </span>
            )}
            <button
              type="button"
              onClick={(event) => {
                event.stopPropagation();
                onToggleMeeting(!meetingEnabled).catch(() => undefined);
              }}
              disabled={meetingUpdating}
              className={`text-[10px] px-1.5 py-0.5 rounded border transition-colors ${meetingEnabled
                ? 'bg-sky-100 dark:bg-sky-900/30 text-sky-700 dark:text-sky-300 border-sky-200 dark:border-sky-700'
                : 'bg-surface-secondary dark:bg-gray-700 text-tertiary dark:text-gray-400 border-default dark:border-gray-600'
                } ${meetingUpdating ? 'opacity-60 cursor-not-allowed' : 'hover:opacity-85'}`}
              title={meetingEnabled ? 'Disable persistent meeting' : 'Enable persistent meeting'}
            >
              Meeting {meetingEnabled ? (meetingActive ? 'ON*' : 'ON') : 'OFF'}
            </button>
          </div>
        </div>
        <div className="block px-3 pb-2 pt-0.5 text-[10px] text-secondary dark:text-gray-400">
          <div className="flex items-center gap-3">
            {(project.human_owner_user_id || project.initiator_user_id) && (
              <span>Owner: {project.human_owner_user_id || project.initiator_user_id}</span>
            )}
            {project.created_at && (
              <span>{formatProjectCreatedDate(project.created_at)}</span>
            )}
          </div>
        </div>
      </div>

      <div className="progress-bar-container relative w-full h-1 bg-surface-secondary dark:bg-gray-700 overflow-hidden">
        <div
          className="progress-fill h-full bg-accent dark:bg-blue-400 rounded-full transition-all relative overflow-hidden"
          style={{ width: `${progress.progressPercentage}%` }}
        >
          <div className="laser-effect absolute inset-0 bg-gradient-to-r from-transparent via-white/50 via-white/80 via-white/50 to-transparent animate-shimmer" style={{ width: '40%' }} />
        </div>
        {cardData && progress.scanRangeWidth > 0 && progress.scanRangeEnd <= 100 && (
          <div
            className="progress-scan absolute top-0 h-full bg-gradient-to-r from-transparent via-blue-300/15 to-transparent animate-shimmer"
            style={{
              left: `${progress.scanRangeStart}%`,
              width: `${progress.scanRangeWidth}%`
            }}
          />
        )}
      </div>

      {isExpanded && (
        <div className="card-content p-3">
          {loading ? (
            <div className="text-xs text-secondary dark:text-gray-400 text-center py-4">
              Loading...
            </div>
          ) : cardData ? (
            <div className="events-column w-full space-y-4">
              <div className="p-2 rounded border border-sky-200/60 dark:border-sky-800/60 bg-sky-50/60 dark:bg-sky-900/10">
                <div className="flex items-center justify-between gap-2 mb-1">
                  <div className="text-[10px] font-semibold text-sky-800 dark:text-sky-300">
                    Persistent Meeting
                  </div>
                  <div className="text-[10px] text-sky-700 dark:text-sky-400">
                    {meetingEnabled ? (meetingActive ? 'Active' : 'Idle') : 'Disabled'}
                  </div>
                </div>
                {meetingEnabled ? (
                  <div className="space-y-1">
                    <div className="text-[10px] text-secondary dark:text-gray-400">
                      Round {cardData.meeting?.round_count || 0}/{cardData.meeting?.max_rounds || 5} - Action Items {cardData.meeting?.action_item_count || 0}
                    </div>
                    {workflowEvidence.profile && (
                      <WorkflowEvidenceSummary
                        label="Workflow Evidence"
                        profile={workflowEvidence.profile}
                        scope={workflowEvidence.scope}
                        selectedLineCount={workflowEvidence.selectedLineCount}
                        totalLineBudget={workflowEvidence.totalLineBudget}
                        totalCandidateCount={workflowEvidence.totalCandidateCount}
                        totalDroppedCount={workflowEvidence.totalDroppedCount}
                        renderedSectionCount={workflowEvidence.renderedSectionCount}
                        budgetUtilizationRatio={workflowEvidence.budgetUtilizationRatio}
                        href={meetingHref}
                        compact
                        className="mt-1"
                      />
                    )}
                    <div className="text-[10px] text-secondary dark:text-gray-400 line-clamp-2">
                      {cardData.meeting?.minutes_preview?.trim() || 'No meeting summary yet'}
                    </div>
                    <button
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation();
                        onOpenMeeting();
                      }}
                      className="mt-1 text-[10px] px-2 py-1 rounded bg-sky-100 dark:bg-sky-900/30 text-sky-800 dark:text-sky-300 hover:opacity-85"
                    >
                      Enter Meeting
                    </button>
                    <button
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation();
                        onOpenMeetingScenePatch();
                      }}
                      className="mt-1 ml-2 text-[10px] px-2 py-1 rounded border border-sky-200 dark:border-sky-700 text-sky-700 dark:text-sky-300 hover:bg-sky-50 dark:hover:bg-sky-900/20"
                    >
                      Scene Patch
                    </button>
                  </div>
                ) : (
                  <div className="text-[10px] text-tertiary dark:text-gray-500">
                    Enable to maintain meeting context and accumulate decisions and action items.
                  </div>
                )}
              </div>

              {cardData.playbooks && cardData.playbooks.length > 0 && (
                <div className="mb-4">
                  <div className="events-header text-[10px] font-semibold text-primary dark:text-gray-300 mb-2">
                    Playbook Tasks ({cardData.playbooks.length})
                  </div>
                  <div className="space-y-1">
                    {cardData.playbooks.map((playbook, index) => (
                      <div
                        key={playbook.code}
                        className="flex items-center gap-2 p-2 hover:bg-surface-secondary dark:hover:bg-gray-800 rounded"
                      >
                        <span className="text-xs text-secondary dark:text-gray-400">
                          {index + 1}.
                        </span>
                        <div className="flex-1 min-w-0">
                          <div className="text-xs font-medium text-primary dark:text-gray-100">
                            {playbook.name}
                          </div>
                          {playbook.description && (
                            <div className="text-[10px] text-secondary dark:text-gray-400">
                              {playbook.description}
                            </div>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div>
                <div className="events-header text-[10px] font-semibold text-primary dark:text-gray-300 mb-2">
                  Live Activity
                </div>
                <div className="events-list space-y-1 max-h-48 overflow-y-auto">
                  {filteredEvents.length > 0 ? (
                    filteredEvents.slice(0, 1).map((event) => (
                      <EventItem
                        key={event.id}
                        event={event}
                        onClick={() => onOpenExecution(event.executionId)}
                      />
                    ))
                  ) : (
                    <div className="text-[10px] text-tertiary dark:text-gray-500 text-center py-4">
                      No activity yet
                    </div>
                  )}
                </div>
              </div>
            </div>
          ) : (
            <div className="text-xs text-secondary dark:text-gray-400 text-center py-4">
              Unable to load data
            </div>
          )}
        </div>
      )}

      <div className="px-3 pb-2 pt-1.5 border-t border-default dark:border-gray-700 grid grid-cols-2 gap-2">
        <button
          onClick={(event) => {
            event.stopPropagation();
            onViewProject();
          }}
          className="w-full text-xs text-accent dark:text-blue-400 hover:opacity-80 dark:hover:text-blue-300 font-medium py-1.5 px-2 rounded hover:bg-accent-10 dark:hover:bg-blue-900/20 transition-colors cursor-pointer"
        >
          View
        </button>
        <button
          onClick={(event) => {
            event.stopPropagation();
            onOpenMeeting();
          }}
          className={`w-full text-xs font-medium py-1.5 px-2 rounded transition-colors ${meetingEnabled
            ? 'text-sky-700 dark:text-sky-300 hover:bg-sky-50 dark:hover:bg-sky-900/20'
            : 'text-tertiary dark:text-gray-500 hover:bg-surface-secondary dark:hover:bg-gray-800'
            }`}
        >
          Meeting
        </button>
      </div>
    </div>
  );
}
