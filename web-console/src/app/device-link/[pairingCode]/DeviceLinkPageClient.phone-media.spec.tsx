import { describe, expect, it } from 'vitest';
import { act, screen, waitFor } from '@testing-library/react';

import {
  clickButton,
  connectAndPairPhone,
  markPhoneConnected,
  mocks,
  renderDeviceLinkPage,
} from './DeviceLinkPageClient.test-support';

describe('DeviceLinkPageClient phone media behavior', () => {
  it('flips phone camera by replacing the video track without closing the media session', async () => {
    await connectAndPairPhone();
    await waitFor(() => expect(mocks.phoneHandles).toHaveLength(1));
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
    });
    await markPhoneConnected();
    await waitFor(() => expect(screen.getByRole('button', { name: 'Streaming' })).toBeDisabled());

    await clickButton('Use front camera');

    expect(mocks.phoneHandles[0].stop).not.toHaveBeenCalled();
    await waitFor(() =>
      expect(mocks.phoneHandles[0].replaceVideoTrack).toHaveBeenCalledWith(
        expect.objectContaining({
          facingMode: { ideal: 'user' },
          width: { ideal: 1280 },
          height: { ideal: 720 },
          frameRate: { max: 30 },
        }),
        undefined,
      ),
    );
    expect(mocks.startPhoneBrowserSourceSession).toHaveBeenCalledTimes(1);
  });

  it('keeps the phone source recoverable when camera replacement needs a media restart', async () => {
    await connectAndPairPhone();
    await waitFor(() => expect(mocks.phoneHandles).toHaveLength(1));
    await markPhoneConnected();
    mocks.phoneHandles[0].replaceVideoTrack.mockImplementationOnce(async () => {
      const error = new Error('replace_track_failed');
      mocks.phoneInputs[0].onError(error);
      throw error;
    });

    await clickButton('Use front camera');

    await waitFor(() => expect(mocks.startPhoneBrowserSourceSession).toHaveBeenCalledTimes(2));
    expect(mocks.phoneHandles[0].stop).toHaveBeenCalledTimes(1);
    expect(mocks.startPhoneBrowserSourceSession).toHaveBeenLastCalledWith(
      expect.objectContaining({
        facingMode: 'user',
        videoOrientation: 'portrait',
      }),
    );
    expect(screen.getByTestId('device-link-connection-status-detail')).toHaveTextContent(
      'Front camera enabled.',
    );
    expect(screen.queryByRole('button', { name: 'Reconnect' })).toBeNull();
  });

  it('switches phone capture orientation without reopening the media session', async () => {
    await connectAndPairPhone();
    await waitFor(() => expect(mocks.phoneHandles).toHaveLength(1));
    await markPhoneConnected();

    await clickButton('Use landscape capture');

    expect(mocks.phoneHandles[0].setVideoOrientation).toHaveBeenCalledWith('landscape');
    expect(mocks.startPhoneBrowserSourceSession).toHaveBeenCalledTimes(1);
    expect(mocks.openDeviceControlSocket).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId('device-link-connection-status-detail')).toHaveTextContent(
      'Landscape capture enabled.',
    );
  });

  it('shows fullscreen fallback copy when the browser does not expose fullscreen APIs', async () => {
    renderDeviceLinkPage();

    await clickButton('Enter fullscreen');

    expect(screen.getByText('Fullscreen unavailable. The capture layout stays edge-to-edge.')).toBeTruthy();
  });
});
