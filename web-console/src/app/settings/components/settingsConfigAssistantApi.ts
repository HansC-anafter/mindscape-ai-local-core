import { getApiBaseUrl } from '../../../lib/api-url';

export const API_URL = getApiBaseUrl();

const jsonHeaders = { 'Content-Type': 'application/json' };

export interface SettingsAssistantAction {
  label: string;
  action: string;
  params?: Record<string, any>;
}

export interface SettingsAssistantChatPayloadOptions {
  message: string;
  currentTab: string;
  currentSection?: string;
  configSnapshot?: unknown;
  systemPrompt: string;
}

export interface SettingsAssistantChatResponse {
  response?: string;
  message?: string;
  actions?: SettingsAssistantAction[];
}

export class SettingsAssistantHttpError extends Error {
  readonly status: number;

  constructor(status: number, message = 'Assistant API request failed') {
    super(message);
    this.name = 'SettingsAssistantHttpError';
    this.status = status;
  }
}

export function resolveSettingsAssistantApiBaseUrl(apiBaseUrl = API_URL): string {
  return apiBaseUrl.startsWith('http') ? apiBaseUrl : '';
}

export function buildSettingsAssistantChatUrl(apiBaseUrl = API_URL): string {
  const apiUrl = resolveSettingsAssistantApiBaseUrl(apiBaseUrl);
  return `${apiUrl}/api/v1/system-settings/assistant/chat`;
}

export function buildSettingsAssistantChatPayload(options: SettingsAssistantChatPayloadOptions) {
  return {
    message: options.message,
    context: {
      current_tab: options.currentTab,
      current_section: options.currentSection,
      config_snapshot: options.configSnapshot,
    },
    system_prompt: options.systemPrompt,
  };
}

export function isSettingsAssistantUnavailableStatus(status: number): boolean {
  return status === 404 || status === 501;
}

export function isSettingsAssistantUnavailableError(error: unknown): boolean {
  return error instanceof SettingsAssistantHttpError
    && isSettingsAssistantUnavailableStatus(error.status);
}

export async function sendSettingsAssistantChat(
  options: SettingsAssistantChatPayloadOptions,
  apiBaseUrl = API_URL
): Promise<SettingsAssistantChatResponse> {
  const response = await fetch(buildSettingsAssistantChatUrl(apiBaseUrl), {
    method: 'POST',
    headers: jsonHeaders,
    body: JSON.stringify(buildSettingsAssistantChatPayload(options)),
  });

  if (!response.ok) {
    throw new SettingsAssistantHttpError(response.status);
  }

  return await response.json() as SettingsAssistantChatResponse;
}
