import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { InlineAolObjectRef, clearInlineObjectReferencePreviewCache } from './InlineAolObjectRef';

const readPreview = vi.fn();

vi.mock('@/lib/api-url', () => ({
  getApiBaseUrl: () => 'http://localhost:8200',
}));

vi.mock('@/lib/object-reference-client', () => ({
  readObjectReferencePreviewWithSync: (...args: unknown[]) => readPreview(...args),
}));

const objectRef = {
  uri: 'mindscape://ig/discovery_target/jc6jf4.__',
  owner_pack: 'ig',
  object_kind: 'discovery_target',
  object_id: 'jc6jf4.__',
  workspace_id: 'ws_1',
};

function readyPreview() {
  return {
    status: 'ready',
    summary: {
      title: '@jc6jf4.__',
      subtitle: '@source',
      summary_text: 'Profile summary',
      labels: ['private'],
      thumbnail_ref: '/api/v1/ig/avatar/jc6jf4.__?workspace_id=ws_1',
      owner_surface_url: '/workspaces/ws_1/capability-ui-hosts/ig/accounts?target_handle=jc6jf4.__',
    },
  };
}

afterEach(() => {
  vi.clearAllMocks();
  clearInlineObjectReferencePreviewCache();
});

describe('InlineAolObjectRef', () => {
  it('keeps the preview open during the hover handoff grace window', async () => {
    readPreview.mockResolvedValue(readyPreview());
    render(
      <InlineAolObjectRef
        workspaceId="ws_1"
        objectRef={objectRef}
        label="@jc6jf4.__"
        previewDelayMs={0}
      />,
    );

    const trigger = screen.getByRole('button', { name: 'Preview AOL object @jc6jf4.__' });
    const wrapper = trigger.parentElement as HTMLElement;
    await act(async () => {
      fireEvent.pointerEnter(wrapper);
    });
    await waitFor(() => expect(screen.getByRole('dialog')).toBeInTheDocument());

    await act(async () => {
      fireEvent.pointerLeave(wrapper);
      await new Promise((resolve) => window.setTimeout(resolve, 120));
    });

    expect(screen.getByRole('dialog')).toBeInTheDocument();
    await act(async () => {
      fireEvent.pointerEnter(wrapper);
    });
  });

  it('closes the preview with Escape', async () => {
    readPreview.mockResolvedValue(readyPreview());
    render(
      <InlineAolObjectRef
        workspaceId="ws_1"
        objectRef={objectRef}
        label="@jc6jf4.__"
        previewDelayMs={0}
      />,
    );

    const trigger = screen.getByRole('button', { name: 'Preview AOL object @jc6jf4.__' });
    fireEvent.pointerEnter(trigger.parentElement as HTMLElement);
    await waitFor(() => expect(screen.getByRole('dialog')).toBeInTheDocument());

    fireEvent.keyDown(document, { key: 'Escape' });

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('hides a failed thumbnail instead of leaving a broken image frame', async () => {
    readPreview.mockResolvedValue(readyPreview());
    const { container } = render(
      <InlineAolObjectRef
        workspaceId="ws_1"
        objectRef={objectRef}
        label="@jc6jf4.__"
        previewDelayMs={0}
      />,
    );

    const trigger = screen.getByRole('button', { name: 'Preview AOL object @jc6jf4.__' });
    fireEvent.pointerEnter(trigger.parentElement as HTMLElement);
    await waitFor(() => expect(container.querySelector('img')).not.toBeNull());

    fireEvent.error(container.querySelector('img') as HTMLImageElement);

    expect(container.querySelector('img')).toBeNull();
  });
});
