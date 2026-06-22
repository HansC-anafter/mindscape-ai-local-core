import '@testing-library/jest-dom/vitest';
import React from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { BaseModal } from './BaseModal';

describe('BaseModal', () => {
  afterEach(() => {
    cleanup();
    document.body.style.overflow = '';
  });

  it('renders modal content inside the owning React tree', () => {
    const { container } = render(
      <div data-testid="host-container">
        <BaseModal isOpen onClose={vi.fn()} title="Inline modal">
          <div>Modal body</div>
        </BaseModal>
      </div>,
    );

    expect(screen.getByText('Inline modal')).toBeInTheDocument();
    expect(container).toContainElement(screen.getByText('Inline modal'));
  });

  it('keeps the legacy modal spacing and scroll container', () => {
    render(
      <BaseModal isOpen onClose={vi.fn()} title="Legacy modal">
        <div>Scrollable modal body</div>
      </BaseModal>,
    );

    const dialog = screen.getByRole('dialog');
    expect(dialog).toHaveClass('fixed', 'z-[70]');

    const shell = dialog.firstElementChild;
    expect(shell).toHaveClass('mx-4', 'max-h-[90vh]', 'overflow-hidden', 'flex', 'flex-col');
    expect(shell).toHaveStyle({ maxHeight: '90vh' });
    expect(screen.getByText('Legacy modal').closest('div')).toHaveClass('flex-shrink-0');
    expect(screen.getByText('Scrollable modal body').parentElement).toHaveClass('p-6', 'overflow-y-auto', 'flex-1', 'min-h-0');
  });

  it('renders above capability host rails', () => {
    render(
      <BaseModal isOpen onClose={vi.fn()} title="Rail-safe modal">
        <div>Modal body</div>
      </BaseModal>,
    );

    expect(screen.getByRole('dialog')).toHaveClass('z-[70]');
  });
});
