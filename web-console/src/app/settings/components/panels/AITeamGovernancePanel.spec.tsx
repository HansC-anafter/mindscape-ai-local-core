import '@testing-library/jest-dom/vitest';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { AITeamGovernancePanel, AgentMarketplace, InstalledAgentsList } from './AITeamGovernancePanel';
import { AVAILABLE_AGENTS } from './aiTeamGovernancePanelData';

const panelsDir = dirname(fileURLToPath(import.meta.url));
const touchedFiles = [
  'AITeamGovernancePanel.tsx',
  'AITeamGovernancePanel.spec.tsx',
  'aiTeamGovernanceAgentSections.tsx',
  'aiTeamGovernancePanelData.ts',
  'aiTeamGovernancePanelTypes.ts',
  'aiTeamGovernancePolicySections.tsx',
];

function readPanelFile(pathFromPanels: string): string {
  return readFileSync(join(panelsDir, pathFromPanels), 'utf8');
}

describe('AITeamGovernancePanel seams', () => {
  it('routes each settings section through the public facade', () => {
    const { rerender } = render(<AITeamGovernancePanel activeSection="install-agents" />);
    expect(screen.getByText('Mindscape Core')).toBeInTheDocument();

    rerender(<AITeamGovernancePanel activeSection="installed-agents" />);
    expect(screen.getByText('OpenClaw')).toBeInTheDocument();
    expect(screen.getByText('Running')).toBeInTheDocument();

    rerender(<AITeamGovernancePanel activeSection="model-policy" />);
    expect(screen.getByText('Local-only mode is enabled')).toBeInTheDocument();

    rerender(<AITeamGovernancePanel activeSection="network-policy" />);
    expect(screen.getByDisplayValue('')).toBeInTheDocument();

    rerender(<AITeamGovernancePanel activeSection="secrets-policy" />);
    expect(screen.getByText('Security Notice')).toBeInTheDocument();
    expect(screen.getByText('Isolated Mode')).toBeInTheDocument();
  });

  it('preserves exported section components and static agent data', () => {
    const marketplace = render(<AgentMarketplace />);
    expect(screen.getByText('AutoGPT')).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: 'Install' })).toHaveLength(4);
    marketplace.unmount();

    render(<InstalledAgentsList />);
    expect(screen.getByText('OpenClaw')).toBeInTheDocument();

    expect(AVAILABLE_AGENTS.map(agent => agent.id)).toEqual([
      'mindscape-core',
      'openclaw',
      'langgraph',
      'crewai',
      'autogpt',
      'open-interpreter',
      'claude-computer-use',
    ]);
  });

  it('keeps assistant handoff messages on available and installed agents', () => {
    const onSendToAssistant = vi.fn();
    render(<AITeamGovernancePanel activeSection="install-agents" onSendToAssistant={onSendToAssistant} />);

    fireEvent.click(screen.getAllByRole('button', { name: 'Install' })[0]);
    expect(onSendToAssistant).toHaveBeenCalledWith('Help me install LangGraph');

    fireEvent.click(screen.getByRole('button', { name: 'Configure' }));
    expect(onSendToAssistant).toHaveBeenCalledWith('Help me configure OpenClaw');
  });

  it('preserves model, network, and secrets local state behavior', () => {
    const { rerender } = render(<AITeamGovernancePanel activeSection="model-policy" />);
    expect(screen.getByText('Local-only mode is enabled')).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole('checkbox')[2]);
    expect(screen.queryByText('Local-only mode is enabled')).not.toBeInTheDocument();

    rerender(<AITeamGovernancePanel activeSection="network-policy" />);
    const hostInput = screen.getByPlaceholderText('Example: api.example.com');
    fireEvent.change(hostInput, { target: { value: 'api.example.com' } });
    fireEvent.click(screen.getByRole('button', { name: 'Add' }));
    expect(screen.getByText('api.example.com')).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole('button', { name: 'Remove' })[0]);
    expect(screen.queryByText('pypi.org')).not.toBeInTheDocument();

    rerender(<AITeamGovernancePanel activeSection="secrets-policy" />);
    expect(screen.getByText('Isolated Mode')).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole('checkbox')[0]);
    expect(screen.queryByText('Isolated Mode')).not.toBeInTheDocument();
  });

  it('keeps touched files under the large-file gate', () => {
    const lineCounts = Object.fromEntries(
      touchedFiles.map(file => [
        file,
        readPanelFile(file).split(/\r?\n/).length,
      ]),
    );

    expect(lineCounts['AITeamGovernancePanel.tsx']).toBeLessThan(120);
    expect(Object.values(lineCounts).every(count => count <= 500)).toBe(true);
  });

  it('does not add executable runtime resource owners', () => {
    const markers = [
      'fe' + 'tch',
      '/a' + 'pi/',
      'set' + 'Interval',
      'set' + 'Timeout',
      'poll' + 'ing',
      'Web' + 'Socket',
      'Event' + 'Source',
      'local' + 'Storage',
      'session' + 'Storage',
      'Abort' + 'Controller',
      'http' + 'x',
      're' + 'quests',
      'pg' + 'bouncer',
      'work' + 'er',
      'qu' + 'eue',
    ];
    const hits: Record<string, string[]> = {};
    for (const file of touchedFiles) {
      const text = readPanelFile(file);
      const found = markers.filter(marker => text.includes(marker));
      if (found.length > 0) {
        hits[file] = found;
      }
    }

    expect(hits).toEqual({});
  });
});
