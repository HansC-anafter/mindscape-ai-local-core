const CAPABILITY_PATH_MARKER = 'app/capabilities/';

export function normalizeCapabilityContextKey(candidate: string | null): string | null {
  if (!candidate) return null;
  let normalized = candidate.replace(/\\/g, '/');
  const markerIndex = normalized.toLowerCase().lastIndexOf(CAPABILITY_PATH_MARKER);
  if (markerIndex !== -1) {
    normalized = normalized.slice(markerIndex + CAPABILITY_PATH_MARKER.length);
  }
  normalized = normalized.replace(/^\/+/, '');
  if (normalized.startsWith('./')) {
    return normalized;
  }
  return `./${normalized}`;
}

export function convertImportPathToContextKey(importPath: string): string | null {
  let contextKey: string | null = null;

  if (importPath) {
    const normalized = importPath.replace(/\\/g, '/');
    const markerIndex = normalized.toLowerCase().lastIndexOf(CAPABILITY_PATH_MARKER);
    let relativePart: string | null = null;

    if (markerIndex !== -1) {
      relativePart = normalized.substring(markerIndex + CAPABILITY_PATH_MARKER.length);
    } else if (normalized.startsWith('./')) {
      relativePart = normalized.substring(2);
    } else {
      relativePart = null;
    }

    if (relativePart) {
      relativePart = relativePart.replace(/^\/+/, '');
      relativePart = relativePart.replace(/\.(tsx|ts|jsx|js)$/, '');
    }

    if (relativePart) {
      contextKey = normalizeCapabilityContextKey(`./${relativePart}.tsx`);
    }
  }

  if (process.env.NODE_ENV === 'development') {
    console.info(
      `[capability-path] import_path="${importPath}" contextKey="${contextKey}"`
    );
  }

  return contextKey;
}
