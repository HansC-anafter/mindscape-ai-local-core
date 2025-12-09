'use client';

import React from 'react';
import { TimelineEvent } from '@/lib/story-thread-api';

interface TimelineProps {
  threadId: string;
  events: TimelineEvent[];
  onEventClick?: (event: TimelineEvent) => void;
}

export function Timeline({ threadId, events, onEventClick }: TimelineProps) {
  const sortedEvents = [...events].sort((a, b) =>
    new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
  );

  const getEventIcon = (eventType: string) => {
    switch (eventType) {
      case 'chapter_started':
        return 'CH';
      case 'chapter_completed':
        return 'OK';
      case 'playbook_executed':
        return 'PB';
      case 'artifact_created':
        return 'AF';
      case 'context_updated':
        return 'UP';
      default:
        return 'EV';
    }
  };

  const formatTimestamp = (timestamp: string) => {
    const date = new Date(timestamp);
    return date.toLocaleString('zh-TW', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  return (
    <div className="timeline-container">
      <div className="timeline-header">
        <h3 className="text-lg font-semibold mb-4">時間線</h3>
      </div>
      <div className="timeline-events space-y-4">
        {sortedEvents.length === 0 ? (
          <div className="text-gray-500 text-center py-8">
            尚無時間線事件
          </div>
        ) : (
          sortedEvents.map((event, index) => (
            <div
              key={event.event_id}
              className="timeline-event flex items-start gap-4 p-4 rounded-lg border border-gray-200 hover:bg-gray-50 cursor-pointer transition-colors"
              onClick={() => onEventClick?.(event)}
            >
              <div className="timeline-icon flex-shrink-0 w-8 h-8 rounded-full bg-blue-100 flex items-center justify-center text-xs font-semibold text-blue-700">
                {getEventIcon(event.event_type)}
              </div>
              <div className="timeline-content flex-1">
                <div className="event-header flex items-center justify-between mb-1">
                  <span className="event-type font-medium text-gray-900">
                    {event.event_type}
                  </span>
                  <span className="event-time text-sm text-gray-500">
                    {formatTimestamp(event.timestamp)}
                  </span>
                </div>
                <div className="event-description text-gray-700">
                  {event.description}
                </div>
                {event.chapter_id && (
                  <div className="event-chapter text-sm text-gray-500 mt-1">
                    章節: {event.chapter_id}
                  </div>
                )}
                {event.metadata && Object.keys(event.metadata).length > 0 && (
                  <div className="event-metadata text-xs text-gray-400 mt-2">
                    {JSON.stringify(event.metadata, null, 2)}
                  </div>
                )}
              </div>
            </div>
          ))
        )}
      </div>
      <style jsx>{`
        .timeline-container {
          max-height: 600px;
          overflow-y: auto;
        }
        .timeline-event {
          position: relative;
        }
        .timeline-event::before {
          content: '';
          position: absolute;
          left: 20px;
          top: 50px;
          bottom: -16px;
          width: 2px;
          background: #e5e7eb;
        }
        .timeline-event:last-child::before {
          display: none;
        }
      `}</style>
    </div>
  );
}

export default Timeline;

