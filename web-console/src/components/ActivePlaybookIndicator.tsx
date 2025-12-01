'use client';

import React, { useState, useEffect, useRef } from 'react';
import { useT } from '@/lib/i18n';

// Laser scan effect styles
const laserScanStyle = `
  @keyframes laser-scan {
    0% {
      transform: translateX(-100%);
    }
    100% {
      transform: translateX(300%);
    }
  }

  .laser-scan-text {
    position: relative;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    color: rgb(37, 99, 235);
    overflow: hidden;
    line-height: 1;
  }

  .laser-scan-text::after {
    content: '';
    position: absolute;
    left: 0;
    top: 0;
    width: 30%;
    height: 100%;
    background: linear-gradient(
      90deg,
      transparent,
      rgba(255, 255, 255, 0.8),
      rgba(255, 255, 255, 1),
      rgba(255, 255, 255, 0.8),
      transparent
    );
    animation: laser-scan 2.5s linear infinite;
    pointer-events: none;
    mix-blend-mode: overlay;
  }

  @keyframes fadeInOut {
    0%, 100% {
      opacity: 0.4;
    }
    50% {
      opacity: 1;
    }
  }

  .fade-in-out {
    animation: fadeInOut 2s ease-in-out infinite;
    transition: opacity 0.3s ease-in-out;
  }

  @keyframes slideIn {
    from {
      opacity: 0;
      transform: translateY(-4px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }

  .slide-in {
    animation: slideIn 0.4s ease-out;
  }
`;

interface ActivePlaybook {
  playbook_id?: string;
  pack_id?: string;
  display_name: string;
  status: string;
}

interface ActivePlaybookIndicatorProps {
  workspaceId: string;
  apiUrl?: string;
}

