/**
 * app i18n messages (English)
 */
import type { MessageKey } from '../../keys';

export const appEn = {

  // App
  appName: 'Mindscape AI',
  appSubtitle: 'Personal AI Team Console',
  appWorkstation: 'Mindscape AI Workstation',
  appCoreConcept: 'Mindscape: Store your personal context | Playbooks: Store your "worth reusing" workflows',

} as const satisfies Partial<Record<MessageKey, string>>;
