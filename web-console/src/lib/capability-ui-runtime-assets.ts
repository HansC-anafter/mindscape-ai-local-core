import type { ComponentType } from 'react';
import * as ReactRuntime from 'react';
import * as ReactDOMRuntime from 'react-dom';
import { buildRuntimeAssetFetchUrl } from './capability-runtime-asset-url';
import type { UIComponentInfo } from './capability-ui-loader-types';

const MINDSCAPE_RUNTIME_REACT_BRIDGE_OWNER = '__mindscapeRuntimeReactBridgeOwner';

type MindscapeRuntimeReactBridge = {
  React: typeof ReactRuntime;
  ReactDOM: Pick<typeof ReactDOMRuntime, 'flushSync' | 'createPortal'>;
  [MINDSCAPE_RUNTIME_REACT_BRIDGE_OWNER]?: 'host';
};

declare global {
  // Runtime ESM packs receive React from the host bundle through this bridge.
  // eslint-disable-next-line no-var
  var MindscapeRuntimeReact: MindscapeRuntimeReactBridge | undefined;
}

function ensureRuntimeReactBridge(): void {
  if (globalThis.MindscapeRuntimeReact?.[MINDSCAPE_RUNTIME_REACT_BRIDGE_OWNER] === 'host') {
    return;
  }

  globalThis.MindscapeRuntimeReact = {
    React: ReactRuntime,
    ReactDOM: {
      flushSync: ReactDOMRuntime.flushSync,
      createPortal: ReactDOMRuntime.createPortal,
    },
    [MINDSCAPE_RUNTIME_REACT_BRIDGE_OWNER]: 'host',
  };
}

function resolveRuntimeAssetUrl(assetUrl: string, apiUrl: string): string {
  if (/^https?:\/\//.test(assetUrl)) {
    return assetUrl;
  }
  const baseUrl = apiUrl.replace(/\/+$/, '');
  const path = assetUrl.startsWith('/') ? assetUrl : `/${assetUrl}`;
  return `${baseUrl}${path}`;
}

async function sha256Integrity(source: string): Promise<string> {
  if (!globalThis.crypto?.subtle) {
    throw new Error('WebCrypto subtle digest is unavailable');
  }
  const digest = await globalThis.crypto.subtle.digest(
    'SHA-256',
    new TextEncoder().encode(source),
  );
  const bytes = Array.from(new Uint8Array(digest));
  const binary = bytes.map((byte) => String.fromCharCode(byte)).join('');
  return `sha256-${btoa(binary)}`;
}

export async function loadRuntimeESMComponent(
  component: UIComponentInfo,
  apiUrl: string,
): Promise<ComponentType<any> | null> {
  if (!component.asset_url) {
    return null;
  }
  if (!component.integrity) {
    console.warn(`[loadCapabilityUIComponent] Runtime asset for ${component.code} missing integrity`);
    return null;
  }
  ensureRuntimeReactBridge();
  const assetUrl = buildRuntimeAssetFetchUrl(
    resolveRuntimeAssetUrl(component.asset_url, apiUrl),
    component.integrity,
  );
  const response = await fetch(assetUrl, { cache: 'force-cache' });
  if (!response.ok) {
    throw new Error(`Runtime asset fetch failed: ${response.status}`);
  }
  const source = await response.text();
  const actualIntegrity = await sha256Integrity(source);
  if (actualIntegrity !== component.integrity) {
    throw new Error(`Runtime asset integrity mismatch for ${component.code}`);
  }
  const blob = new Blob([source], { type: 'text/javascript' });
  const objectUrl = URL.createObjectURL(blob);
  try {
    const module = await import(/* webpackIgnore: true */ objectUrl);
    return module[component.export] || module.default || null;
  } finally {
    URL.revokeObjectURL(objectUrl);
  }
}
