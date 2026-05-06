import type { CapabilityComponentsContext } from '../capability-ui-context-types';

const context = (
  // @ts-ignore - require.context is a webpack feature, not standard TypeScript
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  require.context(
    '../../app/capabilities/performance_direction',
    true,
    /^(?!.*(?:\/__tests__\/|\.test\.tsx$|\.spec\.tsx$|\.stories\.tsx$|\/\._))\.\/(?:components\/)?[^/]+\.tsx$/,
    'lazy'
  ) as CapabilityComponentsContext
);

export default context;
