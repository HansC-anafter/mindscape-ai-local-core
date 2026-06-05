import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { DesktopSourcePreview } from './DesktopSourcePreview';

describe('DesktopSourcePreview', () => {
  it('renders local preview state without creating an interval loop', () => {
    const setIntervalSpy = vi.spyOn(globalThis, 'setInterval');

    render(
      <DesktopSourcePreview
        stream={null}
        sourceKind="virtual_camera"
        state="idle"
      />,
    );

    expect(screen.getByTestId('desktop-source-local-preview')).toBeTruthy();
    expect(screen.getByText('Virtual camera - idle')).toBeTruthy();
    expect(setIntervalSpy).not.toHaveBeenCalled();
  });
});
