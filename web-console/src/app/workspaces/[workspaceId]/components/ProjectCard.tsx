'use client';

import React, { useState, useEffect, useRef } from 'react';
import { useRouter, useParams } from 'next/navigation';
import { Project } from '@/types/project';
import { parseServerTimestamp } from '@/lib/time';

interface ProjectCardData {
  projectId: string;
  projectName: string;
  storyThreadId?: string;
  mindLensId?: string;
  mindLensName?: string;
  status: 'active' | 'paused' | 'completed' | 'archived';
  lastActivity: string;
  stats: {
    totalPlaybooks: number;
    runningExecutions: number;
    pendingConfirmations: number;
    completedExecutions: number;
    artifactCount: number;
  };
  progress: {
    current: number;
    label: string;
  };
  recentEvents: Array<{
    id: string;
    type: 'playbook_started' | 'step_completed' | 'artifact_created' | 'confirmation_needed';
    playbookCode: string;
    playbookName: string;
    executionId: string;
    stepIndex?: number;
    stepName?: string;
    timestamp: string;
    metadata?: Record<string, any>;
    projectId?: string;
    projectName?: string;
  }>;
  playbooks?: Array<{
    code: string;
    name: string;
    description: string;
  }>;
  meeting?: {
    enabled: boolean;
    active: boolean;
    session_id?: string | null;
    status?: string | null;
    round_count?: number;
    max_rounds?: number;
    action_item_count?: number;
    last_activity?: string | null;
    minutes_preview?: string;
  };
}

interface ProjectCardProps {
  project: Project;
  workspaceId?: string;
  isExpanded?: boolean;
  isFocused?: boolean;
  defaultExpanded?: boolean;
  onToggleExpand?: () => void;
  onFocus?: () => void;
  onOpenExecution?: (executionId: string) => void;
  apiUrl?: string;
}

function formatRelativeTime(timestamp: string): string {
  const date = parseServerTimestamp(timestamp);
  if (!date) return timestamp;
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMins < 1) return '剛剛';
  if (diffMins < 60) return `${diffMins} 分鐘前`;
  if (diffHours < 24) return `${diffHours} 小時前`;
  if (diffDays < 7) return `${diffDays} 天前`;
  return date.toLocaleDateString('zh-TW');
}

