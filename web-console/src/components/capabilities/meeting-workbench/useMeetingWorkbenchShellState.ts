import { useState, type Dispatch, type SetStateAction } from 'react';

import type { MeetingMissingContext } from './meetingWorkbenchStatus';
import type {
  GraphViewMode,
  InspectorTab,
  MeetingInfoPanel,
  MeetingMentionItem,
  MeetingNode,
} from './meetingWorkbenchTypes';

export interface MeetingWorkbenchShellState {
  selectedNodeId: string;
  setSelectedNodeId: Dispatch<SetStateAction<string>>;
  activeInspector: InspectorTab | null;
  setActiveInspector: Dispatch<SetStateAction<InspectorTab | null>>;
  activeInfoPanel: MeetingInfoPanel | null;
  setActiveInfoPanel: Dispatch<SetStateAction<MeetingInfoPanel | null>>;
  graphViewMode: GraphViewMode;
  setGraphViewMode: Dispatch<SetStateAction<GraphViewMode>>;
  activeTraceFilter: string | null;
  setActiveTraceFilter: Dispatch<SetStateAction<string | null>>;
  isConsoleOpen: boolean;
  setIsConsoleOpen: Dispatch<SetStateAction<boolean>>;
  command: string;
  setCommand: Dispatch<SetStateAction<string>>;
  localTasks: MeetingNode[];
  setLocalTasks: Dispatch<SetStateAction<MeetingNode[]>>;
  dispatchError: string | null;
  setDispatchError: Dispatch<SetStateAction<string | null>>;
  canvasZoom: number;
  setCanvasZoom: Dispatch<SetStateAction<number>>;
  selectedPackToolId: string;
  setSelectedPackToolId: Dispatch<SetStateAction<string>>;
  appliedMentionItems: MeetingMentionItem[];
  setAppliedMentionItems: Dispatch<SetStateAction<MeetingMentionItem[]>>;
  isDispatching: boolean;
  setIsDispatching: Dispatch<SetStateAction<boolean>>;
  activeMissingContext: MeetingMissingContext | null;
  setActiveMissingContext: Dispatch<SetStateAction<MeetingMissingContext | null>>;
}

export function useMeetingWorkbenchShellState(): MeetingWorkbenchShellState {
  const [selectedNodeId, setSelectedNodeId] = useState('ready');
  const [activeInspector, setActiveInspector] = useState<InspectorTab | null>(null);
  const [activeInfoPanel, setActiveInfoPanel] = useState<MeetingInfoPanel | null>(null);
  const [graphViewMode, setGraphViewMode] = useState<GraphViewMode>('runs');
  const [activeTraceFilter, setActiveTraceFilter] = useState<string | null>(null);
  const [isConsoleOpen, setIsConsoleOpen] = useState(false);
  const [command, setCommand] = useState('');
  const [localTasks, setLocalTasks] = useState<MeetingNode[]>([]);
  const [dispatchError, setDispatchError] = useState<string | null>(null);
  const [canvasZoom, setCanvasZoom] = useState(1);
  const [selectedPackToolId, setSelectedPackToolId] = useState('auto');
  const [appliedMentionItems, setAppliedMentionItems] = useState<MeetingMentionItem[]>([]);
  const [isDispatching, setIsDispatching] = useState(false);
  const [activeMissingContext, setActiveMissingContext] = useState<MeetingMissingContext | null>(null);

  return {
    selectedNodeId,
    setSelectedNodeId,
    activeInspector,
    setActiveInspector,
    activeInfoPanel,
    setActiveInfoPanel,
    graphViewMode,
    setGraphViewMode,
    activeTraceFilter,
    setActiveTraceFilter,
    isConsoleOpen,
    setIsConsoleOpen,
    command,
    setCommand,
    localTasks,
    setLocalTasks,
    dispatchError,
    setDispatchError,
    canvasZoom,
    setCanvasZoom,
    selectedPackToolId,
    setSelectedPackToolId,
    appliedMentionItems,
    setAppliedMentionItems,
    isDispatching,
    setIsDispatching,
    activeMissingContext,
    setActiveMissingContext,
  };
}