export default function ActivePlaybookIndicator({
  workspaceId,
  apiUrl = 'http://localhost:8000',
}: ActivePlaybookIndicatorProps) {
  const t = useT();
  const [activePlaybooks, setActivePlaybooks] = useState<ActivePlaybook[]>([]);
  const [pendingTasksCount, setPendingTasksCount] = useState(0);
  const [loading, setLoading] = useState(false);
  const [isVisible, setIsVisible] = useState(false);

  // Debounce helper ref
  const loadTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  const loadActivePlaybooks = async () => {
    // Initialize variables at function scope to avoid ReferenceError
    let runningTasks: any[] = [];
    let pendingTasks: any[] = [];

    try {
      setLoading(true);

      // Try multiple data sources
      const playbookMap = new Map<string, ActivePlaybook>();

      // 1. Try loading from tasks
      try {
        const tasksResponse = await fetch(
          `${apiUrl}/api/v1/workspaces/${workspaceId}/tasks?limit=20`
        );

        if (tasksResponse.ok) {
          const tasksData = await tasksResponse.json();
          const allTasks = tasksData.tasks || [];

          if (process.env.NODE_ENV === 'development') {
          console.log('[ActivePlaybookIndicator] Tasks data:', allTasks);

          // Debug: log all tasks to understand structure
          if (allTasks.length > 0) {
            console.log('[ActivePlaybookIndicator] All tasks details:', allTasks.map((t: any) => ({
              id: t.id,
              status: t.status,
              pack_id: t.pack_id,
              playbook_id: t.playbook_id,
              task_type: t.task_type,
              execution_id: t.execution_id
            })));
            }
          }

          // Filter tasks by status
          // Status values from API are lowercase: "running", "pending", "succeeded", "failed"
          runningTasks = allTasks.filter(
            (task: any) => {
              const status = (task.status || '').toLowerCase().trim();
              const hasPlaybook = !!(task.pack_id || task.playbook_id || task.task_type);
              return status === 'running' && hasPlaybook;
            }
          );

          pendingTasks = allTasks.filter(
            (task: any) => {
              const status = (task.status || '').toLowerCase().trim();
              const hasPlaybook = !!(task.pack_id || task.playbook_id || task.task_type);
              return status === 'pending' && hasPlaybook;
            }
          );

          if (process.env.NODE_ENV === 'development') {
          console.log('[ActivePlaybookIndicator] Running tasks:', runningTasks);
          console.log('[ActivePlaybookIndicator] Pending tasks:', pendingTasks);
          }

          // Collect RUNNING playbooks
          runningTasks.forEach((task: any) => {
            const key = task.pack_id || task.playbook_id || task.task_type || '';
            if (key && !playbookMap.has(key)) {
              playbookMap.set(key, {
                playbook_id: task.playbook_id,
                pack_id: task.pack_id,
                display_name: task.pack_id || task.playbook_id || task.task_type || 'Unknown',
                status: task.status
              });
            }
          });

          // Count unique pending tasks (if no running tasks)
          if (runningTasks.length === 0) {
            const uniquePendingPlaybooks = new Set<string>();
            pendingTasks.forEach((task: any) => {
              const key = task.pack_id || task.playbook_id || task.task_type || '';
              if (key) {
                uniquePendingPlaybooks.add(key);
              }
            });
            setPendingTasksCount(uniquePendingPlaybooks.size);
          } else {
            setPendingTasksCount(0);
          }
        }
      } catch (err) {
        console.warn('[ActivePlaybookIndicator] Failed to load playbooks from tasks:', err);
      }

      // Note: We only check tasks API for RUNNING status
      // Timeline items are historical records, not current execution status

      const playbooks = Array.from(playbookMap.values());
      if (process.env.NODE_ENV === 'development') {
      console.log('[ActivePlaybookIndicator] Final playbooks:', playbooks);
      }

      setActivePlaybooks(playbooks);

      // Fade in/out animation - show animation if there are running tasks or pending tasks
      const currentPendingCount = runningTasks.length === 0
        ? Array.from(new Set(pendingTasks.map((t: any) => t.pack_id || t.playbook_id || t.task_type || '').filter(Boolean))).length
        : 0;

      if (playbooks.length > 0 || currentPendingCount > 0) {
        setIsVisible(true);
      } else {
        setIsVisible(false);
      }
    } catch (err) {
      console.error('[ActivePlaybookIndicator] Failed to load active playbooks:', err);
    } finally {
      setLoading(false);
    }
  };

  // Debounced version of loadActivePlaybooks
  const debouncedLoad = () => {
    if (loadTimeoutRef.current) clearTimeout(loadTimeoutRef.current);
    loadTimeoutRef.current = setTimeout(() => {
      loadActivePlaybooks();
    }, 300);
  };

  // Pure event-driven: No polling, only react to events
  useEffect(() => {
    // Initial load only
    loadActivePlaybooks();

    // Track last event time for health check
    let lastEventTime = Date.now();
    let healthCheckTimer: NodeJS.Timeout | null = null;

    // Event handlers - primary update mechanism
    const handleTaskUpdate = () => {
      lastEventTime = Date.now();
      debouncedLoad();
      // Reset health check timer on event
      if (healthCheckTimer) {
        clearTimeout(healthCheckTimer);
        healthCheckTimer = null;
      }
      scheduleHealthCheck();
    };

    // Health check: Only check if no events for 30 seconds (safety net)
    const scheduleHealthCheck = () => {
      if (healthCheckTimer) clearTimeout(healthCheckTimer);

      healthCheckTimer = setTimeout(() => {
        const timeSinceLastEvent = Date.now() - lastEventTime;

        // Only health check if page is visible and no events for 30s
        if (!document.hidden && timeSinceLastEvent >= 30000) {
          if (process.env.NODE_ENV === 'development') {
          console.log('[ActivePlaybookIndicator] Health check: No events for 30s, checking status');
          }
          loadActivePlaybooks();
          lastEventTime = Date.now();
        }

        // Schedule next health check
        scheduleHealthCheck();
      }, 30000); // Check every 30s if needed
    };

    // Start health check timer
    scheduleHealthCheck();

    // Listen to events (primary mechanism)
    window.addEventListener('workspace-task-updated', handleTaskUpdate);
    window.addEventListener('workspace-chat-updated', handleTaskUpdate);

    // Refresh when page becomes visible (in case events were missed)
    const handleVisibilityChange = () => {
      if (!document.hidden) {
        const timeSinceLastEvent = Date.now() - lastEventTime;
        // Refresh if page was hidden for more than 5 seconds
        if (timeSinceLastEvent > 5000) {
          debouncedLoad();
          lastEventTime = Date.now();
        }
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);

    return () => {
      window.removeEventListener('workspace-task-updated', handleTaskUpdate);
      window.removeEventListener('workspace-chat-updated', handleTaskUpdate);
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      if (loadTimeoutRef.current) clearTimeout(loadTimeoutRef.current);
      if (healthCheckTimer) clearTimeout(healthCheckTimer);
    };
  }, [workspaceId]);

  // Format playbook names for display
  const formatPlaybookName = (playbook: ActivePlaybook): string => {
    // Convert snake_case or kebab-case to readable format
    const name = playbook.display_name
      .replace(/[_-]/g, ' ')
      .replace(/\b\w/g, (l) => l.toUpperCase());
    return name;
  };

  // Always render the indicator area, even if empty (to maintain layout)
  const playbookNames = activePlaybooks.length > 0
    ? activePlaybooks.map(formatPlaybookName).join(' • ')
    : '';

  // Show pending status if no running tasks but has pending tasks
  const showPendingStatus = activePlaybooks.length === 0 && pendingTasksCount > 0;

  return (
    <>
      <style dangerouslySetInnerHTML={{ __html: laserScanStyle }} />
      <div className={`flex items-center gap-1.5 leading-tight ${isVisible || showPendingStatus ? 'fade-in-out slide-in opacity-100' : 'opacity-50'}`}>
        <span className="text-xs font-medium text-gray-700 whitespace-nowrap leading-tight">
          {t('activePlaybook')}:
        </span>
        {playbookNames ? (
          <button
            className={`
              px-2 py-0.5 text-xs font-medium rounded transition-all duration-300
              bg-gradient-to-r from-blue-50 to-blue-100 text-blue-700
              border border-blue-200 hover:border-blue-300
              shadow-sm hover:shadow-md hover:-translate-y-0.5
              backdrop-blur-sm leading-tight
            `}
            title={playbookNames}
            onClick={() => {
              // TODO: Open playbook details modal or navigate to playbook page
              console.log('View playbook details:', activePlaybooks);
            }}
          >
            <span className="laser-scan-text" data-text={playbookNames}>
              {playbookNames}
            </span>
          </button>
        ) : showPendingStatus ? (
          <span className="text-xs text-yellow-600 italic leading-tight fade-in-out">
            {t('pendingTasksWaiting', { count: String(pendingTasksCount) })}
          </span>
        ) : (
          <span className="text-xs text-gray-400 italic leading-tight">
            {t('noActivePlaybook')}
          </span>
        )}
      </div>
    </>
  );
}
