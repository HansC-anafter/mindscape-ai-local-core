/**
 * profile i18n messages (English)
 */
import type { MessageKey } from '../../keys';

export const profileEn = {

  // Profile
  profile: 'Profile',
  profileDescription: 'Define who you are, your roles, and preferences',
  name: 'Name',
  email: 'Email',
  roles: 'Roles',
  domains: 'Domains',
  preferences: 'Preferences',
  communicationStyle: 'Communication Style',
  responseLength: 'Response Length',
  language: 'Language',

} as const satisfies Partial<Record<MessageKey, string>>;
