import { describe, expect, it, vi } from 'vitest';

import {
  arrayBufferToBase64,
  encodeBrowserPcm16Wav,
  MEETING_VOICE_SAMPLE_RATE,
} from './browserPcmWav';

describe('browserPcmWav', () => {
  it('encodes a mono 16 kHz PCM16 RIFF/WAVE payload with clamping', () => {
    const wav = encodeBrowserPcm16Wav(new Float32Array([-2, 0, 2]));
    const view = new DataView(wav);
    const text = (offset: number, length: number) => String.fromCharCode(
      ...new Uint8Array(wav, offset, length),
    );

    expect(text(0, 4)).toBe('RIFF');
    expect(text(8, 4)).toBe('WAVE');
    expect(text(36, 4)).toBe('data');
    expect(view.getUint16(22, true)).toBe(1);
    expect(view.getUint32(24, true)).toBe(MEETING_VOICE_SAMPLE_RATE);
    expect(view.getUint16(34, true)).toBe(16);
    expect(view.getInt16(44, true)).toBe(-32768);
    expect(view.getInt16(46, true)).toBe(0);
    expect(view.getInt16(48, true)).toBe(32767);
  });

  it('base64-encodes the exact buffer bytes', () => {
    const btoaSpy = vi.spyOn(globalThis, 'btoa');
    expect(arrayBufferToBase64(new Uint8Array([0, 1, 2, 255]).buffer))
      .toBe('AAEC/w==');
    expect(btoaSpy).toHaveBeenCalledTimes(1);
  });
});
