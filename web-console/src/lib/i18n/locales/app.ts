import type { MessageKey } from '../keys';

export const appZhTW = {
  appName: 'Mindscape AI',
  appSubtitle: '個人 AI 團隊工作台',
  appWorkstation: 'Mindscape AI 工作站',
  appCoreConcept: '心智空間：存你這個人的脈絡 | Playbooks：存你覺得「值得反覆使用」的做事方法',
} as const satisfies Partial<Record<MessageKey, string>>;

export const appEn = {
  appName: 'Mindscape AI',
  appSubtitle: 'Personal AI Team Console',
  appWorkstation: 'Mindscape AI Workstation',
  appCoreConcept: 'Mindscape: Store your personal context | Playbooks: Store your "worth reusing" workflows',
} as const satisfies Partial<Record<MessageKey, string>>;
