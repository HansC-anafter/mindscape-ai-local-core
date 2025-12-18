'use client';

import React, { useState, useEffect } from 'react';
import { subscribeEventStream, eventToTimelineItem, UnifiedEvent, TimelineItem } from './eventProjector';
import { AlertCircle, CheckCircle, Clock, Play, FileText, GitBranch, Tool } from 'lucide-react';

interface EventTimelineProps {
  workspaceId: string;
  apiUrl: string;
  onJumpToCard?: (cardId: string) => void;
}

export function EventTimeline({
  workspaceId,
  apiUrl,
  onJumpToCard,
}: EventTimelineProps) {
  const [events, setEvents] = useState<UnifiedEvent[]>([]);
  const [timelineItems, setTimelineItems] = useState<TimelineItem[]>([]);

  useEffect(() => {
    const unsubscribe = subscribeEventStream(
      workspaceId,
      {
        apiUrl,
        eventTypes: [
          'decision_required',
          'run_state_changed',
          'artifact_created',
          'tool_result',
          'playbook_step',
          'branch_proposed',
        ],
        onEvent: (event: UnifiedEvent) => {
          setEvents(prev => {
            if (prev.find(e => e.id === event.id)) {
              return prev;
            }
            return [...prev, event];
          });
        },
        onError: (error) => {
          console.error('Event stream error:', error);
        },
      }
    );

    return () => {
      unsubscribe();
    };
  }, [workspaceId, apiUrl]);

  useEffect(() => {
    const loadInitialEvents = async () => {
      try {
        const response = await fetch(
          `${apiUrl}/api/v1/workspaces/${workspaceId}/events?limit=50`
        );
        if (response.ok) {
          const data = await response.json();
          const initialEvents = data.events || [];
          setEvents(initialEvents);
        }
      } catch (err) {
        console.error('Failed to load initial events:', err);
      }
    };

    loadInitialEvents();
  }, [workspaceId, apiUrl]);

  useEffect(() => {
    const items = events
      .map(event => eventToTimelineItem(event))
      .filter((item): item is TimelineItem => item !== null)
      .sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());

    setTimelineItems(items);
  }, [events]);

  const getEventIcon = (type: string) => {
    switch (type) {
      case 'decision_required':
        return AlertCircle;
      case 'run_state_changed':
        return Play;
      case 'artifact_created':
        return FileText;
      case 'tool_result':
        return Tool;
      case 'playbook_step':
        return CheckCircle;
      case 'branch_proposed':
        return GitBranch;
      default:
        return Clock;
    }
  };

  const getEventColor = (type: string) => {
    switch (type) {
      case 'decision_required':
        return 'text-yellow-600 dark:text-yellow-400';
      case 'run_state_changed':
        return 'text-blue-600 dark:text-blue-400';
      case 'artifact_created':
        return 'text-green-600 dark:text-green-400';
      case 'tool_result':
        return 'text-gray-600 dark:text-gray-400';
      case 'playbook_step':
        return 'text-purple-600 dark:text-purple-400';
      case 'branch_proposed':
        return 'text-orange-600 dark:text-orange-400';
      default:
        return 'text-gray-500 dark:text-gray-500';
    }
  };

  return (
    <div className="event-timeline space-y-3">
      {timelineItems.length > 0 ? (
        timelineItems.map(item => {
          const Icon = getEventIcon(item.type);
          const color = getEventColor(item.type);

          return (
            <div
              key={item.id}
              className={`flex items-start gap-3 p-3 rounded-lg border border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors ${
                item.clickable ? 'cursor-pointer' : ''
              }`}
              onClick={() => {
                if (item.clickable && item.targetCardId) {
                  onJumpToCard?.(item.targetCardId);
                }
              }}
            >
              <Icon className={`w-4 h-4 ${color} flex-shrink-0 mt-0.5`} />
              <div className="flex-1 min-w-0">
                <div className="text-xs font-medium text-gray-900 dark:text-gray-100">
                  {item.summary}
                </div>
                <div className="text-xs text-gray-500 dark:text-gray-500 mt-1">
                  {new Date(item.timestamp).toLocaleString('zh-TW', {
                    month: 'short',
                    day: 'numeric',
                    hour: '2-digit',
                    minute: '2-digit',
                  })}
                </div>
              </div>
              {item.clickable && (
                <div className="text-xs text-blue-600 dark:text-blue-400 flex-shrink-0">
                  View →
                </div>
              )}
            </div>
          );
        })
      ) : (
        <div className="text-xs text-gray-400 dark:text-gray-500 text-center py-4">
          No events
        </div>
      )}
    </div>
  );
}

