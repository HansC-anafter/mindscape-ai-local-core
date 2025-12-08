/**
 * Centralized i18n message keys index
 * Aggregates all module keys into a single export
 */

import { commonKeys } from './common';
import { appKeys } from './app';
import { navigationKeys } from './navigation';
import { agentsKeys } from './agents';
import { playbooksKeys } from './playbooks';
import { mindscapeKeys } from './mindscape';
import { intentsKeys } from './intents';
import { settingsKeys } from './settings';
import { systemKeys } from './system';
import { toolsKeys } from './tools';
import { workspaceKeys } from './workspace';
import { executionKeys } from './execution';
import { timelineKeys } from './timeline';
import { profileKeys } from './profile';
import { habitKeys } from './habit';
import { reviewKeys } from './review';
import { majorProposalKeys } from './majorProposal';
import { workbenchKeys } from './workbench';
import { oauthKeys } from './oauth';
import { integrationsKeys } from './integrations';
import { cloudKeys } from './cloud';
import { capabilityPacksKeys } from './capabilityPacks';
import { resourceBindingKeys } from './resourceBinding';
import { playbookVariantsKeys } from './playbookVariants';

/**
 * All i18n message keys
 * Merged from all modules
 */
export const keys = {
  ...commonKeys,
  ...appKeys,
  ...navigationKeys,
  ...agentsKeys,
  ...playbooksKeys,
  ...mindscapeKeys,
  ...intentsKeys,
  ...settingsKeys,
  ...systemKeys,
  ...toolsKeys,
  ...workspaceKeys,
  ...executionKeys,
  ...timelineKeys,
  ...profileKeys,
  ...habitKeys,
  ...reviewKeys,
  ...majorProposalKeys,
  ...workbenchKeys,
  ...oauthKeys,
  ...integrationsKeys,
  ...cloudKeys,
  ...capabilityPacksKeys,
  ...resourceBindingKeys,
  ...playbookVariantsKeys,
} as const;

export type MessageKey = keyof typeof keys;

