import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { MessageKey } from '@/lib/i18n';
import { DirectorGraphImportExport } from './DirectorGraphImportExport';

const t = (key: MessageKey) => key;

describe('DirectorGraphImportExport', () => {
  it('exports on demand and parses portable graph JSON for import', () => {
    const onExport = vi.fn();
    const onImport = vi.fn();
    const onInvalidImport = vi.fn();
    render(
      <DirectorGraphImportExport
        value={JSON.stringify({
          schema_version: 'composition_graph.v1',
          graph_id: 'cg_test',
          title: 'Composition Graph',
          nodes: [],
          edges: [],
          viewport: { x: 0, y: 0, zoom: 1 },
        })}
        error={null}
        onChange={vi.fn()}
        onExport={onExport}
        onImport={onImport}
        onInvalidImport={onInvalidImport}
        t={t}
      />,
    );

    fireEvent.click(screen.getByTestId('director-graph-export'));
    expect(onExport).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByTestId('director-graph-import'));
    expect(onImport).toHaveBeenCalledWith(expect.objectContaining({ graph_id: 'cg_test' }));
    expect(onInvalidImport).not.toHaveBeenCalled();
  });
});
