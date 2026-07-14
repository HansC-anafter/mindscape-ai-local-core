import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  deleteHttpWebRtcResource,
  postHttpWebRtcOffer,
  waitForIceGatheringComplete,
} from './httpWebRtcNegotiation';
import { startWhepPreview } from './whepPreviewClient';
import { startWhipPublisher } from './whipPublisherClient';

class FakeMediaStream {
  tracks: any[];

  constructor(tracks: any[] = []) {
    this.tracks = [...tracks];
  }

  addTrack(track: any) {
    this.tracks.push(track);
  }

  getTracks() {
    return this.tracks;
  }
}

class FakePeerConnection {
  static instances: FakePeerConnection[] = [];

  iceGatheringState: RTCIceGatheringState = 'complete';
  connectionState: RTCPeerConnectionState = 'new';
  localDescription: RTCSessionDescription | null = null;
  onconnectionstatechange: (() => void) | null = null;
  ontrack: ((event: { track: any }) => void) | null = null;
  addTrack = vi.fn();
  addTransceiver = vi.fn();
  createOffer = vi.fn(async () => ({ type: 'offer', sdp: 'offer_sdp' }));
  setLocalDescription = vi.fn(async () => {
    this.localDescription = { type: 'offer', sdp: 'offer_sdp' } as RTCSessionDescription;
  });
  setRemoteDescription = vi.fn(async () => undefined);
  close = vi.fn();
  addEventListener = vi.fn();
  removeEventListener = vi.fn();

  constructor() {
    FakePeerConnection.instances.push(this);
  }
}

describe('HTTP WebRTC clients', () => {
  beforeEach(() => {
    FakePeerConnection.instances = [];
    vi.stubGlobal('RTCPeerConnection', FakePeerConnection);
    vi.stubGlobal('MediaStream', FakeMediaStream);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('posts WHIP SDP with bearer authorization and deletes the server resource on stop', async () => {
    const fetchMock = vi.fn(async (_url: string, init?: RequestInit) => {
      if (init?.method === 'DELETE') {
        return new Response(null, { status: 204 });
      }
      return new Response('answer_sdp', {
        status: 201,
        headers: { location: '/resource/whip_1' },
      });
    });
    vi.stubGlobal('fetch', fetchMock);
    const videoTrack = { kind: 'video' } as MediaStreamTrack;
    const stream = new FakeMediaStream([videoTrack]) as unknown as MediaStream;
    const onState = vi.fn();

    const handle = await startWhipPublisher({
      endpoint: 'https://media.test/path/whip',
      token: 'publish_token',
      stream,
      onState,
    });

    const peer = FakePeerConnection.instances[0];
    expect(peer.addTrack).toHaveBeenCalledWith(videoTrack, stream);
    expect(fetchMock).toHaveBeenCalledWith(
      'https://media.test/path/whip',
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({ authorization: 'Bearer publish_token' }),
        body: 'offer_sdp',
      }),
    );
    expect(peer.setRemoteDescription).toHaveBeenCalledWith({
      type: 'answer',
      sdp: 'answer_sdp',
    });
    expect(onState.mock.calls.map(([state]) => state)).toEqual([
      'offer_sent',
      'answer_received',
    ]);

    handle.stop();
    handle.stop();
    await Promise.resolve();

    expect(peer.close).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledWith(
      'https://media.test/resource/whip_1',
      expect.objectContaining({
        method: 'DELETE',
        headers: { authorization: 'Bearer publish_token' },
      }),
    );
  });

  it('creates a WHEP recvonly peer and delivers relay tracks through one stream', async () => {
    const fetchMock = vi.fn(async (_url: string, init?: RequestInit) => (
      init?.method === 'DELETE'
        ? new Response(null, { status: 204 })
        : new Response('answer_sdp', { status: 201, headers: { location: '/resource/whep_1' } })
    ));
    vi.stubGlobal('fetch', fetchMock);
    const onRemoteStream = vi.fn();

    const handle = await startWhepPreview({
      endpoint: 'https://media.test/path/whep',
      token: 'preview_token',
      onRemoteStream,
    });
    const peer = FakePeerConnection.instances[0];
    expect(peer.addTransceiver).toHaveBeenNthCalledWith(1, 'video', { direction: 'recvonly' });
    expect(peer.addTransceiver).toHaveBeenNthCalledWith(2, 'audio', { direction: 'recvonly' });
    const remoteTrack = { kind: 'video', stop: vi.fn() };
    peer.ontrack?.({ track: remoteTrack });

    expect(onRemoteStream).toHaveBeenCalledTimes(1);
    const delivered = onRemoteStream.mock.calls[0][0] as FakeMediaStream;
    expect(delivered.getTracks()).toEqual([remoteTrack]);

    handle.stop();
    await Promise.resolve();
    expect(remoteTrack.stop).toHaveBeenCalled();
    expect(fetchMock).toHaveBeenCalledWith(
      'https://media.test/resource/whep_1',
      expect.objectContaining({ method: 'DELETE' }),
    );
  });

  it('rejects empty HTTP WebRTC answers and still tolerates resource cleanup failure', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('', { status: 201 })));

    await expect(postHttpWebRtcOffer({
      endpoint: 'https://media.test/path/whip',
      token: 'token',
      sdp: 'offer',
    })).rejects.toThrow('http_webrtc_answer_missing');

    vi.stubGlobal('fetch', vi.fn(async () => {
      throw new Error('offline');
    }));
    await expect(deleteHttpWebRtcResource({
      resourceUrl: 'https://media.test/resource/1',
      token: 'token',
    })).resolves.toBeUndefined();
  });

  it('finishes ICE gathering immediately when the peer is already complete', async () => {
    const peer = new FakePeerConnection();
    await expect(waitForIceGatheringComplete(
      peer as unknown as RTCPeerConnection,
    )).resolves.toBeUndefined();
    expect(peer.addEventListener).not.toHaveBeenCalled();
  });
});
