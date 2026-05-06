import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type {
  CapabilityComponentModule,
  CapabilityComponentsContext,
} from './capability-ui-context-types';

function DemoLazyComponent() {
  return null;
}

function createLazyTestContext(
  modules: Record<string, CapabilityComponentModule>,
): {
  context: CapabilityComponentsContext;
  loadModule: ReturnType<typeof vi.fn>;
} {
  const loadModule = vi.fn(async (key: string) => {
    const module = modules[key];
    if (!module) {
      throw new Error(`Unknown lazy module: ${key}`);
    }
    return module;
  });

  const context = ((key: string) => loadModule(key)) as CapabilityComponentsContext;
  context.keys = () => Object.keys(modules);
  context.resolve = (request: string) => request;
  context.id = 'capability-ui-loader-lazy-test-context';

  return { context, loadModule };
}

describe('capability-ui-loader', () => {
  beforeEach(() => {
    vi.resetModules();
    delete globalThis.__MINDSCAPE_CAPABILITY_UI_TEST_CONTEXT__;
  });

  afterEach(() => {
    vi.restoreAllMocks();
    delete globalThis.__MINDSCAPE_CAPABILITY_UI_TEST_CONTEXT__;
  });

  it('loads only the requested component from a lazy capability context', async () => {
    const { context, loadModule } = createLazyTestContext({
      './demo_lazy/components/DemoLazyComponent.tsx': {
        DemoLazyComponent,
      },
      './demo_lazy/components/UnusedComponent.tsx': {
        default: () => null,
      },
    });
    globalThis.__MINDSCAPE_CAPABILITY_UI_TEST_CONTEXT__ = context;

    const {
      loadCapabilityUIComponent,
      primeCapabilityUIComponentMetadata,
    } = await import('./capability-ui-loader');

    primeCapabilityUIComponentMetadata('demo_lazy', [
      {
        code: 'DemoLazyComponent',
        path: 'ui/components/DemoLazyComponent.tsx',
        description: 'Lazy demo component',
        export: 'DemoLazyComponent',
        artifact_types: [],
        playbook_codes: [],
        import_path: '/app/src/app/capabilities/demo_lazy/components/DemoLazyComponent.tsx',
      },
      {
        code: 'UnusedComponent',
        path: 'ui/components/UnusedComponent.tsx',
        description: 'Unused demo component',
        export: 'default',
        artifact_types: [],
        playbook_codes: [],
        import_path: '/app/src/app/capabilities/demo_lazy/components/UnusedComponent.tsx',
      },
    ]);

    const Component = await loadCapabilityUIComponent(
      'demo_lazy',
      'DemoLazyComponent',
      'http://api.test',
    );
    const CachedComponent = await loadCapabilityUIComponent(
      'demo_lazy',
      'DemoLazyComponent',
      'http://api.test',
    );

    expect(Component).toBe(DemoLazyComponent);
    expect(CachedComponent).toBe(DemoLazyComponent);
    expect(loadModule).toHaveBeenCalledTimes(1);
    expect(loadModule).toHaveBeenCalledWith('./demo_lazy/components/DemoLazyComponent.tsx');
  });
});
