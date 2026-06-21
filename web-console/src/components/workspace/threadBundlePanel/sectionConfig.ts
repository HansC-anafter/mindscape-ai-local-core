import type {
  BundleSection,
  ThreadReferenceSourceOption,
} from './types';

export const bundleSections: readonly BundleSection[] = [
  'overview',
  'deliverables',
  'references',
  'runs',
  'sources',
];

export const sectionLabels: Record<BundleSection, string> = {
  overview: 'Overview',
  deliverables: 'Deliverables',
  references: 'References',
  runs: 'Runs',
  sources: 'Sources',
};

export const referenceSourceTypes: ThreadReferenceSourceOption[] = [
  { value: 'url', label: 'URL' },
  { value: 'local_file', label: 'Local File' },
  { value: 'obsidian', label: 'Obsidian Note' },
  { value: 'notion', label: 'Notion Page' },
  { value: 'wordpress', label: 'WordPress Article' },
  { value: 'google_drive', label: 'Google Drive' },
];

export function cn(...classes: (string | undefined | null | false)[]): string {
  return classes.filter(Boolean).join(' ');
}
