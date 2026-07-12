export function buildRuntimeAssetFetchUrl(
  assetUrl: string,
  integrity?: string,
  workspaceId?: string,
): string {
  const hashIndex = assetUrl.indexOf('#');
  const baseUrl = hashIndex >= 0 ? assetUrl.slice(0, hashIndex) : assetUrl;
  const hash = hashIndex >= 0 ? assetUrl.slice(hashIndex) : '';
  const parameters: string[] = [];
  const normalizedWorkspaceId = workspaceId?.trim();
  const cacheKey = integrity?.trim();
  if (normalizedWorkspaceId) {
    parameters.push(`workspace_id=${encodeURIComponent(normalizedWorkspaceId)}`);
  }
  if (cacheKey) {
    parameters.push(`integrity=${encodeURIComponent(cacheKey)}`);
  }
  if (parameters.length === 0) {
    return assetUrl;
  }
  const separator = baseUrl.includes('?') ? '&' : '?';
  return `${baseUrl}${separator}${parameters.join('&')}${hash}`;
}
