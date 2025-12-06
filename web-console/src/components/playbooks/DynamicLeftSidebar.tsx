'use client';

import React from 'react';
import { getPlaybookRegistry } from '@/playbook';
import DefaultLeftSidebar from './DefaultLeftSidebar';

interface DynamicLeftSidebarProps {
  playbookCode: string | null;
  workspaceId: string;
  config: {
    type: string;
    component: string;
    config: Record<string, any>;
  } | null;
}

/**
 * DynamicLeftSidebar - Renders left sidebar component based on playbook
 *
 * This component dynamically renders the left sidebar component registered
 * by the active playbook. If no playbook is active, shows default sidebar
 * (Timeline/Outcomes/Background).
 */
export function DynamicLeftSidebar({
  playbookCode,
  workspaceId,
  config
}: DynamicLeftSidebarProps) {
  if (!playbookCode || !config) {
    return <DefaultLeftSidebar workspaceId={workspaceId} />;
  }

  const registry = getPlaybookRegistry();
  const playbook = registry.get(playbookCode);

  if (!playbook) {
    return <DefaultLeftSidebar workspaceId={workspaceId} />;
  }

  const SidebarComponent = registry.getComponent(playbookCode, config.component);

  if (!SidebarComponent) {
    console.warn(
      `Component ${config.component} not found for playbook ${playbookCode}`
    );
    return <DefaultLeftSidebar workspaceId={workspaceId} />;
  }

  return (
    <SidebarComponent
      workspaceId={workspaceId}
      playbookCode={playbookCode}
      config={config.config}
    />
  );
}

