import type { MessageKey } from '../keys';
import { playbooksZhTW } from './playbooks/zh-TW';
import { playbooksEn } from './playbooks/en';
import { playbooksJa } from './playbooks/ja';

export { playbooksZhTW, playbooksEn, playbooksJa };

import { playbookMetadataZhTW, playbookMetadataEn, playbookMetadataJa } from './playbooks/metadata';

export { playbookMetadataZhTW, playbookMetadataEn, playbookMetadataJa };

export function getPlaybookMetadata(
  playbookCode: string,
  field: 'name' | 'description' | 'tags',
  locale: 'zh-TW' | 'en' | 'ja' = 'zh-TW'
): string | string[] | undefined {
  const metadata =
    locale === 'zh-TW' ? playbookMetadataZhTW :
    locale === 'en' ? playbookMetadataEn :
    playbookMetadataJa;
  const playbook = metadata[playbookCode as keyof typeof metadata];
  if (!playbook) return undefined;
  const value = playbook[field];
  if (field === 'tags' && Array.isArray(value)) {
    return value;
  }
  return typeof value === 'string' ? value : (value ? String(value) : undefined);
}
