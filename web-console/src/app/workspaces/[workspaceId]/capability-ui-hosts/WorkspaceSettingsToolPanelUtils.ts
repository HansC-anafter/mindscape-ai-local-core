export function formatList(values: unknown): string {
  if (!Array.isArray(values) || values.length === 0) {
    return '';
  }
  return values.filter((value): value is string => typeof value === 'string' && value.trim().length > 0).join(', ');
}

export function parseList(value: string): string[] {
  return value
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);
}
