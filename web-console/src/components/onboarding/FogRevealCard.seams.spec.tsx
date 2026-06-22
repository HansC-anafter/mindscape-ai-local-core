import type { ReactNode } from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@react-three/fiber', () => ({
  Canvas: ({ children: _children }: { children?: ReactNode }) => (
    <div data-testid="fog-canvas" />
  ),
  extend: vi.fn(),
  useFrame: vi.fn(),
}));

vi.mock('@react-three/drei', () => ({
  shaderMaterial: vi.fn(() => function FogMaterial() {
    return null;
  }),
}));

import { FogRevealCard } from './FogRevealCard';

describe('FogRevealCard seams', () => {
  it('keeps the public facade rendering children through the split implementation', () => {
    render(
      <FogRevealCard>
        <div>Intro content</div>
      </FogRevealCard>,
    );

    expect(screen.getByText('Intro content')).toBeInTheDocument();
    expect(screen.getAllByTestId('fog-canvas')).toHaveLength(2);
  });
});
