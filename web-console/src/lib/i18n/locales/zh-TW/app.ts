/**
 * app i18n messages (Traditional Chinese)
 */
import type { MessageKey } from '../../keys';

export const appZhTW = {

  // App
  appName: 'Mindscape AI',
  appSubtitle: '個人 AI 團隊工作台',
  appWorkstation: 'Mindscape AI 工作站',
  appCoreConcept: '心智空間：存你這個人的脈絡 | Playbooks：存你覺得「值得反覆使用」的做事方法',

} as const satisfies Partial<Record<MessageKey, string>>;
