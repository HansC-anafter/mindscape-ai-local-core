'use client';

import CapabilityStaticLoadedComponents, {
  type StaticCapabilityUiHostProps,
} from '../CapabilityStaticLoadedComponents';
import * as ArtifactDisplayModule0 from '@/app/capabilities/web_generation/components/ArtifactDisplay';
import * as CheckpointTrayModule1 from '@/app/capabilities/web_generation/components/CheckpointTray';
import * as ContextSourcesModule2 from '@/app/capabilities/web_generation/components/ContextSources';
import * as ControlKnobsModule3 from '@/app/capabilities/web_generation/components/ControlKnobs';
import * as DiffViewerModule4 from '@/app/capabilities/web_generation/components/DiffViewer';
import * as DiviSlotDraftEditorModule5 from '@/app/capabilities/web_generation/components/DiviSlotDraftEditor';
import * as GateCardModule6 from '@/app/capabilities/web_generation/components/GateCard';
import * as IntentInputBarModule7 from '@/app/capabilities/web_generation/components/IntentInputBar';
import * as OutcomeCardsModule8 from '@/app/capabilities/web_generation/components/OutcomeCards';
import * as PlanPreviewCardModule9 from '@/app/capabilities/web_generation/components/PlanPreviewCard';
import * as RunCostSummaryModule10 from '@/app/capabilities/web_generation/components/RunCostSummary';
import * as RunStepCardModule11 from '@/app/capabilities/web_generation/components/RunStepCard';
import * as RunTimelineModule12 from '@/app/capabilities/web_generation/components/RunTimeline';
import * as SiteBindingPillModule13 from '@/app/capabilities/web_generation/components/SiteBindingPill';
import * as StudiosLauncherModule14 from '@/app/capabilities/web_generation/components/StudiosLauncher';
import * as ThreadBundlePanelModule15 from '@/app/capabilities/web_generation/components/ThreadBundlePanel';
import * as ThreadHeaderModule16 from '@/app/capabilities/web_generation/components/ThreadHeader';
import * as ThreadListPanelModule17 from '@/app/capabilities/web_generation/components/ThreadListPanel';
import * as ThreadsPanelModule18 from '@/app/capabilities/web_generation/components/ThreadsPanel';
import * as WebGenExecutionPanelModule19 from '@/app/capabilities/web_generation/components/WebGenExecutionPanel';
import * as WebGenerationContextBarModule20 from '@/app/capabilities/web_generation/components/WebGenerationContextBar';
import * as WebGenerationWorkbenchPageModule21 from '@/app/capabilities/web_generation/components/WebGenerationWorkbenchPage';
import * as WordPressSitesPanelModule22 from '@/app/capabilities/web_generation/components/WordPressSitesPanel';
import * as WorkspaceCanvasModule23 from '@/app/capabilities/web_generation/components/WorkspaceCanvas';

const componentModules: Record<string, Record<string, unknown>> = {
  "ArtifactDisplay": ArtifactDisplayModule0 as Record<string, unknown>,
  "CheckpointTray": CheckpointTrayModule1 as Record<string, unknown>,
  "ContextSources": ContextSourcesModule2 as Record<string, unknown>,
  "ControlKnobs": ControlKnobsModule3 as Record<string, unknown>,
  "DiffViewer": DiffViewerModule4 as Record<string, unknown>,
  "DiviSlotDraftEditor": DiviSlotDraftEditorModule5 as Record<string, unknown>,
  "GateCard": GateCardModule6 as Record<string, unknown>,
  "IntentInputBar": IntentInputBarModule7 as Record<string, unknown>,
  "OutcomeCards": OutcomeCardsModule8 as Record<string, unknown>,
  "PlanPreviewCard": PlanPreviewCardModule9 as Record<string, unknown>,
  "RunCostSummary": RunCostSummaryModule10 as Record<string, unknown>,
  "RunStepCard": RunStepCardModule11 as Record<string, unknown>,
  "RunTimeline": RunTimelineModule12 as Record<string, unknown>,
  "SiteBindingPill": SiteBindingPillModule13 as Record<string, unknown>,
  "StudiosLauncher": StudiosLauncherModule14 as Record<string, unknown>,
  "ThreadBundlePanel": ThreadBundlePanelModule15 as Record<string, unknown>,
  "ThreadHeader": ThreadHeaderModule16 as Record<string, unknown>,
  "ThreadListPanel": ThreadListPanelModule17 as Record<string, unknown>,
  "ThreadsPanel": ThreadsPanelModule18 as Record<string, unknown>,
  "WebGenExecutionPanel": WebGenExecutionPanelModule19 as Record<string, unknown>,
  "WebGenerationContextBar": WebGenerationContextBarModule20 as Record<string, unknown>,
  "WebGenerationWorkbenchPage": WebGenerationWorkbenchPageModule21 as Record<string, unknown>,
  "WordPressSitesPanel": WordPressSitesPanelModule22 as Record<string, unknown>,
  "WorkspaceCanvas": WorkspaceCanvasModule23 as Record<string, unknown>,
};

export default function WebGenerationCapabilityUiHost(props: StaticCapabilityUiHostProps) {
  return (
    <CapabilityStaticLoadedComponents
      {...props}
      componentModules={componentModules}
    />
  );
}