function EventItem({
  event,
  onClick
}: {
  event: ProjectCardData['recentEvents'][0];
  onClick: () => void;
}) {
  const icons: Record<string, string> = {
    playbook_started: '▶️',
    step_completed: '✅',
    artifact_created: '📄',
    confirmation_needed: '⏸️'
  };

  return (
    <div
      className="event-item flex items-center gap-2 p-2 hover:bg-surface-secondary dark:hover:bg-gray-800 rounded cursor-pointer transition-colors"
      onClick={onClick}
    >
      <span className="event-icon text-xs flex-shrink-0">{icons[event.type] || '•'}</span>
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

export default function ProjectCard({
  project,
  workspaceId,
  isExpanded: controlledExpanded,
  isFocused = false,
  defaultExpanded = true,  // Default to expanded for better visibility of task details
  onToggleExpand,
  onFocus,
  onOpenExecution,
  apiUrl = ''
}: ProjectCardProps) {
  const router = useRouter();
  const params = useParams();
  const effectiveWorkspaceId = workspaceId || (params?.workspaceId as string);


  const [internalExpanded, setInternalExpanded] = useState(defaultExpanded);
  const [cardData, setCardData] = useState<ProjectCardData | null>(null);
  const [loading, setLoading] = useState(false);
  const [meetingUpdating, setMeetingUpdating] = useState(false);
  const [isHighlighted, setIsHighlighted] = useState(false);
  const loadingRef = useRef(false);
  const highlightTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  const isExpanded = controlledExpanded !== undefined ? controlledExpanded : internalExpanded;
  const handleToggleExpand = onToggleExpand || (() => {
    console.log('[ProjectCard] Toggle expand:', { before: internalExpanded, projectId: project.id });
    setInternalExpanded(!internalExpanded);
  });

  // Debug: Log expansion state
  useEffect(() => {
    console.log('[ProjectCard] Expansion state changed:', {
      projectId: project.id,
      defaultExpanded,
      internalExpanded,
      controlledExpanded,
      isExpanded
    });
  }, [defaultExpanded, internalExpanded, controlledExpanded, isExpanded, project.id]);

  // Listen for highlight-project-card event
  useEffect(() => {
    const handleHighlight = (e: CustomEvent) => {
      const { projectId } = e.detail || {};
      if (projectId === project.id) {
        // Clear existing timeout if any
        if (highlightTimeoutRef.current) {
          clearTimeout(highlightTimeoutRef.current);
        }

        // Set highlighted state
        setIsHighlighted(true);

        // Auto-expand card if collapsed
        if (!isExpanded) {
          handleToggleExpand();
        }

        // Scroll card into view if needed
        const cardElement = document.querySelector(`[data-project-card-id="${project.id}"]`);
        if (cardElement) {
          cardElement.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }

        // Clear highlight after 2.5 seconds
        highlightTimeoutRef.current = setTimeout(() => {
          setIsHighlighted(false);
        }, 2500);
      }
    };

    window.addEventListener('highlight-project-card', handleHighlight as EventListener);
    return () => {
      window.removeEventListener('highlight-project-card', handleHighlight as EventListener);
      if (highlightTimeoutRef.current) {
        clearTimeout(highlightTimeoutRef.current);
      }
    };
  }, [project.id, isExpanded, handleToggleExpand]);

  useEffect(() => {
    // Load data when component mounts or when project changes, not just when expanded
    // This ensures statistics are visible even when card is collapsed
    if (cardData || loadingRef.current || !apiUrl || !effectiveWorkspaceId) {
      return;
    }

    loadingRef.current = true;
    setLoading(true);
    const url = `${apiUrl}/api/v1/workspaces/${effectiveWorkspaceId}/projects/${project.id}/card`;
    console.log('[ProjectCard] Loading card data from:', url);

    let isMounted = true;
    const controller = new AbortController();
    const timeoutId = setTimeout(() => {
      controller.abort();
      console.error('[ProjectCard] Request timeout after 10 seconds');
    }, 10000);

    fetch(url, {
      method: 'GET',
      headers: {
        'Accept': 'application/json',
      },
      signal: controller.signal,
      credentials: 'include'
    })
      .then(res => {
        clearTimeout(timeoutId);
        if (!res.ok) {
          return res.text().then(text => {
            throw new Error(`HTTP ${res.status}: ${res.statusText} - ${text}`);
          });
        }
        return res.json();
      })
      .then(data => {
        if (!isMounted) return;
        console.log('[ProjectCard] Received data:', data);
        setCardData(data);
        loadingRef.current = false;
        setLoading(false);
      })
      .catch(err => {
        clearTimeout(timeoutId);
        if (!isMounted) return;
        loadingRef.current = false;
        if (err.name === 'AbortError') {
          console.error('[ProjectCard] Request aborted');
        } else {
          console.error('[ProjectCard] Failed to load:', err);
        }
        setLoading(false);
      });

    return () => {
      isMounted = false;
      clearTimeout(timeoutId);
      controller.abort();
      loadingRef.current = false;
    };
  }, [cardData, apiUrl, project.id, effectiveWorkspaceId]);

  const meetingEnabled = Boolean(
    cardData?.meeting?.enabled ?? project.metadata?.meeting_enabled
  );
  const meetingActive = Boolean(cardData?.meeting?.active);

  const handleToggleMeeting = async (enabled: boolean) => {
    if (!apiUrl || !effectiveWorkspaceId || meetingUpdating) return;
    setMeetingUpdating(true);
    try {
      const response = await fetch(
        `${apiUrl}/api/v1/workspaces/${effectiveWorkspaceId}/projects/${project.id}`,
        {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ meeting_enabled: enabled }),
        }
      );
      if (!response.ok) {
        throw new Error(`Failed to update meeting flag: ${response.status}`);
      }
      setCardData((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          meeting: {
            enabled,
            active: enabled ? true : false,
            session_id: prev.meeting?.session_id ?? null,
            status: enabled ? 'active' : null,
            round_count: prev.meeting?.round_count ?? 0,
            max_rounds: prev.meeting?.max_rounds ?? 5,
            action_item_count: prev.meeting?.action_item_count ?? 0,
            last_activity: prev.meeting?.last_activity ?? null,
            minutes_preview: prev.meeting?.minutes_preview ?? '',
          },
        };
      });
      // Refetch card data after toggle to sync with backend state
      if (enabled) {
        setTimeout(async () => {
          try {
            const res = await fetch(
              `${apiUrl}/api/v1/workspaces/${effectiveWorkspaceId}/projects/${project.id}/card`,
              { headers: { 'Accept': 'application/json' }, credentials: 'include' }
            );
            if (res.ok) {
              const data = await res.json();
              setCardData(data);
            }
          } catch { /* ignore refetch errors */ }
        }, 1500);

        // Auto kick-off meeting pipeline (no separate chat message needed)
        try {
          // Find or create meeting session
          let sessionId = cardData?.meeting?.session_id || '';
          if (!sessionId) {
            const activeResp = await fetch(
              `${apiUrl}/api/v1/workspaces/${effectiveWorkspaceId}/meeting-sessions/active?project_id=${project.id}`,
              { method: 'GET' }
            );
            if (activeResp.ok) {
              const active = await activeResp.json();
              sessionId = active.id;
            } else if (activeResp.status === 404) {
              const startResp = await fetch(
                `${apiUrl}/api/v1/workspaces/${effectiveWorkspaceId}/meeting-sessions/start`,
                {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({
                    project_id: project.id,
                    thread_id: cardData?.storyThreadId || null,
                  }),
                }
              );
              if (startResp.ok) {
                const started = await startResp.json();
                sessionId = started.id;
              }
            }
          }

          // Trigger the meeting pipeline with project context
          const meetingMessage = `[Meeting Started] Start project meeting for "${project.title}" (${project.type})`;
          console.log('[ProjectCard] Auto-kicking off meeting pipeline for project:', project.id);
          await fetch(`${apiUrl}/api/v1/workspaces/${effectiveWorkspaceId}/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              message: meetingMessage,
              project_id: project.id,
              thread_id: sessionId || undefined,
            }),
          });
          window.dispatchEvent(new Event('workspace-chat-updated'));
        } catch (kickoffErr) {
          console.error('[ProjectCard] Meeting auto-kickoff failed:', kickoffErr);
        }
      }
    } catch (err) {
      console.error('[ProjectCard] Failed to toggle meeting:', err);
      throw err;  // Re-throw so callers (handleOpenMeeting) can detect failure
    } finally {
      setMeetingUpdating(false);
    }
  };

  const handleOpenMeeting = () => {
    console.log('[ProjectCard] Meeting button clicked', { effectiveWorkspaceId, projectId: project.id });
    if (!effectiveWorkspaceId) {
      console.warn('[ProjectCard] No effectiveWorkspaceId, cannot open meeting');
      return;
    }
    router.push(`/workspaces/${effectiveWorkspaceId}/meetings?project_id=${project.id}`);
  };

  const handleOpenExecution = (executionId: string) => {
    if (onOpenExecution) {
      onOpenExecution(executionId);
    }
  };

  const handleCardClick = (e: React.MouseEvent) => {
    const target = e.target as HTMLElement;
    if (target.closest('.card-header') || target.closest('.progress-bar-container') || target.closest('.card-content')) {
      return;
    }

    if (cardData && cardData.stats.runningExecutions > 0 && onOpenExecution) {
      if (cardData.recentEvents && cardData.recentEvents.length > 0) {
        const firstEvent = cardData.recentEvents[0];
        if (firstEvent.executionId) {
          onOpenExecution(firstEvent.executionId);
          return;
        }
      }
    }
    if (onFocus) {
      onFocus();
    }
  };

  const progressPercentage = cardData
    ? Math.max(cardData.progress.current, 1)
    : 1;

  const totalPlaybooks = cardData?.stats.totalPlaybooks || 0;
  const nextTaskProgress = totalPlaybooks > 0
    ? Math.min(progressPercentage + (100 / totalPlaybooks), 100)
    : progressPercentage;
  const nextNextTaskProgress = totalPlaybooks > 0
    ? Math.min(progressPercentage + (200 / totalPlaybooks), 100)
    : progressPercentage;
  const scanRangeStart = progressPercentage;
  const scanRangeEnd = nextNextTaskProgress;
  const scanRangeWidth = scanRangeEnd - scanRangeStart;

  return (
    <div
      data-project-card-id={project.id}
      className={`project-card bg-surface-secondary dark:bg-gray-800 border rounded-lg overflow-hidden transition-all cursor-pointer ${isHighlighted
        ? 'ring-2 ring-accent dark:ring-blue-400 border-accent dark:border-blue-500 shadow-lg'
        : 'border-default dark:border-gray-700'
        } ${isFocused ? 'ring-2 ring-accent dark:ring-blue-400' : ''
        }`}
      onClick={handleCardClick}
    >
      <div
        className={`cursor-pointer hover:bg-surface-secondary dark:hover:bg-gray-700 transition-colors ${meetingActive ? 'meeting-laser-border' : ''}`}
        onClick={(e) => {
          e.stopPropagation();
          handleToggleExpand();
        }}
      >
        <div className="flex items-center justify-between p-3 pb-1.5">
          <div className="left flex items-center gap-2 flex-1 min-w-0">
            <span className="chevron text-xs text-tertiary dark:text-gray-500 flex-shrink-0">
              {isExpanded ? '▼' : '▶'}
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
                title={`${cardData.stats.runningExecutions} 個執行中`}
              >
                🔄 {cardData.stats.runningExecutions}
              </span>
            )}
            {cardData && (
              <span
                className={`badge artifact text-[10px] px-1.5 py-0.5 rounded ${cardData.stats.artifactCount > 0
                  ? 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300'
                  : 'bg-surface-secondary dark:bg-gray-700 text-tertiary dark:text-gray-500'
                  }`}
                title={`${cardData.stats.artifactCount} 個成果`}
              >
                📦 {cardData.stats.artifactCount}
              </span>
            )}
            {cardData && (
              <span
                className={`badge completed text-[10px] px-1.5 py-0.5 rounded ${cardData.stats.completedExecutions > 0
                  ? 'bg-surface-secondary dark:bg-gray-700 text-primary dark:text-gray-300'
                  : 'bg-surface-secondary dark:bg-gray-700 text-tertiary dark:text-gray-500'
                  }`}
                title={`${cardData.stats.completedExecutions} 個已完成`}
              >
                ✓ {cardData.stats.completedExecutions}
              </span>
            )}
            {cardData && cardData.stats.pendingConfirmations > 0 && (
              <span
                className="badge pending text-[10px] px-1.5 py-0.5 bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-300 rounded"
                title={`${cardData.stats.pendingConfirmations} 個待確認`}
              >
                ⏸️ {cardData.stats.pendingConfirmations}
              </span>
            )}
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                handleToggleMeeting(!meetingEnabled).catch(() => { /* error already logged */ });
              }}
              disabled={meetingUpdating}
              className={`text-[10px] px-1.5 py-0.5 rounded border transition-colors ${meetingEnabled
                ? 'bg-sky-100 dark:bg-sky-900/30 text-sky-700 dark:text-sky-300 border-sky-200 dark:border-sky-700'
                : 'bg-surface-secondary dark:bg-gray-700 text-tertiary dark:text-gray-400 border-default dark:border-gray-600'
                } ${meetingUpdating ? 'opacity-60 cursor-not-allowed' : 'hover:opacity-85'}`}
              title={meetingEnabled ? 'Disable persistent meeting' : 'Enable persistent meeting'}
            >
              🧭 {meetingEnabled ? (meetingActive ? 'ON*' : 'ON') : 'OFF'}
            </button>
          </div>
        </div>
        <div className="block px-3 pb-2 pt-0.5 text-[10px] text-secondary dark:text-gray-400">
          <div className="flex items-center gap-3">
            {(project.human_owner_user_id || project.initiator_user_id) && (
              <span>負責人: {project.human_owner_user_id || project.initiator_user_id}</span>
            )}
            {project.created_at && (
              <span>
                {parseServerTimestamp(project.created_at)?.toLocaleDateString('zh-TW', {
                  year: 'numeric',
                  month: 'short',
                  day: 'numeric'
                }) ?? ''}
              </span>
            )}
          </div>
        </div>
      </div>

      <div className="progress-bar-container relative w-full h-1 bg-surface-secondary dark:bg-gray-700 overflow-hidden">
        <div
          className="progress-fill h-full bg-accent dark:bg-blue-400 rounded-full transition-all relative overflow-hidden"
          style={{ width: `${progressPercentage}%` }}
        >
          <div className="laser-effect absolute inset-0 bg-gradient-to-r from-transparent via-white/50 via-white/80 via-white/50 to-transparent animate-shimmer" style={{ width: '40%' }} />
        </div>
        {cardData && scanRangeWidth > 0 && scanRangeEnd <= 100 && (
          <div
            className="progress-scan absolute top-0 h-full bg-gradient-to-r from-transparent via-blue-300/15 to-transparent animate-shimmer"
            style={{
              left: `${scanRangeStart}%`,
              width: `${scanRangeWidth}%`
            }}
          />
        )}
      </div>

      {isExpanded && (
        <div className="card-content p-3">
          {(() => {
            // Debug: Log expansion and data state
            console.log('[ProjectCard] Expanded content rendering:', {
              projectId: project.id,
              isExpanded,
              loading,
              hasCardData: !!cardData,
              cardDataKeys: cardData ? Object.keys(cardData) : null,
              defaultExpanded,
              internalExpanded,
              controlledExpanded
            });
            return null;
          })()}
          {loading ? (
            <div className="text-xs text-secondary dark:text-gray-400 text-center py-4">
              載入中...
            </div>
          ) : cardData ? (
            <div className="events-column w-full space-y-4">
              {/* Persistent Meeting Summary */}
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
                      Round {cardData.meeting?.round_count || 0}/{cardData.meeting?.max_rounds || 5} · Action Items {cardData.meeting?.action_item_count || 0}
                    </div>
                    <div className="text-[10px] text-secondary dark:text-gray-400 line-clamp-2">
                      {cardData.meeting?.minutes_preview?.trim() || 'No meeting summary yet'}
                    </div>
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        handleOpenMeeting();
                      }}
                      className="mt-1 text-[10px] px-2 py-1 rounded bg-sky-100 dark:bg-sky-900/30 text-sky-800 dark:text-sky-300 hover:opacity-85"
                    >
                      Enter Meeting
                    </button>
                  </div>
                ) : (
                  <div className="text-[10px] text-tertiary dark:text-gray-500">
                    Enable to maintain meeting context and accumulate decisions and action items.
                  </div>
                )}
              </div>

              {/* Playbook List */}
              {cardData.playbooks && cardData.playbooks.length > 0 && (
                <div className="mb-4">
                  <div className="events-header text-[10px] font-semibold text-primary dark:text-gray-300 mb-2">
                    Playbook 任務 ({cardData.playbooks.length})
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

              {/* Recent Events */}
              <div>
                <div className="events-header text-[10px] font-semibold text-primary dark:text-gray-300 mb-2">
                  即時動態
                </div>
                <div className="events-list space-y-1 max-h-48 overflow-y-auto">
                  {(() => {
                    // Filter to only show events belonging to this project
                    const filteredEvents = cardData.recentEvents.filter(event => {
                      if (event.projectId) {
                        return event.projectId === project.id;
                      }
                      // No projectId info: assume current project (backward compat)
                      return true;
                    });

                    return filteredEvents.length > 0 ? (
                      filteredEvents.slice(0, 1).map(event => (
                        <EventItem
                          key={event.id}
                          event={event}
                          onClick={() => handleOpenExecution(event.executionId)}
                        />
                      ))
                    ) : (
                      <div className="text-[10px] text-tertiary dark:text-gray-500 text-center py-4">
                        尚無動態
                      </div>
                    );
                  })()}
                </div>
              </div>
            </div>
          ) : (
            <div className="text-xs text-secondary dark:text-gray-400 text-center py-4">
              無法載入數據
            </div>
          )}
        </div>
      )}

      <div className="px-3 pb-2 pt-1.5 border-t border-default dark:border-gray-700 grid grid-cols-2 gap-2">
        <button
          onClick={(e) => {
            e.stopPropagation();
            console.log('[ProjectCard] View button clicked', { project, effectiveWorkspaceId });

            if (effectiveWorkspaceId) {
              console.log('[ProjectCard] Navigating to execution timeline');
              router.push(`/workspaces/${effectiveWorkspaceId}/executions/timeline?project_id=${project.id}`);
            } else if (onFocus) {
              // Fallback
              onFocus();
            }
          }}
          className="w-full text-xs text-accent dark:text-blue-400 hover:opacity-80 dark:hover:text-blue-300 font-medium py-1.5 px-2 rounded hover:bg-accent-10 dark:hover:bg-blue-900/20 transition-colors cursor-pointer"
        >
          查看 →
        </button>
        <button
          onClick={(e) => {
            e.stopPropagation();
            handleOpenMeeting();
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
