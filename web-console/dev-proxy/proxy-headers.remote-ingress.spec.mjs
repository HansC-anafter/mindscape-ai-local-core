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

test('remote proxy replaces spoofed identity headers with verified claims', () => {
  const headers = copyProxyRequestHeaders(
    {
      'x-mindscape-identity-provider': 'spoofed',
      'x-mindscape-identity-subject': 'spoofed',
    },
    target,
    {
      stripRemoteIdentityHeaders: true,
      trustedRemoteIdentity: {
        provider: 'cloudflare-access',
        issuer: 'https://example.cloudflareaccess.com',
        subject: 'verified-subject',
        email: 'person@example.com',
      },
    },
  );

  assert.equal(headers['x-mindscape-identity-provider'], 'cloudflare-access');
  assert.equal(
    headers['x-mindscape-identity-issuer'],
    'https://example.cloudflareaccess.com',
  );
  assert.equal(headers['x-mindscape-identity-subject'], 'verified-subject');
  assert.equal(headers['x-mindscape-identity-email'], 'person@example.com');
});
