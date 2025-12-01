/**
 * Profile i18n messages (Japanese)
 * User profile and preferences
 */
import type { MessageKey } from '../../keys';

export const profileJa = {
  // Profile
  profile: 'プロフィール',
  profileDescription: 'あなたが誰か、あなたの役割と好みを定義',
  name: '名前',
  email: 'メールアドレス',
  roles: '役割',
  domains: '専門分野',
  preferences: '好み設定',
  communicationStyle: 'コミュニケーションスタイル',
  responseLength: '応答の長さ',
  language: '言語',
} as const satisfies Partial<Record<MessageKey, string>>;

