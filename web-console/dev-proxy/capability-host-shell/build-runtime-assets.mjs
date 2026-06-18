import { spawn } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';

export const CAPABILITY_HOST_CSS_OUTPUT = '.next/mindscape-capability-host/app-layout.css';

let capabilityHostStylesheetPromise = null;

export function findReadableRuntimeAssetPath(candidates = []) {
  for (const candidate of candidates) {
    const absolutePath = path.resolve(process.cwd(), candidate);
    if (fs.existsSync(absolutePath)) {
      return absolutePath;
    }
  }
  return null;
}

export function buildCapabilityHostStylesheet() {
  if (capabilityHostStylesheetPromise) {
    return capabilityHostStylesheetPromise;
  }
  const startedAt = Date.now();
  console.log('[frontend-proxy] capability_host_stylesheet_build_start');
  capabilityHostStylesheetPromise = new Promise((resolve) => {
    const outputPath = path.resolve(process.cwd(), CAPABILITY_HOST_CSS_OUTPUT);
    fs.mkdirSync(path.dirname(outputPath), { recursive: true });
    const child = spawn(
      './node_modules/.bin/tailwindcss',
      [
        '-i',
        './src/app/globals.css',
        '-o',
        `./${CAPABILITY_HOST_CSS_OUTPUT}`,
        '--minify',
      ],
      {
        cwd: process.cwd(),
        stdio: 'ignore',
      },
    );
    const timeout = setTimeout(() => {
      child.kill('SIGTERM');
      resolve(false);
    }, 90_000);
    child.on('exit', (code) => {
      clearTimeout(timeout);
      console.log(`[frontend-proxy] capability_host_stylesheet_build_done ${JSON.stringify({
        duration_ms: Date.now() - startedAt,
        ok: code === 0,
      })}`);
      resolve(code === 0);
    });
    child.on('error', () => {
      clearTimeout(timeout);
      console.log(`[frontend-proxy] capability_host_stylesheet_build_done ${JSON.stringify({
        duration_ms: Date.now() - startedAt,
        ok: false,
      })}`);
      resolve(false);
    });
  }).finally(() => {
    capabilityHostStylesheetPromise = null;
  });
  return capabilityHostStylesheetPromise;
}

export function prepareCapabilityHostRuntimeAssets() {
  if (findReadableRuntimeAssetPath([CAPABILITY_HOST_CSS_OUTPUT])) {
    return Promise.resolve(true);
  }
  return buildCapabilityHostStylesheet();
}

export async function resolveCapabilityHostStylesheetPath(candidates = []) {
  const existingPath = findReadableRuntimeAssetPath(candidates);
  if (existingPath) {
    return existingPath;
  }
  await buildCapabilityHostStylesheet();
  return findReadableRuntimeAssetPath(candidates);
}
