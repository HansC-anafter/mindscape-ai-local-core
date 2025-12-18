/**
 * Aggregated i18n messages
 * Combines all locale modules into a single messages object
 */

import { keys } from '../keys';
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

/**
 * Merge multiple message objects into one
 * Uses Object.assign to combine all message objects
 */
function mergeMessages(...objects: Array<Record<string, string>>): Record<string, string> {
  return Object.assign({}, ...objects);
}

/**
 * Aggregate all zh-TW messages
 */
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

/**
 * Aggregate all en messages
 */
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

/**
 * Aggregate all ja messages
 */
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

/**
 * Type-safe message bundles
 */
export type MessageBundles = typeof messages;

/**
 * MessageKey type derived from centralized keys.ts
 * Re-exported for use in modules and components
 */
export type { MessageKey };

/**
 * Validate that both locales have the same keys
 * Also validates against centralized keys.ts
 */
function validateKeyParity(zhTW: Record<string, any>, en: Record<string, any>): void {
  const zhTWKeys = new Set(Object.keys(zhTW));
  const enKeys = new Set(Object.keys(en));

  const missingInEn = Array.from(zhTWKeys).filter(key => !enKeys.has(key));
  const missingInZhTW = Array.from(enKeys).filter(key => !zhTWKeys.has(key));

  if (missingInEn.length > 0 || missingInZhTW.length > 0) {
    console.warn('i18n key parity check failed:');
    if (missingInEn.length > 0) {
      console.warn(`Missing in en: ${missingInEn.join(', ')}`);
    }
    if (missingInZhTW.length > 0) {
      console.warn(`Missing in zh-TW: ${missingInZhTW.join(', ')}`);
    }
  }

  // Validate against centralized keys.ts
  try {
    const centralizedKeySet = new Set(Object.keys(keys));
    const missingInCentralized = Array.from(zhTWKeys).filter(key => !centralizedKeySet.has(key));
    const extraInCentralized = Array.from(centralizedKeySet).filter(key => !zhTWKeys.has(key) && !enKeys.has(key));

    if (missingInCentralized.length > 0 || extraInCentralized.length > 0) {
      console.warn('i18n key validation against keys.ts:');
      if (missingInCentralized.length > 0) {
        console.warn(`Keys in locales but not in keys.ts: ${missingInCentralized.join(', ')}`);
      }
      if (extraInCentralized.length > 0) {
        console.warn(`Keys in keys.ts but not in locales: ${extraInCentralized.join(', ')}`);
      }
    }
  } catch {
    // keys.ts might not be available in all environments, ignore
  }
}

// Validate key parity in development
if (process.env.NODE_ENV === 'development') {
  validateKeyParity(mergeZhTW, mergeEn);
}

/**
 * Final aggregated messages object
 */
export const messages = {
  'zh-TW': mergeZhTW,
  en: mergeEn,
  ja: mergeJa,
} as const;
