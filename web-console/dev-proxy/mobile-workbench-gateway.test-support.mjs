import crypto from 'node:crypto';

export {
  extractMobileWorkbenchGatewayRequestContext,
  isMobileWorkbenchGatewayPathAllowed,
  isMobileWorkbenchGatewayRequestAllowed,
  isMobileWorkbenchGatewayRequestAllowedAsync,
  resolveMobileWorkbenchGatewayConfig,
} from './mobile-workbench-gateway.mjs';

export const RSA_KEY_PAIR = crypto.generateKeyPairSync('rsa', {
  modulusLength: 2048,
  publicKeyEncoding: {
    type: 'spki',
    format: 'pem',
  },
  privateKeyEncoding: {
    type: 'pkcs1',
    format: 'pem',
  },
});

export function base64urlEncode(value) {
  return Buffer.from(value)
    .toString('base64')
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '');
}

export function createSignedAccessJwt(payload = {}, privateKey = RSA_KEY_PAIR.privateKey) {
  const header = base64urlEncode(JSON.stringify({ alg: 'RS256', typ: 'JWT' }));
  const body = base64urlEncode(JSON.stringify(payload));
  const signingInput = `${header}.${body}`;
  const signature = crypto.createSign('RSA-SHA256')
    .update(signingInput)
    .end()
    .sign(privateKey);
  return `${signingInput}.${base64urlEncode(signature)}`;
}

export function createAccessJwt(payload = {}) {
  const header = Buffer.from(JSON.stringify({ alg: 'none', typ: 'JWT' }))
    .toString('base64')
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '');
  const body = Buffer.from(JSON.stringify(payload))
    .toString('base64')
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '');

  return `${header}.${body}.sig`;
}
