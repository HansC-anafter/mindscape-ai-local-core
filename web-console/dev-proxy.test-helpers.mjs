import http from 'node:http';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const tempDirs = [];

export function makeTempDir() {
  const nextDir = fs.mkdtempSync(path.join(os.tmpdir(), 'frontend-proxy-remote-workbench-'));
  tempDirs.push(nextDir);
  return nextDir;
}

export function cleanupTempDirs() {
  while (tempDirs.length > 0) {
    const target = tempDirs.pop();
    fs.rmSync(target, { recursive: true, force: true });
  }
}

export function createBackendServer(handler) {
  return createTestServer(async (req, res) => {
    const result = await handler(req);
    const body = JSON.stringify(result.body);
    res.writeHead(result.status, {
      'content-type': 'application/json',
      'content-length': Buffer.byteLength(body),
    });
    res.end(body);
  });
}

export function createTestServer(handler) {
  return http.createServer(handler);
}
