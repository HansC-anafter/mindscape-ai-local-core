import type React from 'react';
import { describe, expect, it } from 'vitest';
import { FileOutput, Wrench } from 'lucide-react';

import type { WorkspaceToolDefinition } from '@/lib/workspace-tools/workspace-tool-registry';
import { iconForTool } from './packScopeToolRailModel';

const baseTool: WorkspaceToolDefinition = {
  tool_key: 'ig:official_outputs',
  capability_code: 'ig',
  id: 'official_outputs',
  group: 'capability',
  slot: 'workbench.left_tool_rail',
  label: 'Outputs',
  icon: 'FileOutput',
  order: 40,
  panel_component_code: 'IGOfficialOutputsToolPanel',
  panel_component: {
    code: 'IGOfficialOutputsToolPanel',
    path: 'ui/workbench/officialArtifacts/IGOfficialOutputsToolPanel.tsx',
    description: 'Official IG generated post outputs for the pack-scope tool rail',
    export: 'default',
    artifact_types: [],
    playbook_codes: [],
    import_path: '@/app/capabilities/ig/components/IGOfficialOutputsToolPanel',
    layout_hint: 'default',
  },
};

describe('packScopeToolRailModel iconForTool', () => {
  it('renders FileOutput for generated output tools', () => {
    const icon = iconForTool(baseTool) as React.ReactElement;

    expect(icon.type).toBe(FileOutput);
  });

  it('falls back to Wrench for unknown manifest icons', () => {
    const icon = iconForTool({ ...baseTool, icon: 'UnknownIcon' }) as React.ReactElement;

    expect(icon.type).toBe(Wrench);
  });
});
