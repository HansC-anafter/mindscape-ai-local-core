import type { MessageKey } from '../keys';
import { commonZhTW } from './zh-TW/common';
import { commonEn } from './en/common';
import { commonJa } from './ja/common';
import { appZhTW } from './zh-TW/app';
import { appEn } from './en/app';
import { navigationZhTW } from './zh-TW/navigation';
import { navigationEn } from './en/navigation';
import { appJa } from './ja/app';
import { navigationJa } from './ja/navigation';
import { workbenchJa } from './ja/workbench';
import { timelineJa } from './ja/timeline';
import { systemJa } from './ja/system';
import { settingsJa } from './ja/settings';
import { mindscapeJa } from './ja/mindscape';
import { profileJa } from './ja/profile';
import { intentsJa } from './ja/intents';
import { reviewJa } from './ja/review';
import { habitJa } from './ja/habit';
import { majorProposalJa } from './ja/majorProposal';
import { agentsJa } from './ja/agents';
import { mindscapeZhTW } from './zh-TW/mindscape';
import { mindscapeEn } from './en/mindscape';
import { playbooksZhTW, playbooksEn, playbooksJa } from './playbooks';
import { profileZhTW } from './zh-TW/profile';
import { profileEn } from './en/profile';
import { intentsZhTW } from './zh-TW/intents';
import { intentsEn } from './en/intents';
import { timelineZhTW } from './zh-TW/timeline';
import { timelineEn } from './en/timeline';
import { reviewZhTW } from './zh-TW/review';
import { reviewEn } from './en/review';
import { habitZhTW } from './zh-TW/habit';
import { habitEn } from './en/habit';
import { majorProposalZhTW } from './zh-TW/majorProposal';
import { majorProposalEn } from './en/majorProposal';
import { agentsZhTW } from './zh-TW/agents';
import { agentsEn } from './en/agents';
import { settingsZhTW } from './zh-TW/settings';
import { settingsEn } from './en/settings';
import { workbenchZhTW } from './zh-TW/workbench';
import { workbenchEn } from './en/workbench';
import { systemZhTW } from './zh-TW/system';
import { systemEn } from './en/system';
import { executionZhTW } from './zh-TW/execution';
import { executionEn } from './en/execution';
import { executionJa } from './ja/execution';
import { workspaceZhTW } from './zh-TW/workspace';
import { workspaceEn } from './en/workspace';
import { workspaceJa } from './ja/workspace';

function mergeMessages(...objects: Array<Record<string, string>>): Record<string, string> {
  return Object.assign({}, ...objects);
}

const mergeZhTW = {
  ...commonZhTW,
  ...appZhTW,
  ...navigationZhTW,
  ...mindscapeZhTW,
  ...playbooksZhTW,
  ...profileZhTW,
  ...intentsZhTW,
  ...timelineZhTW,
  ...reviewZhTW,
  ...habitZhTW,
  ...majorProposalZhTW,
  ...agentsZhTW,
  ...settingsZhTW,
  ...workbenchZhTW,
  ...systemZhTW,
  ...executionZhTW,
  ...workspaceZhTW,
} as const;

const mergeEn = {
  ...commonEn,
  ...appEn,
  ...navigationEn,
  ...mindscapeEn,
  ...playbooksEn,
  ...profileEn,
  ...intentsEn,
  ...timelineEn,
  ...reviewEn,
  ...habitEn,
  ...majorProposalEn,
  ...agentsEn,
  ...settingsEn,
  ...workbenchEn,
  ...systemEn,
  ...executionEn,
  ...workspaceEn,
} as const;

const mergeJa = {
  ...commonJa,
  ...appJa,
  ...navigationJa,
  ...mindscapeJa,
  ...playbooksJa,
  ...profileJa,
  ...intentsJa,
  ...timelineJa,
  ...reviewJa,
  ...habitJa,
  ...majorProposalJa,
  ...agentsJa,
  ...settingsJa,
  ...workbenchJa,
  ...systemJa,
  ...executionJa,
  ...workspaceJa,
} as const;

function sourceAlignedCatalog(
  overrides: Record<string, string>,
): Record<keyof typeof mergeEn, string> {
  return Object.fromEntries(
    Object.entries(mergeEn).map(([key, sourceMessage]) => [
      key,
      typeof overrides[key] === 'string' ? overrides[key] : sourceMessage,
    ]),
  ) as Record<keyof typeof mergeEn, string>;
}

export type MessageBundles = typeof messages;

export type { MessageKey };

export const messages = {
  'zh-TW': sourceAlignedCatalog(mergeZhTW),
  en: mergeEn,
  ja: sourceAlignedCatalog(mergeJa),
} as const;
