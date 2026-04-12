import { useEffect, useState } from 'react';

import type { IGPost } from '../../../types';
import type { Metrics } from '../types';

export function useMeasureMetrics(post: IGPost | null) {
  const [metrics, setMetrics] = useState<Metrics | null>(null);

  useEffect(() => {
    if (!post) {
      setMetrics(null);
      return;
    }

    const postMetrics: Metrics = {
      likes: post.frontmatter?.metrics?.likes,
      comments: post.frontmatter?.metrics?.comments,
      shares: post.frontmatter?.metrics?.shares,
      saves: post.frontmatter?.metrics?.saves,
      reach: post.frontmatter?.metrics?.reach,
      impressions: post.frontmatter?.metrics?.impressions,
      engagement_rate: post.frontmatter?.metrics?.engagement_rate,
      backfilled_at: post.frontmatter?.metrics?.backfilled_at,
      backfill_source: post.frontmatter?.metrics?.backfill_source,
    };

    setMetrics(Object.keys(postMetrics).length > 0 ? postMetrics : null);
  }, [post]);

  return { metrics };
}

