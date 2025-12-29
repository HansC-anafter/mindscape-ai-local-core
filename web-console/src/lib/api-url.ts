/**
 * 统一的 API URL 工具函数
 * 所有前端代码应该使用这个函数获取 API URL，而不是硬编码端口
 */

/**
 * 获取初始 API URL（同步版本，用于初始化）
 * 优先使用环境变量，否则使用端口配置系统的默认值（8200）
 */
export function getApiBaseUrl(): string {
  // 优先使用环境变量
  if (process.env.NEXT_PUBLIC_API_URL && process.env.NEXT_PUBLIC_API_URL.startsWith('http')) {
    return process.env.NEXT_PUBLIC_API_URL;
  }

  // 使用同源代理（如果前端和后端在同一域名下）
  if (typeof window !== 'undefined') {
    const protocol = window.location.protocol;
    const hostname = window.location.hostname;
    // 使用端口配置系统的默认值（8200）
    return `${protocol}//${hostname}:8200`;
  }

  // 服务端渲染时使用默认值（端口配置系统默认值）
  return 'http://localhost:8200';
}

/**
 * 获取动态 API URL（异步版本，支持从端口配置服务获取）
 * 这个函数会尝试从端口配置服务获取最新的 URL，如果失败则回退到初始 URL
 */
export async function getApiUrl(): Promise<string> {
  // 如果 settingsApi 可用，使用它的动态获取功能
  try {
    const { getApiUrl: getDynamicApiUrl } = await import('../app/settings/utils/settingsApi');
    return await getDynamicApiUrl();
  } catch {
    // 如果导入失败，回退到同步版本
    return getApiBaseUrl();
  }
}


