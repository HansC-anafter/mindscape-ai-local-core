'use client';

import React, { useState } from 'react';
import LeftSidebarTabs from '../../app/workspaces/[workspaceId]/components/LeftSidebarTabs';
import TimelinePanel from '../../app/workspaces/components/TimelinePanel';
import OutcomesPanel from '../../app/workspaces/[workspaceId]/components/OutcomesPanel';
import { PackPanel } from '../../app/workspaces/[workspaceId]/components/PackPanel';

import { getApiBaseUrl } from '../../lib/api-url';

const API_URL = getApiBaseUrl();

interface DefaultLeftSidebarProps {
  workspaceId: string;
}

/**
 * DefaultLeftSidebar - Default left sidebar for workspace
 *
 * Shows Timeline, Outcomes, and Pack tabs when no playbook is active.
 * This is the default "dispatch center" for general workspace navigation.
 */
export default function DefaultLeftSidebar({
  workspaceId
}: DefaultLeftSidebarProps) {
  const [activeTab, setActiveTab] = useState<'timeline' | 'outcomes' | 'pack'>('timeline');

  return (
    <div className="w-80 h-full flex flex-col border-r dark:border-gray-700 bg-white dark:bg-gray-900">
      <LeftSidebarTabs
        activeTab={activeTab}
        onTabChange={setActiveTab}
        timelineContent={
          <TimelinePanel
            workspaceId={workspaceId}
            apiUrl={API_URL}
            isInSettingsPage={false}
          />
        }
        outcomesContent={
          <OutcomesPanel workspaceId={workspaceId} apiUrl={API_URL} />
        }
        packContent={
          <PackPanel
            workspaceId={workspaceId}
            apiUrl={API_URL}
          />
        }
      />
    </div>
  );
}

