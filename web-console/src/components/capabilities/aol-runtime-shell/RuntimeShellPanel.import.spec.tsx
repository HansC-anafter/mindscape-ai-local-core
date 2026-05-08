import { describe, expect, it } from 'vitest';

describe('RuntimeShellPanel dynamic import', () => {
  it('resolves the runtime shell panel module without hanging', async () => {
    const module = await Promise.race([
      import('./RuntimeShellPanel'),
      new Promise<never>((_resolve, reject) => {
        setTimeout(() => reject(new Error('RuntimeShellPanel import timed out')), 5000);
      }),
    ]);

    expect(module.RuntimeShellPanel).toBeTypeOf('function');
  }, 7000);
});
