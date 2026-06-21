'use client';

import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import type { MouseEvent } from 'react';
import { useRouter, useParams } from 'next/navigation';
import { Project } from '@/types/project';
import { isDocumentHidden, onDocumentVisible } from '@/lib/page-visibility';
import { subscribeEventStream, UnifiedEvent } from '@/components/workspace/eventProjector';
import ProjectCardView from './ProjectCardView';
import {
  fetchActiveMeetingSession,
  fetchProjectCard,
  loadMeetingSession,
  loadProjectCardWithSharedFetch,
  postMeetingChatMessage,
  startMeetingSession,
  updateProjectMeetingFlag,
} from './projectCardApi';
import {
  EMPTY_WORKFLOW_EVIDENCE,
  buildExecutionTimelineRoute,
  buildMeetingMessage,
  buildMeetingRoute,
  buildMeetingScenePatchRoute,
  calculateProjectProgress,
  filterEventsForProject,
  firstExecutionId,
  isMeetingActive,
  isMeetingEnabled,
  meetingDataForToggle,
  workflowEvidenceFromEventPayload,
  workflowEvidenceFromSession,
} from './projectCardState';
import type {
  ProjectCardApiContext,
  ProjectCardData,
  ProjectCardProps,
  WorkflowEvidenceValues,
} from './projectCardTypes';

