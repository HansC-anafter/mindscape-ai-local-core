'use client';

import React, { useState, useEffect } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import Header from '../../../../components/Header';
import { t } from '../../../../lib/i18n';
import { formatLocalDateTime } from '@/lib/time';

import { getApiBaseUrl } from '../../../../lib/api-url';

const API_URL = getApiBaseUrl();

export const dynamic = 'force-dynamic';
export const dynamicParams = true;

interface TimelineEvent {
  id: string;
  timestamp: string;
  event_type: string;
  actor: string;
  payload: any;
  metadata?: any;
}

export default function WorkspaceTimelinePage() {
  const params = useParams();
  const workspaceId = params?.workspaceId as string;
  const [events, setEvents] = useState<TimelineEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [workspace, setWorkspace] = useState<{ title?: string } | null>(null);

  useEffect(() => {
    const loadWorkspace = async () => {
      try {
        const response = await fetch(`${API_URL}/api/v1/workspaces/${workspaceId}`);
        if (response.ok) {
          const data = await response.json();
          setWorkspace(data);
        }
      } catch {
      }
    };

    const loadTimeline = async () => {
      try {
        setLoading(true);
        const response = await fetch(
          `${API_URL}/api/v1/workspaces/${workspaceId}/timeline?limit=50`
        );
        if (response.ok) {
          const data = await response.json();
          const timelineItems = data.items || data.events || [];
          const mappedEvents = timelineItems.map((event: any) => ({
            id: event.id,
            timestamp: event.timestamp,
            event_type: event.event_type,
            actor: event.actor,
            payload: event.payload || {},
            metadata: event.metadata || {}
          }));
          setEvents(mappedEvents);
        } else {
          setError('Failed to load timeline');
        }
      } catch {
        setError('Failed to load timeline');
      } finally {
        setLoading(false);
      }
    };

    if (workspaceId) {
      loadTimeline();
      loadWorkspace();
    }
  }, [workspaceId]);

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50">
        <Header />
        <div className="flex items-center justify-center h-[calc(100vh-64px)]">
          <div className="text-gray-500">{t('loading' as any)}</div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <Header />
      <div className="max-w-4xl mx-auto p-8">
        <Link
          href={`/workspaces/${workspaceId}`}
          className="text-blue-600 hover:text-blue-800 mb-4 inline-block"
        >
          &lt; {t('backToList' as any)}
        </Link>

        <h1 className="text-3xl font-bold text-gray-900 mb-6">
          Timeline: {workspace?.title || 'Workspace'}
        </h1>

        {error && (
          <div className="mb-4 p-4 bg-red-50 border border-red-200 rounded-lg">
            <p className="text-red-700">{error}</p>
          </div>
        )}

        {events.length === 0 ? (
          <div className="text-center py-12">
            <p className="text-gray-500">{t('noData' as any)}</p>
          </div>
        ) : (
          <div className="space-y-4">
            {events.map((event) => {
              let content = '';
              let displayType = event.event_type;

              if (event.event_type === 'message') {
                content = event.payload?.message || event.payload?.text || '';
                displayType = event.actor === 'user' ? 'User Message' : 'Assistant Reply';
              } else if (event.event_type === 'playbook_step') {
                content = `Playbook: ${event.payload?.playbook_code || 'unknown'} - Step: ${event.payload?.step || 'unknown'}`;
                displayType = 'Playbook Step';
              } else if (event.event_type === 'tool_call') {
                content = `Tool: ${event.payload?.tool_fqn || event.payload?.tool_name || 'unknown'}`;
                displayType = 'Tool Call';
              } else if (event.event_type === 'project_created') {
                content = `Workspace created: ${event.payload?.title || event.payload?.workspace_id || ''}`;
                displayType = 'Workspace Created';
              } else {
                content = event.payload ? JSON.stringify(event.payload, null, 2) : '';
              }

              return (
                <div
                  key={event.id}
                  className="bg-white rounded-lg border border-gray-200 p-4 hover:shadow-md transition-shadow"
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-2">
                        <div className="text-sm text-gray-500">
                          {formatLocalDateTime(event.timestamp)}
                        </div>
                        <span className="text-xs px-2 py-0.5 bg-blue-100 text-blue-700 rounded">
                          {event.actor}
                        </span>
                      </div>
                      <div className="text-sm font-medium text-gray-700 mb-2">
                        {displayType}
                      </div>
                      {content && (
                        <div className="text-gray-900 whitespace-pre-wrap break-words">
                          {content}
                        </div>
                      )}
                      {!content && (
                        <div className="text-gray-400 text-sm italic">
                          No content
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
