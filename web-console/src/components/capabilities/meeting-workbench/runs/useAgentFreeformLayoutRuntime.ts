import { useCallback, useState } from 'react';

import {
  DEFAULT_AGENT_FREEFORM_PANELS,
  type AgentFreeformLayoutDecision,
  type AgentFreeformLayoutIntent,
  type AgentFreeformLayoutState,
  type AgentFreeformPanel,
} from './agentFreeformLayoutModel';
import { validateAgentFreeformLayoutIntent } from './agentFreeformLayoutValidator';

function applyPanelIntent(
  panels: AgentFreeformPanel[],
  intent: AgentFreeformLayoutIntent,
): AgentFreeformPanel[] {
  const existing = panels.find((panel) => panel.id === intent.panel_id);
  if (intent.operation === 'close_panel') {
    return existing?.pinned ? panels : panels.filter((panel) => panel.id !== intent.panel_id);
  }
  if (!intent.bounds) return panels;
  const bounds = {
    x: Math.round(intent.bounds.x),
    y: Math.round(intent.bounds.y),
    width: Math.round(intent.bounds.width),
    height: Math.round(intent.bounds.height),
  };
  if (existing) {
    if (existing.pinned && ['move_panel', 'resize_panel', 'close_panel'].includes(intent.operation)) {
      return panels;
    }
    return panels.map((panel) =>
      panel.id === intent.panel_id
        ? {
            ...panel,
            bounds,
            zLayer: intent.z_layer || panel.zLayer,
            collapsed: intent.operation === 'collapse_panel' ? true : intent.operation === 'expand_panel' ? false : panel.collapsed,
            traceEventIds: Array.from(new Set([...panel.traceEventIds, ...(intent.trace_refs || [])])),
          }
        : panel,
    );
  }
  return [
    ...panels,
    {
      id: intent.panel_id,
      type: intent.panel_type || 'timeline',
      title: intent.panel_type || intent.panel_id,
      bounds,
      zLayer: intent.z_layer || 'base',
      traceEventIds: intent.trace_refs || [],
    },
  ];
}

export function useAgentFreeformLayoutRuntime(initialPanels = DEFAULT_AGENT_FREEFORM_PANELS) {
  const [state, setState] = useState<AgentFreeformLayoutState>({
    panels: initialPanels,
    locked: false,
    selectedPanelId: 'composer',
    decisions: [],
  });

  const applyIntent = useCallback((intent: AgentFreeformLayoutIntent): AgentFreeformLayoutDecision => {
    let decision: AgentFreeformLayoutDecision;
    setState((current) => {
      if (current.locked) {
        decision = {
          status: 'rejected',
          intent,
          panel_id: intent.panel_id,
          reason: 'Layout is locked by the user.',
          rule_id: 'layout-locked',
          trace_refs: intent.trace_refs,
        };
        return { ...current, decisions: [...current.decisions, decision] };
      }
      const validation = validateAgentFreeformLayoutIntent(intent, current.panels);
      if (!validation.accepted) {
        decision = {
          status: 'rejected',
          intent,
          panel_id: intent.panel_id,
          reason: validation.reason,
          rule_id: validation.ruleId,
          trace_refs: intent.trace_refs,
        };
        return { ...current, decisions: [...current.decisions, decision] };
      }
      const panels = applyPanelIntent(current.panels, {
        ...intent,
        bounds: validation.normalizedBounds || intent.bounds,
      });
      const existing = current.panels.find((panel) => panel.id === intent.panel_id);
      const overridden = Boolean(existing?.pinned && ['move_panel', 'resize_panel', 'close_panel'].includes(intent.operation));
      decision = {
        status: overridden ? 'overridden' : 'accepted',
        intent,
        panel_id: intent.panel_id,
        reason: overridden ? 'User-pinned panel overrides agent layout intent.' : validation.reason,
        rule_id: overridden ? 'user-pin-priority' : validation.ruleId,
        trace_refs: intent.trace_refs,
      };
      return {
        ...current,
        panels,
        selectedPanelId: intent.panel_id,
        decisions: [...current.decisions, decision],
      };
    });
    return decision!;
  }, []);

  const resetLayout = useCallback(() => {
    setState({
      panels: initialPanels,
      locked: false,
      selectedPanelId: 'composer',
      decisions: [{ status: 'reset', reason: 'Layout reset to default workspace.' }],
    });
  }, [initialPanels]);

  const toggleLocked = useCallback(() => {
    setState((current) => ({
      ...current,
      locked: !current.locked,
      decisions: [
        ...current.decisions,
        {
          status: 'locked',
          reason: !current.locked ? 'Layout locked by the user.' : 'Layout unlocked by the user.',
        },
      ],
    }));
  }, []);

  const selectPanel = useCallback((panelId: string) => {
    setState((current) => ({ ...current, selectedPanelId: panelId }));
  }, []);

  return {
    state,
    applyIntent,
    resetLayout,
    toggleLocked,
    selectPanel,
  };
}
