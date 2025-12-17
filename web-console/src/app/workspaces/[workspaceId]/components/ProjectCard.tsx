'use client';

import React, { useState, useEffect, useRef } from 'react';
import { useRouter } from 'next/navigation';
import { Project } from '@/types/project';

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
    projectId?: string;  // 添加 project 归属信息
    projectName?: string;
  }>;
  playbooks?: Array<{
    code: string;
    name: string;
    description: string;
  }>;
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
  try {
    const date = new Date(timestamp);
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
  } catch {
    return timestamp;
  }
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
      className="event-item flex items-center gap-2 p-2 hover:bg-gray-50 dark:hover:bg-gray-800 rounded cursor-pointer transition-colors"
      onClick={onClick}
    >
      <span className="event-icon text-xs flex-shrink-0">{icons[event.type] || '•'}</span>
      <div className="event-content flex-1 min-w-0">
        <div className="playbook-name text-[10px] font-medium text-gray-900 dark:text-gray-100 truncate">
          {event.playbookName}
        </div>
        {event.stepName && (
          <div className="step-info text-[9px] text-gray-500 dark:text-gray-400">
            Step {event.stepIndex}: {event.stepName}
          </div>
        )}
      </div>
      <span className="event-time text-[9px] text-gray-400 dark:text-gray-500 flex-shrink-0">
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
  defaultExpanded = false,  // Add defaultExpanded prop
  onToggleExpand,
  onFocus,
  onOpenExecution,
  apiUrl = ''
}: ProjectCardProps) {
  const router = useRouter();
  const [internalExpanded, setInternalExpanded] = useState(defaultExpanded);
  const [cardData, setCardData] = useState<ProjectCardData | null>(null);
  const [loading, setLoading] = useState(false);
  const loadingRef = useRef(false);

  const isExpanded = controlledExpanded !== undefined ? controlledExpanded : internalExpanded;
  const handleToggleExpand = onToggleExpand || (() => setInternalExpanded(!internalExpanded));

  useEffect(() => {
    // Load data when component mounts or when project changes, not just when expanded
    // This ensures statistics are visible even when card is collapsed
    if (cardData || loadingRef.current || !apiUrl || !workspaceId) {
      return;
    }

    loadingRef.current = true;
    setLoading(true);
    const url = `${apiUrl}/api/v1/workspaces/${workspaceId}/projects/${project.id}/card`;
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
  }, [cardData, apiUrl, project.id, workspaceId]);

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
      className={`project-card bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden transition-all cursor-pointer ${
        isFocused ? 'ring-2 ring-blue-500 dark:ring-blue-400' : ''
      }`}
      onClick={handleCardClick}
    >
      <div
        className="cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
        onClick={(e) => {
          e.stopPropagation();
          handleToggleExpand();
        }}
      >
        <div className="flex items-center justify-between p-3 pb-1.5">
          <div className="left flex items-center gap-2 flex-1 min-w-0">
            <span className="chevron text-xs text-gray-400 dark:text-gray-500 flex-shrink-0">
              {isExpanded ? '▼' : '▶'}
            </span>
            <span className="project-name text-sm font-medium text-gray-900 dark:text-gray-100 truncate">
              {project.title}
            </span>
            {cardData?.mindLensName && (
              <span className="mind-lens-tag text-[10px] px-1.5 py-0.5 bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 rounded">
                @{cardData.mindLensName}
              </span>
            )}
          </div>
          <div className="right flex items-center gap-2 flex-shrink-0">
            {cardData && (
              <span
                className={`badge running text-[10px] px-1.5 py-0.5 rounded ${
                  cardData.stats.runningExecutions > 0
                    ? 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300'
                    : 'bg-gray-100 dark:bg-gray-700 text-gray-400 dark:text-gray-500'
                }`}
                title={`${cardData.stats.runningExecutions} 個執行中`}
              >
                🔄 {cardData.stats.runningExecutions}
              </span>
            )}
            {cardData && (
              <span
                className={`badge artifact text-[10px] px-1.5 py-0.5 rounded ${
                  cardData.stats.artifactCount > 0
                    ? 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300'
                    : 'bg-gray-100 dark:bg-gray-700 text-gray-400 dark:text-gray-500'
                }`}
                title={`${cardData.stats.artifactCount} 個成果`}
              >
                📦 {cardData.stats.artifactCount}
              </span>
            )}
            {cardData && (
              <span
                className={`badge completed text-[10px] px-1.5 py-0.5 rounded ${
                  cardData.stats.completedExecutions > 0
                    ? 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300'
                    : 'bg-gray-100 dark:bg-gray-700 text-gray-400 dark:text-gray-500'
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
          </div>
        </div>
        <div className="block px-3 pb-2 pt-0.5 text-[10px] text-gray-500 dark:text-gray-400">
          <div className="flex items-center gap-3">
            {(project.human_owner_user_id || project.initiator_user_id) && (
              <span>負責人: {project.human_owner_user_id || project.initiator_user_id}</span>
            )}
            {project.created_at && (
              <span>
                {new Date(project.created_at).toLocaleDateString('zh-TW', {
                  year: 'numeric',
                  month: 'short',
                  day: 'numeric'
                })}
              </span>
            )}
          </div>
        </div>
      </div>

      <div className="progress-bar-container relative w-full h-1 bg-gray-200 dark:bg-gray-700 overflow-hidden">
        <div
          className="progress-fill h-full bg-blue-500 dark:bg-blue-400 rounded-full transition-all relative overflow-hidden"
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
          {loading ? (
            <div className="text-xs text-gray-500 dark:text-gray-400 text-center py-4">
              載入中...
            </div>
          ) : cardData ? (
            <div className="events-column w-full space-y-4">
              {/* Playbook List */}
              {cardData.playbooks && cardData.playbooks.length > 0 && (
                <div className="mb-4">
                  <div className="events-header text-[10px] font-semibold text-gray-700 dark:text-gray-300 mb-2">
                    Playbook 任務 ({cardData.playbooks.length})
                  </div>
                  <div className="space-y-1">
                    {cardData.playbooks.map((playbook, index) => (
                      <div
                        key={playbook.code}
                        className="flex items-center gap-2 p-2 hover:bg-gray-50 dark:hover:bg-gray-800 rounded"
                      >
                        <span className="text-xs text-gray-500 dark:text-gray-400">
                          {index + 1}.
                        </span>
                        <div className="flex-1 min-w-0">
                          <div className="text-xs font-medium text-gray-900 dark:text-gray-100">
                            {playbook.name}
                          </div>
                          {playbook.description && (
                            <div className="text-[10px] text-gray-500 dark:text-gray-400">
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
                <div className="events-header text-[10px] font-semibold text-gray-700 dark:text-gray-300 mb-2">
                  即時動態
                </div>
                <div className="events-list space-y-1 max-h-48 overflow-y-auto">
                  {(() => {
                    // 过滤只显示属于当前 project 的 events
                    const filteredEvents = cardData.recentEvents.filter(event => {
                      // 如果 event 有 projectId，只显示匹配的
                      if (event.projectId) {
                        return event.projectId === project.id;
                      }
                      // 如果没有 projectId 信息，假设属于当前 project（向后兼容）
                      return true;
                    });

                    return filteredEvents.length > 0 ? (
                      filteredEvents.slice(0, 5).map(event => (
                        <EventItem
                          key={event.id}
                          event={event}
                          onClick={() => handleOpenExecution(event.executionId)}
                        />
                      ))
                    ) : (
                      <div className="text-[10px] text-gray-400 dark:text-gray-500 text-center py-4">
                        尚無動態
                      </div>
                    );
                  })()}
                </div>
              </div>
            </div>
          ) : (
            <div className="text-xs text-gray-500 dark:text-gray-400 text-center py-4">
              無法載入數據
            </div>
          )}
        </div>
      )}

      <div className="px-3 pb-2 pt-1.5 border-t border-gray-200 dark:border-gray-700">
        <button
          onClick={async (e) => {
            e.stopPropagation();
            console.log('[ProjectCard] View button clicked', { cardData, onOpenExecution, project });

            // Try to find executionId from cardData events
            let executionId: string | null = null;
            if (cardData && cardData.recentEvents && cardData.recentEvents.length > 0) {
              for (const event of cardData.recentEvents) {
                if (event.executionId) {
                  executionId = event.executionId;
                  console.log('[ProjectCard] Found executionId from events:', executionId);
                  break;
                }
              }
            }

            // If we have executionId, navigate to execution page
            if (executionId && onOpenExecution) {
              onOpenExecution(executionId);
              return;
            }

            // If no executionId, try to fetch executions for this project
            if (!executionId && workspaceId && apiUrl) {
              try {
                console.log('[ProjectCard] No executionId in events, fetching project executions...');
                const response = await fetch(
                  `${apiUrl}/api/v1/workspaces/${workspaceId}/projects/${project.id}/execution-tree`
                );
                if (response.ok) {
                  const data = await response.json();
                  // Extract executions from playbookGroups
                  const allExecutions: any[] = [];
                  if (data.playbookGroups && Array.isArray(data.playbookGroups)) {
                    data.playbookGroups.forEach((group: any) => {
                      if (group.executions && Array.isArray(group.executions)) {
                        allExecutions.push(...group.executions);
                      }
                    });
                  }

                  if (allExecutions.length > 0) {
                    // Get the first running execution, or the most recent one
                    const runningExecution = allExecutions.find((e: any) => e.status === 'running');
                    const targetExecution = runningExecution || allExecutions[0];
                    if (targetExecution && targetExecution.execution_id) {
                      executionId = targetExecution.execution_id;
                      console.log('[ProjectCard] Found executionId from API:', executionId);
                      if (onOpenExecution) {
                        onOpenExecution(executionId);
                        return;
                      }
                    }
                  }
                }
              } catch (err) {
                console.error('[ProjectCard] Failed to fetch executions:', err);
              }
            }

            // Fallback: if we still have no executionId, try to navigate to workspace page with project focus
            if (!executionId && workspaceId) {
              console.log('[ProjectCard] No execution found, navigating to workspace page');
              router.push(`/workspaces/${workspaceId}?project_id=${project.id}`);
              return;
            }

            // Last fallback: use onFocus if available
            if (onFocus) {
              console.log('[ProjectCard] Using onFocus fallback');
              onFocus();
            }
          }}
          className="w-full text-xs text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300 font-medium py-1.5 px-2 rounded hover:bg-blue-50 dark:hover:bg-blue-900/20 transition-colors cursor-pointer"
        >
          查看 →
        </button>
      </div>
    </div>
  );
}
