import { describe, expect, it, vi } from 'vitest';

import { startPhoneBrowserSourceSession } from './webrtcSessionClient';
import {
  defaultSessionInput,
  emitSignal,
  flushMicrotasks,
  installMediaDevices,
  installMediaStreamMock,
  installTrackPeerConnectionMock,
  installWebSocketMock,
  MediaStreamMock,
} from './webrtcSessionClient.test-support';

describe('webrtcSessionClient track replacement', () => {
  it('replaces phone camera video track without closing the media session', async () => {
    const oldVideoTrack = { kind: 'video', readyState: 'live', stop: vi.fn() };
    const audioTrack = { kind: 'audio', readyState: 'live', stop: vi.fn() };
    const newVideoTrack = { kind: 'video', readyState: 'live', stop: vi.fn() };
    const initialStream = new MediaStreamMock([oldVideoTrack, audioTrack]);
    const replacementStream = new MediaStreamMock([newVideoTrack]);
    const getUserMedia = vi.fn()
      .mockResolvedValueOnce(initialStream)
      .mockResolvedValueOnce(replacementStream);
    const { instances: sockets } = installWebSocketMock();
    const { replaceTrack } = installTrackPeerConnectionMock(oldVideoTrack);
    installMediaStreamMock();
    installMediaDevices(getUserMedia);

    const handle = await startPhoneBrowserSourceSession({
      ...defaultSessionInput,
      facingMode: 'environment',
    });
    emitSignal(sockets[0], {
      type: 'participant_joined',
      sender: 'source',
      created_at_epoch: 1,
    });
    await flushMicrotasks();

    const nextStream = await handle.replaceVideoTrack?.({
      facingMode: { ideal: 'user' },
      width: { ideal: 1280 },
      height: { ideal: 720 },
      frameRate: { max: 30 },
    });

    expect(getUserMedia).toHaveBeenNthCalledWith(2, {
      video: {
        facingMode: { ideal: 'user' },
        width: { ideal: 1280 },
        height: { ideal: 720 },
        frameRate: { max: 30 },
      },
      audio: false,
    });
    expect(replaceTrack).toHaveBeenCalledWith(newVideoTrack);
    expect(oldVideoTrack.stop).toHaveBeenCalled();
    expect(sockets[0].close).not.toHaveBeenCalled();
    expect(nextStream?.getVideoTracks()).toEqual([newVideoTrack]);
  });

  it('switches phone capture orientation by replacing the outgoing presentation track', async () => {
    const rawVideoTrack = { kind: 'video', readyState: 'live', stop: vi.fn() };
    const audioTrack = { kind: 'audio', readyState: 'live', stop: vi.fn() };
    const landscapeVideoTrack = { kind: 'video', readyState: 'live', stop: vi.fn() };
    const initialStream = new MediaStreamMock([rawVideoTrack, audioTrack]);
    const getUserMedia = vi.fn().mockResolvedValue(initialStream);
    const canvasInstances: any[] = [];
    const transformedTracks = [landscapeVideoTrack];
    const originalCreateElement = document.createElement.bind(document);
    const createElement = vi.spyOn(document, 'createElement').mockImplementation((tagName: string) => {
      if (tagName === 'canvas') {
        const canvas = {
          width: 0,
          height: 0,
          getContext: vi.fn(() => ({
            clearRect: vi.fn(),
            drawImage: vi.fn(),
          })),
          captureStream: vi.fn(() => new MediaStreamMock([transformedTracks.shift()])),
        };
        canvasInstances.push(canvas);
        return canvas as unknown as HTMLElement;
      }
      if (tagName === 'video') {
        return {
          muted: false,
          playsInline: false,
          srcObject: null,
          videoWidth: 640,
          videoHeight: 480,
          play: vi.fn(async () => undefined),
          pause: vi.fn(),
        } as unknown as HTMLElement;
      }
      return originalCreateElement(tagName);
    });
    const requestAnimationFrame = vi.spyOn(window, 'requestAnimationFrame').mockImplementation(() => 1);
    const cancelAnimationFrame = vi.spyOn(window, 'cancelAnimationFrame').mockImplementation(() => undefined);
    const { instances: sockets } = installWebSocketMock();
    const { replaceTrack } = installTrackPeerConnectionMock(rawVideoTrack);
    installMediaStreamMock();
    installMediaDevices(getUserMedia);

    const handle = await startPhoneBrowserSourceSession({
      ...defaultSessionInput,
      facingMode: 'environment',
      videoOrientation: 'portrait',
    });
    emitSignal(sockets[0], {
      type: 'participant_joined',
      sender: 'source',
      created_at_epoch: 1,
    });
    await flushMicrotasks();

    const nextStream = await handle.setVideoOrientation?.('landscape');

    expect(canvasInstances).toHaveLength(1);
    expect(canvasInstances[0]).toMatchObject({ width: 1280, height: 720 });
    expect(replaceTrack).toHaveBeenCalledWith(landscapeVideoTrack);
    expect(nextStream?.getVideoTracks()).toEqual([landscapeVideoTrack]);
    expect(sockets[0].close).not.toHaveBeenCalled();

    createElement.mockRestore();
    requestAnimationFrame.mockRestore();
    cancelAnimationFrame.mockRestore();
  });
});
