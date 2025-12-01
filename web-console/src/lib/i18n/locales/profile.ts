/**
 * Profile i18n messages
 * User profile and preferences
 */
import type { MessageKey } from '../keys';

export const profileZhTW = {
  // Profile
  profile: '自我設定',
  profileDescription: '定義你是誰、你的角色與偏好',
  name: '姓名',
  email: '電子郵件',
  roles: '角色',
  domains: '專業領域',
  preferences: '偏好設定',
  communicationStyle: '溝通風格',
  responseLength: '回應長度',
  language: '語言',
} as const satisfies Partial<Record<MessageKey, string>>;

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
