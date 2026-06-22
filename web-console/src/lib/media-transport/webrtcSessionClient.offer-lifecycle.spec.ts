import { describe, expect, it, vi } from 'vitest';

import { startPhoneBrowserSourceSession } from './webrtcSessionClient';
import {
  defaultSessionInput,
  emitSignal,
  flushMicrotasks,
  installMediaDevices,
  installOfferPeerConnectionMock,
  installWebSocketMock,
  sentSignalMessages,
} from './webrtcSessionClient.test-support';

describe('webrtcSessionClient offer lifecycle', () => {
  it('does not duplicate the source offer while the first offer is still unanswered', async () => {
    const getUserMedia = vi.fn(async () => ({
      getTracks: () => [{ kind: 'video', readyState: 'live', stop: vi.fn() }],
    }));
    const { instances: sockets } = installWebSocketMock();
    installOfferPeerConnectionMock([
      { type: 'offer', sdp: 'offer_before_workspace' },
      { type: 'offer', sdp: 'offer_after_workspace' },
    ]);
    installMediaDevices(getUserMedia);

    await startPhoneBrowserSourceSession({
      ...defaultSessionInput,
      facingMode: 'environment',
    });

    emitSignal(sockets[0], {
      type: 'participant_joined',
      sender: 'source',
      created_at_epoch: 1,
    });
    await flushMicrotasks(2);

    emitSignal(sockets[0], {
      type: 'participant_joined',
      sender: 'workspace',
      created_at_epoch: 2,
    });
    await flushMicrotasks(2);

    const sentMessages = sentSignalMessages(sockets[0]);
    expect(sentMessages).toContainEqual({ type: 'offer', sdp: 'offer_before_workspace' });
    expect(sentMessages).not.toContainEqual({ type: 'offer', sdp: 'offer_after_workspace' });
  });

  it('resends the source offer when a workspace receiver rejoins after an answered offer', async () => {
    const getUserMedia = vi.fn(async () => ({
      getTracks: () => [{ kind: 'video', readyState: 'live', stop: vi.fn() }],
    }));
    const { instances: sockets } = installWebSocketMock();
    installOfferPeerConnectionMock([
      { type: 'offer', sdp: 'offer_before_answer' },
      { type: 'offer', sdp: 'offer_after_rejoin' },
    ]);
    installMediaDevices(getUserMedia);

    await startPhoneBrowserSourceSession({
      ...defaultSessionInput,
      facingMode: 'environment',
    });

    emitSignal(sockets[0], {
      type: 'participant_joined',
      sender: 'source',
      created_at_epoch: 1,
    });
    await flushMicrotasks(2);

    emitSignal(sockets[0], {
      type: 'answer',
      sender: 'workspace',
      sdp: 'answer_before_rejoin',
      created_at_epoch: 2,
    });
    await flushMicrotasks();

    emitSignal(sockets[0], {
      type: 'participant_joined',
      sender: 'workspace',
      created_at_epoch: 3,
    });
    await flushMicrotasks(2);

    const sentMessages = sentSignalMessages(sockets[0]);
    expect(sentMessages).toContainEqual({ type: 'offer', sdp: 'offer_before_answer' });
    expect(sentMessages).toContainEqual({ type: 'offer', sdp: 'offer_after_rejoin' });
  });
});
