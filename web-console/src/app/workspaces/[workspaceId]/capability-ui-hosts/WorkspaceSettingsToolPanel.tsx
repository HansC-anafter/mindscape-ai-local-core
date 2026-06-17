'use client';

import React, { useState } from 'react';
import {
  Bot,
  ChevronDown,
  ChevronRight,
  Database,
  RefreshCw,
  Settings as SettingsIcon,
  Share2,
  SlidersHorizontal,
} from 'lucide-react';

import {
  DataSection,
  ExecutionSection,
  SocialMediaSection,
  ToolEnginesSection,
} from './WorkspaceSettingsToolPanelSections';
import { StatusSection } from './WorkspaceSettingsToolPanelStatus';
import type {
  SettingsSection,
  WorkspaceSettingsToolPanelProps,
} from './WorkspaceSettingsToolPanelTypes';
import { WorkspaceSection } from './WorkspaceSettingsToolPanelWorkspace';

const SECTIONS: Array<{ id: SettingsSection; icon: React.ReactNode }> = [
  { id: 'Status', icon: <RefreshCw aria-hidden="true" className="h-4 w-4" /> },
  { id: 'Workspace', icon: <SettingsIcon aria-hidden="true" className="h-4 w-4" /> },
  { id: 'Execution', icon: <Bot aria-hidden="true" className="h-4 w-4" /> },
  { id: 'Tools', icon: <SlidersHorizontal aria-hidden="true" className="h-4 w-4" /> },
  { id: 'Social', icon: <Share2 aria-hidden="true" className="h-4 w-4" /> },
  { id: 'Data', icon: <Database aria-hidden="true" className="h-4 w-4" /> },
];

export default function WorkspaceSettingsToolPanel({
  workspaceId,
  apiUrl,
}: WorkspaceSettingsToolPanelProps) {
  const [openSections, setOpenSections] = useState<Record<SettingsSection, boolean>>({
    Status: true,
    Workspace: false,
    Execution: false,
    Tools: false,
    Social: false,
    Data: false,
  });

  const toggleSection = (sectionId: SettingsSection) => {
    setOpenSections((current) => ({
      ...current,
      [sectionId]: !current[sectionId],
    }));
  };

  const renderSectionContent = (sectionId: SettingsSection) => {
    if (sectionId === 'Status') {
      return <StatusSection apiUrl={apiUrl} workspaceId={workspaceId} />;
    }
    if (sectionId === 'Workspace') {
      return <WorkspaceSection apiUrl={apiUrl} />;
    }
    if (sectionId === 'Execution') {
      return <ExecutionSection apiUrl={apiUrl} workspaceId={workspaceId} />;
    }
    if (sectionId === 'Tools') {
      return <ToolEnginesSection workspaceId={workspaceId} />;
    }
    if (sectionId === 'Social') {
      return <SocialMediaSection workspaceId={workspaceId} />;
    }
    return <DataSection apiUrl={apiUrl} workspaceId={workspaceId} />;
  };

  return (
    <div
      className="flex h-full min-h-0 w-full flex-col bg-white text-gray-900 dark:bg-gray-950 dark:text-gray-100"
      data-testid="workspace-settings-panel"
    >
      <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain p-2" data-testid="workspace-settings-panel-body">
        <div className="space-y-2" data-testid="workspace-settings-section-stack">
          {SECTIONS.map((section) => {
            const isOpen = openSections[section.id];
            const sectionKey = section.id.toLowerCase();
            return (
              <section
                key={section.id}
                className="overflow-hidden rounded border border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-950"
                data-testid={`workspace-settings-section-${sectionKey}`}
              >
                <button
                  type="button"
                  className={`flex w-full items-center justify-between gap-2 px-3 py-2 text-left ${
                    isOpen
                      ? 'bg-gray-100 text-gray-950 dark:bg-gray-900 dark:text-white'
                      : 'text-gray-600 hover:bg-gray-50 hover:text-gray-950 dark:text-gray-300 dark:hover:bg-gray-900 dark:hover:text-white'
                  }`}
                  aria-expanded={isOpen}
                  aria-controls={`workspace-settings-section-body-${sectionKey}`}
                  onClick={() => toggleSection(section.id)}
                >
                  <span className="flex min-w-0 items-center gap-2">
                    {isOpen ? (
                      <ChevronDown aria-hidden="true" className="h-4 w-4 shrink-0" />
                    ) : (
                      <ChevronRight aria-hidden="true" className="h-4 w-4 shrink-0" />
                    )}
                    <span className="shrink-0">{section.icon}</span>
                    <span className="text-sm font-semibold">{section.id}</span>
                  </span>
                </button>
                {isOpen ? (
                  <div
                    id={`workspace-settings-section-body-${sectionKey}`}
                    className="border-t border-gray-200 p-3 dark:border-gray-800"
                    data-testid={`workspace-settings-${sectionKey}-section-panel`}
                  >
                    {renderSectionContent(section.id)}
                  </div>
                ) : null}
              </section>
            );
          })}
        </div>
      </div>
    </div>
  );
}
