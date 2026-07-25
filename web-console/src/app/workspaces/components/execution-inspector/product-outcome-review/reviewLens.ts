import type { UIComponentInfo } from '@/lib/capability-ui-loader';
import type { ReviewLensPin, ReviewLensSelection } from './types';

export function selectPinnedReviewLensComponent(
  components: UIComponentInfo[],
  pin: ReviewLensPin,
): ReviewLensSelection | null {
  const matches = components.filter((component) => (
    component.code === pin.component_code
    && component.integrity === pin.integrity
    && component.runtime === pin.runtime
    && component.export === pin.export
    && typeof component.asset_url === 'string'
    && component.asset_url.length > 0
    && component.legacy_context !== true
  ));
  return matches.length === 1 ? { component: matches[0], pin } : null;
}
