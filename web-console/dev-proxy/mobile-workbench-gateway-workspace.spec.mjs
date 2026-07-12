import assert from 'node:assert/strict';
import test from 'node:test';

import {
  authorizeRemoteWorkbenchRequest,
} from './mobile-workbench-gateway.mjs';
import {
  createEffectivePolicyPayload,
  createGatewayConfig,
  createPolicyResolution,
  createSignedAccessJwt,
  createTestVerifier,
} from './mobile-workbench-gateway.test-support.mjs';

const verifier = createTestVerifier();

function workspaceResolution(workspaceId, {
  directPrincipals = [],
  effectivePrincipals = null,
  capabilityCodes = ['yogacoach'],
} = {}) {
  const globals = [
    {
      subject: 'subject-global-a',
      email: 'hans@anafter.co',
      grant_sources: ['local_core_super_admin'],
    },
    {
      subject: 'subject-global-b',
      email: 'pproo.reader@gmail.com',
      grant_sources: ['local_core_super_admin'],
    },
  ];
  const projected = effectivePrincipals || [
    ...globals,
    ...directPrincipals.map((principal) => ({
      ...principal,
      grant_sources: ['workspace_direct_member'],
    })),
  ];
  return createPolicyResolution({
    workspaceId,
    effectivePayload: createEffectivePolicyPayload({
      workspaceId,
      directPrincipals,
      effectivePrincipals: projected,
      capabilityCodes,
    }),
  });
}

async function request({
  workspaceId = 'workspace-a',
  claims = {},
  config = createGatewayConfig(),
  headers = {},
  url = null,
  resolution = null,
} = {}) {
  let resolverCalls = 0;
  const result = await authorizeRemoteWorkbenchRequest(
    url || `/workspaces/${workspaceId}/capability-ui-hosts/yogacoach`,
    {
      host: 'remote-workbench.mindscapeai.app',
      'Cf-Access-Jwt-Assertion': createSignedAccessJwt({ claims }),
      ...headers,
    },
    config,
    {
      verifyAccessToken: verifier,
      resolveWorkspaceCapabilityPolicy: async () => {
        resolverCalls += 1;
        return resolution || workspaceResolution(workspaceId);
      },
    },
  );
  return { result, resolverCalls };
}

test('enrollment_only records only an exact pending designation and denies all data', async () => {
  const config = createGatewayConfig({
    state: 'enrollment_only',
    administrators: [
      {
        subject: 'pending_identity_resolution',
        email: 'hans@anafter.co',
        status: 'pending',
      },
      {
        subject: 'pending_identity_resolution',
        email: 'pproo.reader@gmail.com',
        status: 'pending',
      },
    ],
  });
  const designated = await request({ config });
  assert.equal(designated.result.allowed, false);
  assert.equal(designated.result.reason_code, 'remote_access_enrollment_only');
  assert.deepEqual(designated.result.subject_candidate, {
    issuer: 'https://shy-resonance-542b.cloudflareaccess.com',
    subject: 'subject-global-a',
    email: 'hans@anafter.co',
  });
  assert.equal(designated.resolverCalls, 0);

  const outsider = await request({
    config,
    claims: { sub: 'subject-outsider', email: 'outsider@example.com' },
  });
  assert.equal(outsider.result.allowed, false);
  assert.equal(outsider.result.subject_candidate, null);
  assert.equal(outsider.resolverCalls, 0);
});

test('both global administrators inherit workspace A and B without direct rows', async () => {
  for (const [workspaceId, subject, email] of [
    ['workspace-a', 'subject-global-a', 'hans@anafter.co'],
    ['workspace-a', 'subject-global-b', 'pproo.reader@gmail.com'],
    ['workspace-b', 'subject-global-a', 'hans@anafter.co'],
    ['workspace-b', 'subject-global-b', 'pproo.reader@gmail.com'],
  ]) {
    const { result } = await request({
      workspaceId,
      claims: { sub: subject, email },
      resolution: workspaceResolution(workspaceId),
    });
    assert.equal(result.allowed, true);
    assert.deepEqual(result.grant_sources, ['local_core_super_admin']);
  }
});

test('ordinary direct member is limited to its one workspace and outsider is denied', async () => {
  const direct = { subject: 'subject-direct', email: 'direct@example.com' };
  const allowed = await request({
    workspaceId: 'workspace-a',
    claims: { sub: direct.subject, email: direct.email },
    resolution: workspaceResolution('workspace-a', { directPrincipals: [direct] }),
  });
  assert.equal(allowed.result.allowed, true);
  assert.deepEqual(allowed.result.grant_sources, ['workspace_direct_member']);

  const deniedCrossWorkspace = await request({
    workspaceId: 'workspace-b',
    claims: { sub: direct.subject, email: direct.email },
    resolution: workspaceResolution('workspace-b'),
  });
  assert.equal(deniedCrossWorkspace.result.allowed, false);
  assert.equal(deniedCrossWorkspace.result.reason_code, 'workspace_membership_required');
  assert.equal(deniedCrossWorkspace.result.verification_stage, 'principal_verified');

  const outsider = await request({
    claims: { sub: 'subject-outsider', email: 'outsider@example.com' },
  });
  assert.equal(outsider.result.allowed, false);
  assert.equal(outsider.result.reason_code, 'workspace_membership_required');
});

