'use client';

import React from 'react';
import AITeamPanel from '../execution/AITeamPanel';
import { IntentCardPanel } from './IntentCardPanel';
import type { AITeamMember } from '../execution/AITeamPanel';
import './RightSidebar.css';

interface RightSidebarProps {
  workspaceId: string;
  apiUrl: string;
  aiTeamMembers: AITeamMember[];
  isExecuting: boolean;
}

export function RightSidebar({
  workspaceId,
  apiUrl,
  aiTeamMembers,
  isExecuting,
}: RightSidebarProps) {
  return (
    <div className="right-sidebar">
      <section className="sidebar-section ai-team-section">
        <div className="section-header neutral">
          <span className="title">AI Collaboration Team</span>
        </div>
        <AITeamPanel members={aiTeamMembers} isLoading={isExecuting} />
      </section>

      <section className="sidebar-section intent-section">
        <IntentCardPanel workspaceId={workspaceId} apiUrl={apiUrl} />
      </section>
    </div>
  );
}

