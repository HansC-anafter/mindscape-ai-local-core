import { describe, expect, it } from 'vitest';

import { DEFAULT_AGENT_FREEFORM_PANELS } from './agentFreeformLayoutModel';
import { validateAgentFreeformLayoutIntent } from './agentFreeformLayoutValidator';

describe('agentFreeformLayoutValidator', () => {
  it('rejects direct DOM or CSS mutation requests', () => {
    const result = validateAgentFreeformLayoutIntent(
      {
        operation: 'place_panel',
        panel_id: 'bad',
        panel_type: 'timeline',
        bounds: { x: 10, y: 10, width: 300, height: 200 },
        reason: 'try raw css',
        raw_css: '.app { display: none }',
      },
      DEFAULT_AGENT_FREEFORM_PANELS,
    );

    expect(result.accepted).toBe(false);
    expect(result.ruleId).toBe('no-direct-dom-or-css');
  });

  it('rejects panels that would cover the command bar protected zone', () => {
    const result = validateAgentFreeformLayoutIntent(
      {
        operation: 'place_panel',
        panel_id: 'too-low',
        panel_type: 'timeline',
        bounds: { x: 20, y: 600, width: 300, height: 160 },
        reason: 'cover command bar',
      },
      DEFAULT_AGENT_FREEFORM_PANELS,
    );

    expect(result.accepted).toBe(false);
    expect(result.ruleId).toBe('command-bar-protected-zone');
  });

  it('accepts normalized in-bounds panel placement', () => {
    const result = validateAgentFreeformLayoutIntent(
      {
        operation: 'place_panel',
        panel_id: 'tools',
        panel_type: 'tool_calls',
        bounds: { x: 740.2, y: 240.7, width: 300.4, height: 220.8 },
        z_layer: 'raised',
        reason: 'show tool calls',
      },
      DEFAULT_AGENT_FREEFORM_PANELS,
    );

    expect(result.accepted).toBe(true);
    expect(result.normalizedBounds).toEqual({ x: 740, y: 241, width: 300, height: 221 });
  });
});
