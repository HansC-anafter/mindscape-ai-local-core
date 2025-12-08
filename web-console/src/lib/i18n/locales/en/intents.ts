/**
 * intents i18n messages (English)
 */
import type { MessageKey } from '../../keys';

export const intentsEn = {

  // Intents
  intents: 'Intent Cards',
  intentsDescription: 'Track your long-term goals and projects',
  intentTitle: 'Title',
  intentDescription: 'Description',
  intentStatus: 'Status',
  intentPriority: 'Priority',
  intentProgress: 'Progress',
  intentTags: 'Tags',
  intentCategory: 'Category',
  intentDueDate: 'Due Date',
  newIntent: 'New Intent Card',
  editIntent: 'Edit Intent Card',

} as const satisfies Partial<Record<MessageKey, string>>;
