import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  buildActiveMeetingSessionUrl,
  buildMeetingSessionUrl,
  buildProjectCardDedupKey,
  buildProjectCardUrl,
  buildProjectUrl,
  buildStartMeetingSessionUrl,
  buildWorkspaceChatUrl,
} from './projectCardApi';
import {
  buildExecutionTimelineRoute,
  buildMeetingMessage,
  buildMeetingRoute,
  buildMeetingScenePatchRoute,
  calculateProjectProgress,
  filterEventsForProject,
  firstExecutionId,
  meetingDataForToggle,
  workflowEvidenceFromEventPayload,
  workflowEvidenceFromSession,
} from './projectCardState';
import type { ProjectCardData } from './projectCardTypes';

const componentsDir = dirname(fileURLToPath(import.meta.url));
const webConsoleRoot = join(componentsDir, '../../../../..');
const touchedFiles = [
  'ProjectCard.tsx',
  'ProjectCardView.tsx',
  'projectCardTypes.ts',
  'projectCardApi.ts',
  'projectCardState.ts',
  'projectCardSeams.spec.ts',
];

function readComponentFile(fileName: string): string {
  return readFileSync(join(componentsDir, fileName), 'utf8');
}

function readWebConsoleFile(pathFromRoot: string): string {
  return readFileSync(join(webConsoleRoot, pathFromRoot), 'utf8');
}

function cardData(overrides: Partial<ProjectCardData> = {}): ProjectCardData {
  return {
    projectId: 'project-1',
    projectName: 'Demo Project',
    status: 'active',
    lastActivity: '2026-06-21T00:00:00Z',
    stats: {
      totalPlaybooks: 4,
      runningExecutions: 1,
      pendingConfirmations: 0,
      completedExecutions: 2,
      artifactCount: 3,
    },
    progress: {
      current: 20,
      label: 'Running',
    },
    recentEvents: [
      {
        id: 'event-1',
        type: 'playbook_started',
        playbookCode: 'demo',
        playbookName: 'Demo',
        executionId: 'exec-1',
        timestamp: '2026-06-21T00:00:00Z',
        projectId: 'project-1',
      },
      {
        id: 'event-2',
        type: 'artifact_created',
        playbookCode: 'other',
        playbookName: 'Other',
        executionId: 'exec-2',
        timestamp: '2026-06-21T00:01:00Z',
        projectId: 'project-2',
      },
      {
        id: 'event-3',
        type: 'step_completed',
        playbookCode: 'global',
        playbookName: 'Global',
        executionId: 'exec-3',
        timestamp: '2026-06-21T00:02:00Z',
      },
    ],
    ...overrides,
  };
}

