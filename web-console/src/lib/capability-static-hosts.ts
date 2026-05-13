export type CapabilityWorkbenchSearchParams =
  | URLSearchParams
  | Record<string, string | string[] | undefined>;

export interface CapabilityWorkbenchPathOptions {
  surfacePath?: readonly string[];
  searchParams?: CapabilityWorkbenchSearchParams;
}

function assertRawSegment(label: string, value: string): void {
  if (!value.trim()) {
    throw new Error(`${label} must be a non-empty raw segment`);
  }
  if (value.includes('/')) {
    throw new Error(`${label} must not contain "/"`);
  }
}

function encodeSearchParams(searchParams?: CapabilityWorkbenchSearchParams): string {
  if (!searchParams) {
    return '';
  }

  const params = new URLSearchParams();
  if (searchParams instanceof URLSearchParams) {
    searchParams.forEach((value, key) => {
      params.append(key, value);
    });
  } else {
    for (const [key, value] of Object.entries(searchParams)) {
      if (Array.isArray(value)) {
        for (const item of value) {
          params.append(key, item);
        }
      } else if (typeof value === 'string') {
        params.set(key, value);
      }
    }
  }

  const encoded = params.toString();
  return encoded ? `?${encoded}` : '';
}

export function buildCapabilityWorkbenchPath(
  workspaceId: string,
  capabilityCode: string,
  options: CapabilityWorkbenchPathOptions = {},
): string {
  const normalizedWorkspaceId = String(workspaceId || '').trim();
  const normalizedCapabilityCode = String(capabilityCode || '').trim();

  assertRawSegment('workspaceId', normalizedWorkspaceId);
  assertRawSegment('capabilityCode', normalizedCapabilityCode);

  const surfaceSegments = options.surfacePath || [];
  for (const [index, segment] of surfaceSegments.entries()) {
    assertRawSegment(`surfacePath[${index}]`, String(segment || ''));
  }

  const encodedSurfacePath = surfaceSegments
    .map((segment) => encodeURIComponent(segment))
    .join('/');
  const path = [
    '/workspaces',
    encodeURIComponent(normalizedWorkspaceId),
    'capability-ui-hosts',
    encodeURIComponent(normalizedCapabilityCode),
    encodedSurfacePath,
  ].filter(Boolean).join('/');

  return `${path}${encodeSearchParams(options.searchParams)}`;
}
