export function shortId(value: string | null | undefined): string {
  if (!value) {
    return 'none';
  }

  if (value.length <= 18) {
    return value;
  }

  return `${value.slice(0, 8)}...${value.slice(-6)}`;
}

export function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

export function readString(value: unknown): string {
  return typeof value === 'string' ? value : '';
}

export function safeMentionId(value: string): string {
  return value.replace(/[^a-zA-Z0-9_-]/g, '_');
}
