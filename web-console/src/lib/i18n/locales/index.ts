/**
 * Aggregated i18n messages
 * Combines all locale modules into a single messages object
 */

import { keys } from '../keys';
import type { MessageKey } from '../keys';
import { commonZhTW, commonEn } from './common';
import { appZhTW, appEn } from './app';
import { navigationZhTW, navigationEn } from './navigation';
import { commonJa } from './ja/common';
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
import { mindscapeZhTW, mindscapeEn } from './mindscape';
import { playbooksZhTW, playbooksEn, playbooksJa } from './playbooks';
import { profileZhTW, profileEn } from './profile';
import { intentsZhTW, intentsEn } from './intents';
import { timelineZhTW, timelineEn } from './timeline';
import { reviewZhTW, reviewEn } from './review';
import { habitZhTW, habitEn } from './habit';
import { majorProposalZhTW, majorProposalEn } from './majorProposal';
import { agentsZhTW, agentsEn } from './agents';
import { settingsZhTW, settingsEn } from './settings';
import { workbenchZhTW, workbenchEn } from './workbench';
import { systemZhTW, systemEn } from './system';
import { executionZhTW } from './zh-TW/execution';
import { executionEn } from './en/execution';
import { executionJa } from './ja/execution';

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
