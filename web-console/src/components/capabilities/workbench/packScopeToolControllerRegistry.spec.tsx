import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import {
  useOptionalPackScopeToolController,
  useRegisterPackScopeToolController,
} from './packScopeToolControllerRegistry';

interface DemoController {
  label: string;
}

function Publisher({
  controllerKey,
  controller,
}: {
  controllerKey: string;
  controller: DemoController;
}) {
  useRegisterPackScopeToolController(controllerKey, controller);
  return <div data-testid="publisher">{controller.label}</div>;
}

function Consumer({ controllerKey }: { controllerKey: string }) {
  const controller = useOptionalPackScopeToolController<DemoController>(controllerKey, null);
  return <div data-testid="consumer">{controller?.label || 'missing'}</div>;
}

describe('packScopeToolControllerRegistry', () => {
  beforeEach(() => {
    delete window.__mindscapePackScopeToolControllers;
  });

  it('lets a pack-scope panel read a controller outside the provider tree', async () => {
    const providerRender = render(
      <Publisher
        controllerKey="demo:pack-scope-tool-controller"
        controller={{ label: 'prefilled controller' }}
      />,
    );

    render(<Consumer controllerKey="demo:pack-scope-tool-controller" />);

    await waitFor(() => {
      expect(screen.getByTestId('consumer')).toHaveTextContent('prefilled controller');
    });

    providerRender.unmount();

    await waitFor(() => {
      expect(screen.getByTestId('consumer')).toHaveTextContent('missing');
    });
  });

  it('does not let an old cleanup remove a newer controller for the same key', async () => {
    const first = render(
      <Publisher
        controllerKey="demo:pack-scope-tool-controller"
        controller={{ label: 'first controller' }}
      />,
    );
    const second = render(
      <Publisher
        controllerKey="demo:pack-scope-tool-controller"
        controller={{ label: 'second controller' }}
      />,
    );
    render(<Consumer controllerKey="demo:pack-scope-tool-controller" />);

    await waitFor(() => {
      expect(screen.getByTestId('consumer')).toHaveTextContent('second controller');
    });

    first.unmount();
    expect(screen.getByTestId('consumer')).toHaveTextContent('second controller');

    second.unmount();

    await waitFor(() => {
      expect(screen.getByTestId('consumer')).toHaveTextContent('missing');
    });
  });
});
