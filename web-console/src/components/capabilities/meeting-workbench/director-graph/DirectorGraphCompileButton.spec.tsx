import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { MessageKey } from '@/lib/i18n';
import { DirectorGraphCompileButton } from './DirectorGraphCompileButton';

const t = (key: MessageKey) => key;

describe('DirectorGraphCompileButton', () => {
  it('calls compile when enabled and locks while running', () => {
    const onCompile = vi.fn();
    const { rerender } = render(
      <DirectorGraphCompileButton disabled={false} status="idle" onCompile={onCompile} t={t} />,
    );

    fireEvent.click(screen.getByTestId('director-graph-compile'));
    expect(onCompile).toHaveBeenCalledTimes(1);

    rerender(<DirectorGraphCompileButton disabled={false} status="running" onCompile={onCompile} t={t} />);
    expect(screen.getByTestId('director-graph-compile')).toBeDisabled();
  });
});