describe('project card seams', () => {
  it('builds existing endpoint shapes and dedupe key', () => {
    const context = { apiUrl: 'http://api.test', workspaceId: 'workspace-1', projectId: 'project-1' };

    expect(buildProjectCardUrl(context)).toBe('http://api.test/api/v1/workspaces/workspace-1/projects/project-1/card');
    expect(buildProjectUrl(context)).toBe('http://api.test/api/v1/workspaces/workspace-1/projects/project-1');
    expect(buildMeetingSessionUrl('http://api.test', 'workspace-1', 'session-1')).toBe('http://api.test/api/v1/workspaces/workspace-1/meeting-sessions/session-1');
    expect(buildActiveMeetingSessionUrl(context)).toBe('http://api.test/api/v1/workspaces/workspace-1/meeting-sessions/active?project_id=project-1');
    expect(buildStartMeetingSessionUrl('http://api.test', 'workspace-1')).toBe('http://api.test/api/v1/workspaces/workspace-1/meeting-sessions/start');
    expect(buildWorkspaceChatUrl('http://api.test', 'workspace-1')).toBe('http://api.test/api/v1/workspaces/workspace-1/chat');
    expect(buildProjectCardDedupKey(context)).toBe('workspace-project-card:workspace-1:project-1');
  });

  it('builds existing navigation routes and meeting message', () => {
    expect(buildMeetingRoute('workspace-1', 'project-1')).toBe('/workspaces/workspace-1/meetings?project_id=project-1');
    expect(buildMeetingRoute('workspace-1', 'project-1', 'session-1')).toBe('/workspaces/workspace-1/meetings?project_id=project-1&session_id=session-1');
    expect(buildMeetingScenePatchRoute('workspace-1', 'project-1')).toBe('/workspaces/workspace-1/meetings?project_id=project-1&open_patch=1');
    expect(buildMeetingScenePatchRoute('workspace-1', 'project-1', 'session-1')).toBe('/workspaces/workspace-1/meetings?project_id=project-1&open_patch=1&session_id=session-1');
    expect(buildExecutionTimelineRoute('workspace-1', 'project-1')).toBe('/workspaces/workspace-1/executions/timeline?project_id=project-1');
    expect(buildMeetingMessage('Demo', 'research')).toBe('[Meeting Started] Start project meeting for "Demo" (research)');
  });

  it('derives workflow evidence and meeting toggle data', () => {
    expect(workflowEvidenceFromEventPayload({
      workflow_evidence_profile: 'compact',
      workflow_evidence_scope: 'workspace',
      workflow_evidence_selected_line_count: 10,
      workflow_evidence_total_line_budget: 100,
      workflow_evidence_total_candidate_count: 20,
      workflow_evidence_total_dropped_count: 2,
      workflow_evidence_rendered_section_count: 3,
      workflow_evidence_budget_utilization_ratio: 0.5,
    })).toMatchObject({
      profile: 'compact',
      scope: 'workspace',
      selectedLineCount: 10,
      totalLineBudget: 100,
      totalCandidateCount: 20,
      totalDroppedCount: 2,
      renderedSectionCount: 3,
      budgetUtilizationRatio: 0.5,
    });

    expect(workflowEvidenceFromSession({
      metadata: {
        workflow_evidence_diagnostics: {
          profile: 'full',
          scope: 'meeting',
          selected_line_count: 8,
        },
      },
    })).toMatchObject({
      profile: 'full',
      scope: 'meeting',
      selectedLineCount: 8,
    });

    expect(meetingDataForToggle({ session_id: 'session-1', round_count: 2 }, false)).toMatchObject({
      enabled: false,
      active: false,
      session_id: 'session-1',
      status: null,
      round_count: 2,
      max_rounds: 5,
    });
  });

  it('calculates progress and filters events by project', () => {
    const data = cardData();

    expect(calculateProjectProgress(data)).toEqual({
      progressPercentage: 20,
      scanRangeStart: 20,
      scanRangeEnd: 70,
      scanRangeWidth: 50,
    });
    expect(filterEventsForProject(data.recentEvents, 'project-1').map((event) => event.id)).toEqual(['event-1', 'event-3']);
    expect(firstExecutionId(data)).toBe('exec-1');
    expect(firstExecutionId(cardData({ stats: { ...data.stats, runningExecutions: 0 } }))).toBeNull();
  });

  it('keeps touched component files below the line gate', () => {
    for (const fileName of touchedFiles) {
      const lineCount = readComponentFile(fileName).split(/\r?\n/).length;
      expect(lineCount, fileName).toBeLessThanOrEqual(500);
    }
  });

  it('keeps API ownership in the API helper', () => {
    const apiSource = readComponentFile('projectCardApi.ts');
    expect(apiSource).toContain('fetch(');
    expect(apiSource).toContain('/api/v1/workspaces/${workspaceId}/projects/${projectId}/card');
    expect(apiSource).toContain('/api/v1/workspaces/${workspaceId}/meeting-sessions/start');
    expect(apiSource).toContain('/api/v1/workspaces/${workspaceId}/chat');

    for (const fileName of ['ProjectCardView.tsx', 'projectCardState.ts']) {
      const source = readComponentFile(fileName);
      expect(source, fileName).not.toMatch(/\bfetch\s*\(/);
      expect(source, fileName).not.toContain('/api/v1/');
    }
  });

  it('keeps the ProjectCard view resource passive', () => {
    const source = readComponentFile('ProjectCardView.tsx');
    expect(source).not.toMatch(/\bfetch\s*\(/);
    expect(source).not.toContain('/api/v1/');
    expect(source).not.toContain('setTimeout(');
    expect(source).not.toContain('setInterval(');
    expect(source).not.toContain('AbortController');
    expect(source).not.toContain('localStorage');
    expect(source).not.toContain('sessionStorage');
    expect(source).not.toContain('EventSource');
    expect(source).not.toContain('WebSocket');
    expect(source).not.toMatch(/\bpoll/i);
  });

  it('keeps resource timing and event stream ownership in ProjectCard', () => {
    const source = readComponentFile('ProjectCard.tsx');
    expect(source).toContain('new AbortController()');
    expect(source).toContain('setTimeout(() => {');
    expect(source).toContain('setTimeout(async () => {');
    expect(source).toContain('subscribeEventStream(effectiveWorkspaceId');
    expect(source).toContain("window.addEventListener('highlight-project-card'");
    expect(source).toContain("window.dispatchEvent(new Event('workspace-chat-updated'))");
  });

  it('preserves live ProjectCard callers', () => {
    const projectsPanel = readWebConsoleFile('src/app/workspaces/[workspaceId]/components/ProjectsPanel.tsx');
    const projectSubTabs = readWebConsoleFile('src/app/workspaces/[workspaceId]/components/ProjectSubTabs.tsx');

    expect(projectsPanel).toContain("import ProjectCard from './ProjectCard'");
    expect(projectSubTabs).toContain("import ProjectCard from './ProjectCard'");
    expect(projectsPanel).toContain('<ProjectCard');
    expect(projectSubTabs).toContain('<ProjectCard');
  });

  it('keeps touched source files ascii only', () => {
    for (const fileName of touchedFiles) {
      expect(readComponentFile(fileName), fileName).not.toMatch(/[^\x00-\x7F]/);
    }
  });
});