test('the same subject is deduplicated while retaining both grant sources', async () => {
  const direct = { subject: 'subject-global-a', email: 'hans@anafter.co' };
  const resolution = workspaceResolution('workspace-a', {
    directPrincipals: [direct],
    effectivePrincipals: [
      {
        ...direct,
        grant_sources: ['local_core_super_admin', 'workspace_direct_member'],
      },
      {
        subject: 'subject-global-b',
        email: 'pproo.reader@gmail.com',
        grant_sources: ['local_core_super_admin'],
      },
    ],
  });
  const { result } = await request({ resolution });
  assert.equal(result.allowed, true);
  assert.deepEqual(result.grant_sources, [
    'local_core_super_admin',
    'workspace_direct_member',
  ]);
});

test('email, URL, token workspace, Referer, and Host cannot create membership', async () => {
  const sameEmailWrongSubject = await request({
    claims: { sub: 'wrong-subject', email: 'hans@anafter.co' },
  });
  assert.equal(sameEmailWrongSubject.result.reason_code, 'workspace_membership_required');

  const tokenMismatch = await request({
    claims: { workspace_id: 'workspace-b' },
  });
  assert.equal(tokenMismatch.result.reason_code, 'access_token_workspace_mismatch');
  assert.equal(tokenMismatch.resolverCalls, 0);

  const refererMismatch = await request({
    url: '/api/v1/workspaces/workspace-a/tasks',
    headers: {
      referer: 'https://remote-workbench.mindscapeai.app/workspaces/workspace-b/capability-ui-hosts/yogacoach',
    },
  });
  assert.equal(refererMismatch.result.reason_code, 'request_context_mismatch');
  assert.equal(refererMismatch.resolverCalls, 0);

  const hostSpoof = await request({
    claims: { sub: 'subject-outsider', email: 'outsider@example.com' },
    headers: { host: 'localhost:3001' },
  });
  assert.equal(hostSpoof.result.reason_code, 'invalid_public_host');
  assert.equal(hostSpoof.resolverCalls, 0);
});

test('effective auth fingerprint drift fails closed', async () => {
  const resolution = workspaceResolution('workspace-a');
  resolution.effectivePolicy.authConfigFingerprint = '0'.repeat(64);
  const { result } = await request({ resolution });
  assert.equal(result.allowed, false);
  assert.equal(result.reason_code, 'workspace_policy_auth_config_mismatch');
});

test('same-revision runtime source or administrator drift fails closed', async () => {
  const sourceDrift = workspaceResolution('workspace-a');
  sourceDrift.effectivePolicy.runtimePolicySource = 'default_deny';
  assert.equal((await request({ resolution: sourceDrift })).result.reason_code,
    'workspace_policy_auth_config_mismatch');

  const administratorDrift = workspaceResolution('workspace-a');
  administratorDrift.effectivePolicy.localCoreSuperAdmins = [{
    subject: 'subject-outsider',
    email: 'outsider@example.com',
    status: 'active',
  }];
  assert.equal((await request({ resolution: administratorDrift })).result.reason_code,
    'workspace_policy_auth_config_mismatch');
});

test('effective source labels cannot contradict active grants', () => {
  const runtimeSourceMismatch = createEffectivePolicyPayload();
  runtimeSourceMismatch.runtime_policy_source = 'default_deny';
  assert.throws(
    () => createPolicyResolution({ effectivePayload: runtimeSourceMismatch }),
    /active_runtime_policy_source_mismatch/,
  );

  const workspaceSourceMismatch = createEffectivePolicyPayload();
  workspaceSourceMismatch.workspace_policy_source = 'default_deny';
  assert.throws(
    () => createPolicyResolution({ effectivePayload: workspaceSourceMismatch }),
    /default_deny_workspace_policy_has_grants/,
  );
});

test('older and newer effective runtime revisions both fail closed', async () => {
  for (const runtimePolicyRevision of [1, 3]) {
    const resolution = workspaceResolution('workspace-a');
    resolution.effectivePolicy.runtimePolicyRevision = runtimePolicyRevision;
    const { result } = await request({ resolution });
    assert.equal(result.allowed, false);
    assert.equal(result.reason_code, 'workspace_policy_auth_config_mismatch');
  }
});
