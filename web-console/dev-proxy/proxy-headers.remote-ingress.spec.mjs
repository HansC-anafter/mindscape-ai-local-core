import assert from 'node:assert/strict';
import test from 'node:test';

import { copyProxyRequestHeaders } from './proxy-headers.mjs';


const target = new URL('http://127.0.0.1:3000');

test('client ingress marker is stripped on local requests', () => {
  const headers = copyProxyRequestHeaders(
    { 'x-mindscape-remote-ingress': 'remote_workbench' },
    target,
  );

  assert.equal(headers['x-mindscape-remote-ingress'], undefined);
});

test('remote proxy replaces every client marker with the trusted value', () => {
  const headers = copyProxyRequestHeaders(
    { 'x-mindscape-remote-ingress': 'client-spoof' },
    target,
    { stripRemoteIdentityHeaders: true },
  );

  assert.equal(headers['x-mindscape-remote-ingress'], 'remote_workbench');
});