export default function ProjectCard({
  project,
  workspaceId,
  isExpanded: controlledExpanded,
  isFocused = false,
  defaultExpanded = true,
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
  const [visibilityLoadTick, setVisibilityLoadTick] = useState(0);
  const [meetingUpdating, setMeetingUpdating] = useState(false);
  const [isHighlighted, setIsHighlighted] = useState(false);
  const [workflowEvidence, setWorkflowEvidence] = useState<WorkflowEvidenceValues>(EMPTY_WORKFLOW_EVIDENCE);
  const loadingRef = useRef(false);
  const highlightTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  const projectApiContext = useMemo<ProjectCardApiContext | null>(
    () => effectiveWorkspaceId
      ? { apiUrl, workspaceId: effectiveWorkspaceId, projectId: project.id }
      : null,
    [apiUrl, effectiveWorkspaceId, project.id],
  );

  const isExpanded = controlledExpanded !== undefined ? controlledExpanded : internalExpanded;
  const handleToggleExpand = useCallback(() => {
    if (onToggleExpand) {
      onToggleExpand();
      return;
    }
    setInternalExpanded(!internalExpanded);
  }, [internalExpanded, onToggleExpand]);

  useEffect(() => {
    const handleHighlight = (e: CustomEvent) => {
      const { projectId } = e.detail || {};
      if (projectId === project.id) {
        if (highlightTimeoutRef.current) {
          clearTimeout(highlightTimeoutRef.current);
        }

        setIsHighlighted(true);

        if (!isExpanded) {
          handleToggleExpand();
        }

        const cardElement = document.querySelector(`[data-project-card-id="${project.id}"]`);
        if (cardElement) {
          cardElement.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }

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
    if (!isExpanded || cardData || loadingRef.current || apiUrl == null || !projectApiContext || isDocumentHidden()) {
      return;
    }

    loadingRef.current = true;
    setLoading(true);

    let isMounted = true;
    const controller = new AbortController();
    const timeoutId = setTimeout(() => {
      controller.abort();
      console.error('[ProjectCard] Request timeout after 30 seconds');
    }, 30000);

    loadProjectCardWithSharedFetch(projectApiContext, controller.signal)
      .then(data => {
        clearTimeout(timeoutId);
        if (!isMounted) return;
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
  }, [cardData, apiUrl, project.id, projectApiContext, isExpanded, visibilityLoadTick]);

  useEffect(() => onDocumentVisible(() => {
    setVisibilityLoadTick((tick) => tick + 1);
  }), []);

  const meetingOnForSubscription = isMeetingEnabled(cardData, project);

  useEffect(() => {
    if (!meetingOnForSubscription || apiUrl == null || !effectiveWorkspaceId || !projectApiContext) return;

    const unsubscribe = subscribeEventStream(effectiveWorkspaceId, {
      apiUrl,
      eventTypes: ['meeting_round', 'meeting_start', 'meeting_end', 'decision_proposal', 'decision_final'],
      projectId: project.id,
      onEvent: (event: UnifiedEvent) => {
        if (event.type === 'meeting_start') {
          setWorkflowEvidence(workflowEvidenceFromEventPayload(event.payload));
        }
        fetchProjectCard(projectApiContext)
          .then(data => { if (data) setCardData(data); })
          .catch(() => { });
      },
    });

    return unsubscribe;
  }, [meetingOnForSubscription, projectApiContext, apiUrl, effectiveWorkspaceId, project.id]);

  useEffect(() => {
    const sessionId = cardData?.meeting?.session_id;
    if (!sessionId || apiUrl == null || !effectiveWorkspaceId) {
      setWorkflowEvidence(EMPTY_WORKFLOW_EVIDENCE);
      return;
    }

    let cancelled = false;

    const loadMeetingDiagnostics = async () => {
      try {
        const session = await loadMeetingSession(apiUrl, effectiveWorkspaceId, sessionId);
        if (cancelled) {
          return;
        }
        setWorkflowEvidence(workflowEvidenceFromSession(session));
      } catch (err) {
        console.error('[ProjectCard] Failed to load meeting diagnostics:', err);
        if (!cancelled) {
          setWorkflowEvidence(EMPTY_WORKFLOW_EVIDENCE);
        }
      }
    };

    void loadMeetingDiagnostics();

    return () => {
      cancelled = true;
    };
  }, [apiUrl, cardData?.meeting?.session_id, effectiveWorkspaceId]);

  const meetingEnabled = isMeetingEnabled(cardData, project);
  const meetingActive = isMeetingActive(cardData);

  const handleToggleMeeting = async (enabled: boolean) => {
    if (apiUrl == null || !effectiveWorkspaceId || meetingUpdating || !projectApiContext) return;
    setMeetingUpdating(true);
    try {
      await updateProjectMeetingFlag(projectApiContext, enabled);
      setCardData((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          meeting: meetingDataForToggle(prev.meeting, enabled),
        };
      });
      if (enabled) {
        setTimeout(async () => {
          try {
            const data = await fetchProjectCard(projectApiContext);
            if (data) {
              setCardData(data);
            }
          } catch {
            return;
          }
        }, 1500);

        try {
          let sessionId = cardData?.meeting?.session_id || '';
          if (!sessionId) {
            const active = await fetchActiveMeetingSession(projectApiContext);
            if (active.id) {
              sessionId = active.id;
            } else if (active.status === 404) {
              const started = await startMeetingSession(apiUrl, effectiveWorkspaceId, {
                project_id: project.id,
                thread_id: cardData?.storyThreadId || null,
              });
              if (started?.id) {
                sessionId = started.id;
              }
            }
          }

          await postMeetingChatMessage(apiUrl, effectiveWorkspaceId, {
            message: buildMeetingMessage(project.title, String(project.type)),
            project_id: project.id,
            thread_id: sessionId || undefined,
          });
          window.dispatchEvent(new Event('workspace-chat-updated'));
        } catch (kickoffErr) {
          console.error('[ProjectCard] Meeting auto-kickoff failed:', kickoffErr);
        }
      }
    } catch (err) {
      console.error('[ProjectCard] Failed to toggle meeting:', err);
      throw err;
    } finally {
      setMeetingUpdating(false);
    }
  };

  const handleOpenMeeting = () => {
    if (!effectiveWorkspaceId) {
      console.warn('[ProjectCard] No effectiveWorkspaceId, cannot open meeting');
      return;
    }
    router.push(buildMeetingRoute(effectiveWorkspaceId, project.id));
  };

  const handleOpenMeetingScenePatch = () => {
    if (!effectiveWorkspaceId) {
      console.warn('[ProjectCard] No effectiveWorkspaceId, cannot open meeting scene patch');
      return;
    }
    router.push(buildMeetingScenePatchRoute(effectiveWorkspaceId, project.id, cardData?.meeting?.session_id));
  };

  const handleOpenExecution = (executionId: string) => {
    if (onOpenExecution) {
      onOpenExecution(executionId);
    }
  };

  const handleCardClick = (e: MouseEvent<HTMLDivElement>) => {
    const target = e.target as HTMLElement;
    if (target.closest('.card-header') || target.closest('.progress-bar-container') || target.closest('.card-content')) {
      return;
    }

    const executionId = firstExecutionId(cardData);
    if (executionId && onOpenExecution) {
      onOpenExecution(executionId);
      return;
    }
    if (onFocus) {
      onFocus();
    }
  };

  const handleViewProject = () => {
    if (effectiveWorkspaceId) {
      router.push(buildExecutionTimelineRoute(effectiveWorkspaceId, project.id));
    } else if (onFocus) {
      onFocus();
    }
  };

  return (
    <ProjectCardView
      project={project}
      effectiveWorkspaceId={effectiveWorkspaceId}
      cardData={cardData}
      loading={loading}
      isExpanded={isExpanded}
      isFocused={isFocused}
      isHighlighted={isHighlighted}
      meetingEnabled={meetingEnabled}
      meetingActive={meetingActive}
      meetingUpdating={meetingUpdating}
      workflowEvidence={workflowEvidence}
      progress={calculateProjectProgress(cardData)}
      filteredEvents={filterEventsForProject(cardData?.recentEvents || [], project.id)}
      meetingHref={buildMeetingRoute(effectiveWorkspaceId, project.id, cardData?.meeting?.session_id)}
      onCardClick={handleCardClick}
      onToggleExpand={handleToggleExpand}
      onToggleMeeting={handleToggleMeeting}
      onOpenMeeting={handleOpenMeeting}
      onOpenMeetingScenePatch={handleOpenMeetingScenePatch}
      onOpenExecution={handleOpenExecution}
      onViewProject={handleViewProject}
    />
  );
}
