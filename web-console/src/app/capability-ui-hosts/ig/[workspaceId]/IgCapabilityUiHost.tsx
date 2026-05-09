'use client';

import CapabilityStaticLoadedComponents, {
  type StaticCapabilityUiHostProps,
} from '@/app/workspaces/[workspaceId]/capability-ui-hosts/CapabilityStaticLoadedComponents';
import * as IGFollowingAnalyzerModule0 from '@/app/capabilities/ig/components/IGFollowingAnalyzer';
import * as IGGridViewModule1 from '@/app/capabilities/ig/components/IGGridView';
import * as IGGridViewModalModule2 from '@/app/capabilities/ig/components/IGGridViewModal';
import * as IGPostCardModule3 from '@/app/capabilities/ig/components/IGPostCard';
import * as IGTimelineViewModule4 from '@/app/capabilities/ig/components/IGTimelineView';
import * as IGWorkbenchModule5 from '@/app/capabilities/ig/components/IGWorkbench';
import * as ReadyScoreModule6 from '@/app/capabilities/ig/components/ReadyScore';

const componentModules: Record<string, Record<string, unknown>> = {
  IGFollowingAnalyzer: IGFollowingAnalyzerModule0 as Record<string, unknown>,
  IGGridView: IGGridViewModule1 as Record<string, unknown>,
  IGGridViewModal: IGGridViewModalModule2 as Record<string, unknown>,
  IGPostCard: IGPostCardModule3 as Record<string, unknown>,
  IGTimelineView: IGTimelineViewModule4 as Record<string, unknown>,
  IGWorkbench: IGWorkbenchModule5 as Record<string, unknown>,
  ReadyScore: ReadyScoreModule6 as Record<string, unknown>,
};

export default function IgCapabilityUiHost(props: StaticCapabilityUiHostProps) {
  return (
    <CapabilityStaticLoadedComponents
      {...props}
      componentModules={componentModules}
    />
  );
}
