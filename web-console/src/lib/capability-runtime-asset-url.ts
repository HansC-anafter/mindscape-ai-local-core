export function buildRuntimeAssetFetchUrl(assetUrl: string, integrity?: string): string {
  const cacheKey = integrity?.trim();
  if (!cacheKey) {
    return assetUrl;
  }

  const hashIndex = assetUrl.indexOf('#');
  const baseUrl = hashIndex >= 0 ? assetUrl.slice(0, hashIndex) : assetUrl;
  const hash = hashIndex >= 0 ? assetUrl.slice(hashIndex) : '';
  const separator = baseUrl.includes('?') ? '&' : '?';

  return `${baseUrl}${separator}integrity=${encodeURIComponent(cacheKey)}${hash}`;
}
